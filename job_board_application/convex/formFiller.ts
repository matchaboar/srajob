import { mutation, query } from "./_generated/server";
import { v } from "convex/values";
import { getAuthUserId } from "@convex-dev/auth/server";

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
  args: { jobUrl: v.string() },
  returns: v.null(),
  handler: async (ctx, args) => {
    const userId = await getAuthUserId(ctx);
    if (!userId) {
      throw new Error("Not authenticated");
    }

    await ctx.db.insert("form_fill_queue", {
      userId,
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
