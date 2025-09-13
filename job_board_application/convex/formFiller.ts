import { mutation, query } from "./_generated/server";
import { v } from "convex/values";
import { getAuthUserId } from "@convex-dev/auth/server";
import type { Id } from "./_generated/dataModel";

export const storeResume = mutation({
  args: { resume: v.any() },
  returns: v.null(),
  handler: async (ctx, args) => {
    const userId = await getAuthUserId(ctx);
    if (!userId) {
      throw new Error("Not authenticated");
    }

    const existing = await ctx.db
      .query("resumes")
      .withIndex("by_user", (q) => q.eq("userId", userId))
      .unique();

    if (existing) {
      await ctx.db.patch(existing._id, { data: args.resume });
    } else {
      await ctx.db.insert("resumes", { userId, data: args.resume });
    }
    return null;
  },
});

export const queueApplication = mutation({
  args: { jobId: v.id("jobs"), jobUrl: v.string() },
  returns: v.null(),
  handler: async (ctx, args) => {
    const userId = await getAuthUserId(ctx);
    if (!userId) {
      throw new Error("Not authenticated");
    }

    await ctx.db.insert("form_fill_queue", {
      userId,
      jobId: args.jobId,
      jobUrl: args.jobUrl,
      status: "pending",
      queuedAt: Date.now(),
    });
    return null;
  },
});

export const nextApplication = query({
  args: {},
  returns: v.union(
    v.null(),
    v.object({ _id: v.id("form_fill_queue"), jobUrl: v.string() })
  ),
  handler: async (ctx) => {
    const userId = await getAuthUserId(ctx);
    if (!userId) {
      throw new Error("Not authenticated");
    }

    const next = await ctx.db
      .query("form_fill_queue")
      .withIndex("by_user", (q) => q.eq("userId", userId))
      .filter((q) => q.eq(q.field("status"), "pending"))
      .order("asc")
      .first();

    if (!next) {
      return null;
    }

    return { _id: next._id, jobUrl: next.jobUrl };
  },
});

// List a user's AI applications with job info and status
export const listUserAIApplications = query({
  args: {
    status: v.optional(
      v.union(v.literal("pending"), v.literal("running"), v.literal("completed"), v.literal("error"))
    ),
  },
  returns: v.any(),
  handler: async (ctx, args) => {
    const userId = await getAuthUserId(ctx);
    if (!userId) throw new Error("Not authenticated");

    let q = ctx.db.query("form_fill_queue").withIndex("by_user", (q) => q.eq("userId", userId));
    if (args.status) {
      // Filter in memory since index is by_user; small per-user set
      const items = await q.collect();
      const filtered = items.filter((i: any) => i.status === args.status);
      const enriched = await Promise.all(
        filtered.map(async (i: any) => ({
          ...i,
          job: await ctx.db.get(i.jobId as Id<"jobs">),
        }))
      );
      // Latest first
      return enriched.sort((a: any, b: any) => (b.queuedAt || 0) - (a.queuedAt || 0));
    }
    const items = await q.collect();
    const enriched = await Promise.all(
      items.map(async (i: any) => ({
        ...i,
        job: await ctx.db.get(i.jobId as Id<"jobs">),
      }))
    );
    return enriched.sort((a: any, b: any) => (b.queuedAt || 0) - (a.queuedAt || 0));
  },
});

// System-only: lease the next pending item (atomically set to running)
export const leaseNextPending = mutation({
  args: {},
  returns: v.union(
    v.null(),
    v.object({
      _id: v.id("form_fill_queue"),
      userId: v.id("users"),
      jobId: v.id("jobs"),
      jobUrl: v.string(),
      queuedAt: v.number(),
      startedAt: v.optional(v.number()),
    })
  ),
  handler: async (ctx) => {
    // Opportunistically recover stale running items so queues don't get stuck
    try {
      const ttlMs = 15_000; // consider "running" stale after 15s in dev
      const cutoff = Date.now() - ttlMs;
      const running = await ctx.db
        .query("form_fill_queue")
        .withIndex("by_status", (q) => q.eq("status", "running"))
        .collect();
      for (const i of running) {
        const started = (i as any).startedAt ?? 0;
        if (started < cutoff) {
          await ctx.db.patch(i._id, { status: "pending", startedAt: undefined });
        }
      }
    } catch (e) {
      // best-effort; continue to lease
    }

    // Oldest pending first
    const next = await ctx.db
      .query("form_fill_queue")
      .withIndex("by_status", (q) => q.eq("status", "pending"))
      .order("asc")
      .first();
    if (!next) return null;
    await ctx.db.patch(next._id, { status: "running", startedAt: Date.now() });
    return {
      _id: next._id,
      userId: next.userId as Id<"users">,
      jobId: next.jobId as Id<"jobs">,
      jobUrl: next.jobUrl,
      queuedAt: next.queuedAt,
      startedAt: Date.now(),
    };
  },
});

