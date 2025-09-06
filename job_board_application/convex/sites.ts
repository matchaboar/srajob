import { query, mutation } from "./_generated/server";
import { v } from "convex/values";

export const listSuccessfulSites = query({
  args: { limit: v.optional(v.number()) },
  returns: v.array(
    v.object({
      _id: v.id("sites"),
      name: v.optional(v.string()),
      url: v.string(),
      pattern: v.optional(v.string()),
      lastRunAt: v.optional(v.number()),
    })
  ),
  handler: async (ctx, args) => {
    const limit = args.limit ?? 50;
    const sites = await ctx.db.query("sites").collect();
    const completed = (sites as any[])
      .filter((s) => s.completed === true)
      .sort((a, b) => (b.lastRunAt ?? 0) - (a.lastRunAt ?? 0))
      .slice(0, limit)
      .map((s) => ({
        _id: s._id,
        name: s.name,
        url: s.url,
        pattern: s.pattern,
        lastRunAt: s.lastRunAt,
      }));
    return completed;
  },
});

export const listFailedSites = query({
  args: { limit: v.optional(v.number()) },
  returns: v.array(
    v.object({
      _id: v.id("sites"),
      name: v.optional(v.string()),
      url: v.string(),
      pattern: v.optional(v.string()),
      lastFailureAt: v.optional(v.number()),
      failCount: v.optional(v.number()),
      lastError: v.optional(v.string()),
    })
  ),
  handler: async (ctx, args) => {
    const limit = args.limit ?? 50;
    const sites = await ctx.db.query("sites").collect();
    const failed = (sites as any[])
      .filter((s) => s.failed === true && s.completed !== true)
      .sort((a, b) => (b.lastFailureAt ?? 0) - (a.lastFailureAt ?? 0))
      .slice(0, limit)
      .map((s) => ({
        _id: s._id,
        name: s.name,
        url: s.url,
        pattern: s.pattern,
        lastFailureAt: s.lastFailureAt,
        failCount: s.failCount,
        lastError: s.lastError,
      }));
    return failed;
  },
});

export const retrySite = mutation({
  args: { id: v.id("sites"), clearError: v.optional(v.boolean()) },
  returns: v.object({ success: v.boolean() }),
  handler: async (ctx, args) => {
    const patch: any = {
      completed: false,
      failed: false,
      lockedBy: "",
      lockExpiresAt: 0,
      lastRunAt: 0,
    };
    if (args.clearError !== false) {
      patch.lastError = undefined;
      patch.lastFailureAt = undefined;
      // keep failCount to preserve history
    }
    await ctx.db.patch(args.id, patch);
    return { success: true };
  },
});

export const getScrapeHistoryForUrls = query({
  args: {
    urls: v.array(v.string()),
    limit: v.optional(v.number()),
  },
  returns: v.array(
    v.object({
      sourceUrl: v.string(),
      entries: v.array(
        v.object({
          _id: v.id("scrapes"),
          startedAt: v.number(),
          completedAt: v.number(),
        })
      ),
    })
  ),
  handler: async (ctx, args) => {
    const lim = args.limit ?? 3;
    const out: { sourceUrl: string; entries: { _id: any; startedAt: number; completedAt: number }[] }[] = [];
    for (const url of args.urls) {
      const list = await ctx.db
        .query("scrapes")
        .withIndex("by_source", (q) => q.eq("sourceUrl", url))
        .collect();
      const entries = (list as any[])
        .sort((a, b) => (b.completedAt ?? 0) - (a.completedAt ?? 0))
        .slice(0, lim)
        .map((s) => ({ _id: s._id, startedAt: s.startedAt, completedAt: s.completedAt }));
      out.push({ sourceUrl: url, entries });
    }
    return out;
  },
});
