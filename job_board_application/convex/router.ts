import { httpRouter } from "convex/server";
import { httpAction, mutation, query } from "./_generated/server";
import { v } from "convex/values";
import { api } from "./_generated/api";
import type { Id, Doc } from "./_generated/dataModel";

const http = httpRouter();

/**
 * API endpoint for posting new jobs
 *
 * POST /api/jobs
 * Content-Type: application/json
 * 
 * Body:
 * {
 *   "title": "Software Engineer",
 *   "company": "Tech Corp",
 *   "description": "We are looking for...",
 *   "location": "San Francisco, CA",
 *   "remote": true,
 *   "level": "mid",
 *   "totalCompensation": 150000,
 *   "url": "https://company.com/jobs/123",
 *   // Optional; mark as internal/test so UI can ignore
 *   "test": false
 * }
 * 
 * Response:
 * {
 *   "success": true,
 *   "jobId": "job_id_here"
 * }
 */
http.route({
  path: "/api/jobs",
  method: "POST",
  handler: httpAction(async (ctx, request) => {
    try {
      const body = await request.json();
      
      // Validate required fields
      const requiredFields = ["title", "company", "description", "location", "remote", "level", "totalCompensation", "url"];
      for (const field of requiredFields) {
        if (!(field in body)) {
          return new Response(
            JSON.stringify({ error: `Missing required field: ${field}` }),
            { status: 400, headers: { "Content-Type": "application/json" } }
          );
        }
      }

      // Validate level enum
      const validLevels = ["junior", "mid", "senior", "staff"];
      if (!validLevels.includes(body.level)) {
        return new Response(
          JSON.stringify({ error: `Invalid level. Must be one of: ${validLevels.join(", ")}` }),
          { status: 400, headers: { "Content-Type": "application/json" } }
        );
      }

      const jobId = await ctx.runMutation(api.router.insertJobRecord, {
        title: body.title,
        company: body.company,
        description: body.description,
        location: body.location,
        remote: body.remote,
        level: body.level,
        totalCompensation: body.totalCompensation,
        url: body.url,
        test: body.test ?? false,
      });

      return new Response(
        JSON.stringify({ success: true, jobId }),
        { status: 201, headers: { "Content-Type": "application/json" } }
      );
    } catch (error) {
      return new Response(
        JSON.stringify({ error: "Invalid JSON body" }),
        { status: 400, headers: { "Content-Type": "application/json" } }
      );
    }
  }),
});

/**
 * API endpoint to list sites to scrape
 *
 * GET /api/sites
 * Response: [{ _id, name, url, pattern, enabled, lastRunAt }]
 */