export const completeJob = mutation({
  args: {
    id: v.id("form_fill_queue"),
    filledData: v.optional(v.any()),
    logs: v.optional(
      v.object({
        fieldsYaml: v.optional(v.string()),
        fillLogYaml: v.optional(v.string()),
        screenshot: v.optional(v.string()),
      })
    ),
  },
  returns: v.null(),
  handler: async (ctx, args) => {
    await ctx.db.patch(args.id, {
      status: "completed",
      completedAt: Date.now(),
      filledData: args.filledData ?? null,
      logs: args.logs ?? undefined,
      error: undefined,
    });
    return null;
  },
});

export const failJob = mutation({
  args: { id: v.id("form_fill_queue"), error: v.string() },
  returns: v.null(),
  handler: async (ctx, args) => {
    await ctx.db.patch(args.id, { status: "error", error: args.error, completedAt: Date.now() });
    return null;
  },
});

export const getResumeByUser = query({
  args: { userId: v.id("users") },
  returns: v.union(v.null(), v.any()),
  handler: async (ctx, args) => {
    const existing = await ctx.db
      .query("resumes")
      .withIndex("by_user", (q) => q.eq("userId", args.userId))
      .unique();
    return existing?.data ?? null;
  },
});

// System-only: reset stale running items back to pending after a timeout
export const resetStaleRunning = mutation({
  args: { maxAgeSeconds: v.optional(v.number()) },
  returns: v.object({ reset: v.number() }),
  handler: async (ctx, args) => {
    const maxAgeMs = Math.max(10_000, Math.floor((args.maxAgeSeconds ?? 300) * 1000));
    const cutoff = Date.now() - maxAgeMs;
    const running = await ctx.db
      .query("form_fill_queue")
      .withIndex("by_status", (q) => q.eq("status", "running"))
      .collect();
    let reset = 0;
    for (const i of running) {
      const started = (i as any).startedAt ?? 0;
      if (started < cutoff) {
        await ctx.db.patch(i._id, { status: "pending", startedAt: undefined });
        reset++;
      }
    }
    return { reset };
  },
});

// System mutation: queue recent jobs for a specific user
export const queueJobsForUser = mutation({
  args: {
    userId: v.id("users"),
    limit: v.optional(v.number()),
    onlyUnqueued: v.optional(v.boolean()),
  },
  returns: v.object({ inserted: v.number() }),
  handler: async (ctx, args) => {
    const limit = Math.max(1, Math.min(100, args.limit ?? 10));
    const onlyUnqueued = args.onlyUnqueued ?? true;

    // Collect queued/applications for this user to avoid duplicates
    const queueItems = await ctx.db
      .query("form_fill_queue")
      .withIndex("by_user", (q) => q.eq("userId", args.userId))
      .collect();
    const queued = new Set(queueItems.map((i: any) => i.jobId));

    const apps = await ctx.db
      .query("applications")
      .withIndex("by_user", (q) => q.eq("userId", args.userId))
      .collect();
    const applied = new Set(apps.map((a: any) => a.jobId));

    // Pull recent jobs and filter
    const jobs = await ctx.db
      .query("jobs")
      .withIndex("by_posted_at")
      .order("desc")
      .collect();

    const candidates = jobs
      .filter((j: any) => j && j.url)
      .filter((j: any) => j.test !== true)
      .filter((j: any) => !applied.has(j._id))
      .filter((j: any) => (onlyUnqueued ? !queued.has(j._id) : true))
      .slice(0, limit);

    let inserted = 0;
    for (const j of candidates) {
      await ctx.db.insert("form_fill_queue", {
        userId: args.userId,
        jobId: j._id,
        jobUrl: j.url,
        status: "pending",
        queuedAt: Date.now(),
      });
      inserted++;
    }
    return { inserted };
  },
});

// Allow user to retry a specific queued item (from error or running back to pending)
export const retryQueueItem = mutation({
  args: { id: v.id("form_fill_queue") },
  returns: v.null(),
  handler: async (ctx, args) => {
    await ctx.db.patch(args.id, {
      status: "pending",
      error: undefined,
      startedAt: undefined,
      queuedAt: Date.now(),
    });
    return null;
  },
});
