import { defineSchema, defineTable } from "convex/server";
import { v } from "convex/values";
import { authTables } from "@convex-dev/auth/server";

const applicationTables = {
  jobs: defineTable({
    title: v.string(),
    company: v.string(),
    description: v.string(),
    location: v.string(),
    remote: v.boolean(),
    level: v.union(v.literal("junior"), v.literal("mid"), v.literal("senior"), v.literal("staff")),
    totalCompensation: v.number(),
    url: v.string(),
    postedAt: v.number(),
    // Optional flag to identify internal/test rows not meant for UI
    test: v.optional(v.boolean()),
  })
    .index("by_posted_at", ["postedAt"])
    .searchIndex("search_title", {
      searchField: "title",
      filterFields: ["remote", "level"],
    }),

  applications: defineTable({
    userId: v.id("users"),
    jobId: v.id("jobs"),
    status: v.union(v.literal("applied"), v.literal("rejected")),
    appliedAt: v.number(),
  })
    .index("by_user", ["userId"])
    .index("by_job", ["jobId"])
    .index("by_user_and_job", ["userId", "jobId"]),
  
  // List of websites to scrape for jobs
  sites: defineTable({
    name: v.optional(v.string()),
    url: v.string(),
    // Optional pattern for detail pages (e.g., "https://example.com/jobs/**")
    pattern: v.optional(v.string()),
    enabled: v.boolean(),
    // Optional timestamp of the last successful run
    lastRunAt: v.optional(v.number()),
    // Simple cooperative locking for scraper workers
    lockedBy: v.optional(v.string()),
    lockExpiresAt: v.optional(v.number()),
    // Optional completion flag if treating a site as a one-off job
    completed: v.optional(v.boolean()),
    // If true, site is in a failed state and excluded from auto-leasing until manually retried
    failed: v.optional(v.boolean()),
    // Failure tracking so stuck jobs get retried and diagnosable
    failCount: v.optional(v.number()),
    lastFailureAt: v.optional(v.number()),
    lastError: v.optional(v.string()),
  })
    .index("by_enabled", ["enabled"]),

  // Raw scrape results captured by the scraper
  scrapes: defineTable({
    sourceUrl: v.string(),
    pattern: v.optional(v.string()),
    startedAt: v.number(),
    completedAt: v.number(),
    items: v.any(),
  }).index("by_source", ["sourceUrl"]),

  resumes: defineTable({
    userId: v.id("users"),
    data: v.any(),
  }).index("by_user", ["userId"]),

  form_fill_queue: defineTable({
    userId: v.id("users"),
    jobUrl: v.string(),
    status: v.union(v.literal("pending"), v.literal("completed")),
    queuedAt: v.number(),
  }).index("by_user", ["userId"]),
};

export default defineSchema({
  ...authTables,
  ...applicationTables,
});