http.route({
  path: "/api/sites",
  method: "GET",
  handler: httpAction(async (ctx, _request) => {
    const sites = await ctx.runQuery(api.router.listSites, { enabledOnly: true });
    return new Response(JSON.stringify(sites), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  }),
});

http.route({
  path: "/api/sites",
  method: "POST",
  handler: httpAction(async (ctx, request) => {
    try {
      const body = await request.json();
      const id = await ctx.runMutation(api.router.upsertSite, {
        name: body.name ?? undefined,
        url: body.url,
        pattern: body.pattern ?? undefined,
        enabled: body.enabled ?? true,
      });
      return new Response(JSON.stringify({ success: true, id }), {
        status: 201,
        headers: { "Content-Type": "application/json" },
      });
    } catch (error) {
      return new Response(
        JSON.stringify({ error: "Invalid JSON body" }),
        { status: 400, headers: { "Content-Type": "application/json" } }
      );
    }
  }),
});

export const listSites = query({
  args: { enabledOnly: v.boolean() },
  handler: async (ctx, args) => {
    const q = ctx.db.query("sites");
    if (args.enabledOnly) {
      return await q.withIndex("by_enabled", (q2) => q2.eq("enabled", true)).collect();
    }
    return await q.collect();
  },
});

// Atomically lease the next available site for scraping.
// Excludes completed sites and honors locks.
export const leaseSite = mutation({
  args: {
    workerId: v.string(),
    lockSeconds: v.optional(v.number()),
  },
  handler: async (ctx, args) => {
    const now = Date.now();
    const ttlMs = Math.max(1, Math.floor((args.lockSeconds ?? 300) * 1000));

    // Pull enabled sites and pick the first that is not completed and not locked (or lock expired)
    const candidates = await ctx.db
      .query("sites")
      .withIndex("by_enabled", (q) => q.eq("enabled", true))
      .collect();

    const pick: any = candidates
      .filter((s: any) => !s.completed)
      .filter((s: any) => !s.failed)
      .filter((s: any) => !s.lockExpiresAt || s.lockExpiresAt <= now)
      .sort((a: any, b: any) => (a.lastRunAt ?? 0) - (b.lastRunAt ?? 0))[0];

    if (!pick) return null;

    await ctx.db.patch(pick._id, {
      lockedBy: args.workerId,
      lockExpiresAt: now + ttlMs,
    });
    // Return minimal fields for the worker
    const fresh = await ctx.db.get(pick._id as Id<"sites">);
    if (!fresh) return null;
    const s = fresh as Doc<"sites">;
    return {
      _id: s._id,
      name: s.name,
      url: s.url,
      pattern: s.pattern,
      enabled: s.enabled,
      lastRunAt: s.lastRunAt,
      lockedBy: s.lockedBy,
      lockExpiresAt: s.lockExpiresAt,
      completed: s.completed,
    };
  },
});

// Mark a leased site as completed and clear its lock.
export const completeSite = mutation({
  args: { id: v.id("sites") },
  handler: async (ctx, args) => {
    const now = Date.now();
    await ctx.db.patch(args.id, {
      completed: true,
      lockedBy: "",
      lockExpiresAt: 0,
      lastRunAt: now,
    });
    return { success: true };
  },
});

// Clear a lock without completing, e.g., on failure.
export const releaseSite = mutation({
  args: { id: v.id("sites") },
  handler: async (ctx, args) => {
    await ctx.db.patch(args.id, {
      lockedBy: "",
      lockExpiresAt: 0,
    });
    return { success: true };
  },
});

// Record a failure and release the lock so it can be retried later
export const failSite = mutation({
  args: {
    id: v.id("sites"),
    error: v.optional(v.string()),
  },
  handler: async (ctx, args) => {
    const cur = await ctx.db.get(args.id);
    const count = (cur as any)?.failCount ?? 0;
    await ctx.db.patch(args.id, {
      failCount: count + 1,
      lastFailureAt: Date.now(),
      lastError: args.error,
      failed: true,
      lockedBy: "",
      lockExpiresAt: 0,
    });
    return { success: true };
  },
});

// HTTP endpoint to lease next site
http.route({
  path: "/api/sites/lease",
  method: "POST",
  handler: httpAction(async (ctx, request) => {
    const body = await request.json();
    const site = await ctx.runMutation(api.router.leaseSite, {
      workerId: body.workerId,
      lockSeconds: body.lockSeconds ?? 300,
    });
    return new Response(JSON.stringify(site), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  }),
});

// HTTP endpoint to mark site completed
http.route({
  path: "/api/sites/complete",
  method: "POST",
  handler: httpAction(async (ctx, request) => {
    const body = await request.json();
    const res = await ctx.runMutation(api.router.completeSite, { id: body.id });
    return new Response(JSON.stringify(res), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  }),
});

// HTTP endpoint to release a lock (optional)
http.route({
  path: "/api/sites/release",
  method: "POST",
  handler: httpAction(async (ctx, request) => {
    const body = await request.json();
    const res = await ctx.runMutation(api.router.releaseSite, { id: body.id });
    return new Response(JSON.stringify(res), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  }),
});

// HTTP endpoint to mark a site as failed and release
http.route({
  path: "/api/sites/fail",
  method: "POST",
  handler: httpAction(async (ctx, request) => {
    const body = await request.json();
    const res = await ctx.runMutation(api.router.failSite, { id: body.id, error: body.error });
    return new Response(JSON.stringify(res), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  }),
});

export const upsertSite = mutation({
  args: {
    name: v.optional(v.string()),
    url: v.string(),
    pattern: v.optional(v.string()),
    enabled: v.boolean(),
  },
  handler: async (ctx, args) => {
    // For simplicity, just insert a new record
    return await ctx.db.insert("sites", { ...args, lastRunAt: Date.now() });
  },
});

export const updateSiteEnabled = mutation({
  args: {
    id: v.id("sites"),
    enabled: v.boolean(),
  },
  handler: async (ctx, args) => {
    await ctx.db.patch(args.id, { enabled: args.enabled });
    return args.id;
  },
});

// Test helper: insert a canned site without args for CLI testing
export const insertTestSiteNoArgs = mutation({
  args: {},
  handler: async (ctx) => {
    return await ctx.db.insert("sites", {
      name: "Test Site",
      url: "https://example.com/jobs",
      pattern: "https://example.com/jobs/**",
      enabled: true,
      lastRunAt: Date.now(),
    });
  },
});

// Test helper: insert a dummy scrape row
export const insertDummyScrape = mutation({
  args: {},
  handler: async (ctx) => {
    const now = Date.now();
    return await ctx.db.insert("scrapes", {
      sourceUrl: "https://example.com/jobs",
      pattern: "https://example.com/jobs/**",
      startedAt: now,
      completedAt: now,
      items: { results: { hits: ["https://example.com/jobs"], items: [{ job_title: "N/A" }] } },
    });
  },
});

export const insertJobRecord = mutation({
  args: {
    title: v.string(),
    company: v.string(),
    description: v.string(),
    location: v.string(),
    remote: v.boolean(),
    level: v.union(v.literal("junior"), v.literal("mid"), v.literal("senior"), v.literal("staff")),
    totalCompensation: v.number(),
    url: v.string(),
    test: v.optional(v.boolean()),
  },
  handler: async (ctx, args) => {
    const jobId = await ctx.db.insert("jobs", {
      ...args,
      postedAt: Date.now(),
    });
    return jobId;
  },
});

/**
 * API endpoint for storing raw scrape results
 *
 * POST /api/scrapes
 * Content-Type: application/json
 * Body: { sourceUrl: string, pattern?: string, items: any, startedAt?: number, completedAt?: number }
 */
http.route({
  path: "/api/scrapes",
  method: "POST",
  handler: httpAction(async (ctx, request) => {
    try {
      const body = await request.json();
      const now = Date.now();
      const scrapeId = await ctx.runMutation(api.router.insertScrapeRecord, {
        sourceUrl: body.sourceUrl,
        pattern: body.pattern ?? undefined,
        startedAt: body.startedAt ?? now,
        completedAt: body.completedAt ?? now,
        items: body.items,
      });
      return new Response(
        JSON.stringify({ success: true, scrapeId }),
        { status: 201, headers: { "Content-Type": "application/json" } }
      );
    } catch (error) {
      return new Response(
        JSON.stringify({ error: "Invalid JSON body" }),
        { status: 400, headers: { "Content-Type": "application/json" } }
      );
    }
  }),
});

/**
 * API endpoint to store a user's resume
 *
 * POST /api/resume
 * Body: resume object
 */
http.route({
  path: "/api/resume",
  method: "POST",
  handler: httpAction(async (ctx, request) => {
    const resume = await request.json();
    await ctx.runMutation(api.formFiller.storeResume, { resume });
    return new Response(JSON.stringify({ success: true }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  }),
});

/**
 * API endpoint to queue a job application for form filling
 *
 * POST /api/form-fill/queue
 * Body: { jobUrl: string }
 */
http.route({
  path: "/api/form-fill/queue",
  method: "POST",
  handler: httpAction(async (ctx, request) => {
    const body = await request.json();
    await ctx.runMutation(api.formFiller.queueApplication, { jobUrl: body.jobUrl });
    return new Response(JSON.stringify({ success: true }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  }),
});

/**
 * API endpoint to fetch the next queued job application
 *
 * GET /api/form-fill/next
 */
http.route({
  path: "/api/form-fill/next",
  method: "GET",
  handler: httpAction(async (ctx) => {
    const next = await ctx.runQuery(api.formFiller.nextApplication, {});
    return new Response(JSON.stringify(next), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  }),
});

export const insertScrapeRecord = mutation({
  args: {
    sourceUrl: v.string(),
    pattern: v.optional(v.string()),
    startedAt: v.number(),
    completedAt: v.number(),
    items: v.any(),
  },
  handler: async (ctx, args) => {
    const id = await ctx.db.insert("scrapes", args);
    return id;
  },
});

export default http;
