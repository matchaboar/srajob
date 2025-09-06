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
};

export default defineSchema({
  ...authTables,
  ...applicationTables,
});
