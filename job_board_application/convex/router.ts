import { httpRouter } from "convex/server";
import { httpAction, mutation, query } from "./_generated/server";
import { v } from "convex/values";
import { api } from "./_generated/api";

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
