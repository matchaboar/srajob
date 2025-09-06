import { query, mutation } from "./_generated/server";
import { v } from "convex/values";
import { getAuthUserId } from "@convex-dev/auth/server";
import { paginationOptsValidator } from "convex/server";

export const listJobs = query({
  args: {
    paginationOpts: paginationOptsValidator,
    search: v.optional(v.string()),
    remote: v.optional(v.boolean()),
    level: v.optional(v.union(v.literal("junior"), v.literal("mid"), v.literal("senior"), v.literal("staff"))),
    minCompensation: v.optional(v.number()),
    maxCompensation: v.optional(v.number()),
  },
  handler: async (ctx, args) => {
    const userId = await getAuthUserId(ctx);
    if (!userId) {
      throw new Error("Not authenticated");
    }

    // Get user's applied/rejected jobs first
    const userApplications = await ctx.db
      .query("applications")
      .withIndex("by_user", (q) => q.eq("userId", userId))
      .collect();

    const appliedJobIds = new Set(userApplications.map(app => app.jobId));

    // Apply search and filters
    let jobs;
    if (args.search) {
      jobs = await ctx.db
        .query("jobs")
        .withSearchIndex("search_title", (q) => {
          let searchQuery = q.search("title", args.search!);
          if (args.remote !== undefined) {
            searchQuery = searchQuery.eq("remote", args.remote);
          }
          if (args.level) {
            searchQuery = searchQuery.eq("level", args.level);
          }
          return searchQuery;
        })
        .paginate(args.paginationOpts);
    } else {
      jobs = await ctx.db
        .query("jobs")
        .withIndex("by_posted_at")
        .order("desc")
        .paginate(args.paginationOpts);
    }

    // Filter out applied/rejected jobs and apply compensation filters
    let filteredJobs = jobs.page.filter((job: any) => {
      // Remove jobs user has already applied to or rejected
      if (appliedJobIds.has(job._id)) {
        return false;
      }
      
      // Apply compensation filters
      if (args.minCompensation !== undefined && job.totalCompensation < args.minCompensation) {
        return false;
      }
      if (args.maxCompensation !== undefined && job.totalCompensation > args.maxCompensation) {
        return false;
      }
      return true;
    });

    // Get application counts for remaining jobs
    const jobsWithData = await Promise.all(
      filteredJobs.map(async (job: any) => {
        const applicationCount = await ctx.db
          .query("applications")
          .withIndex("by_job", (q) => q.eq("jobId", job._id))
          .filter((q) => q.eq(q.field("status"), "applied"))
          .collect();

        return {
          ...job,
          applicationCount: applicationCount.length,
          userStatus: null, // These jobs don't have user applications by definition
        };
      })
    );

    return {
      page: jobsWithData,
      isDone: jobs.isDone,
      continueCursor: jobs.continueCursor,
    };
  },
});

export const applyToJob = mutation({
  args: {
    jobId: v.id("jobs"),
    type: v.union(v.literal("ai"), v.literal("manual")),
  },
  handler: async (ctx, args) => {
    const userId = await getAuthUserId(ctx);
    if (!userId) {
      throw new Error("Not authenticated");
    }

    // Check if user already applied or rejected this job
    const existingApplication = await ctx.db
      .query("applications")
      .withIndex("by_user_and_job", (q) => q.eq("userId", userId).eq("jobId", args.jobId))
      .unique();

    if (existingApplication) {
      throw new Error("Already applied to this job");
    }

    await ctx.db.insert("applications", {
      userId,
      jobId: args.jobId,
      status: "applied",
      appliedAt: Date.now(),
    });

    return { success: true };
  },
});

export const rejectJob = mutation({
  args: {
    jobId: v.id("jobs"),
  },
  handler: async (ctx, args) => {
    const userId = await getAuthUserId(ctx);
    if (!userId) {
      throw new Error("Not authenticated");
    }

    // Check if user already has an application for this job
    const existingApplication = await ctx.db
      .query("applications")
      .withIndex("by_user_and_job", (q) => q.eq("userId", userId).eq("jobId", args.jobId))
      .unique();

    if (existingApplication) {
      await ctx.db.patch(existingApplication._id, { status: "rejected" });
    } else {
      await ctx.db.insert("applications", {
        userId,
        jobId: args.jobId,
        status: "rejected",
        appliedAt: Date.now(),
      });
    }

    return { success: true };
  },
});

export const getRecentJobs = query({
  args: {},
  handler: async (ctx) => {
    // This query will automatically update when new jobs are inserted
    // because Convex queries are reactive by default
    const jobs = await ctx.db
      .query("jobs")
      .withIndex("by_posted_at")
      .order("desc")
      .take(20); // Increased from 10 to show more recent jobs

    return jobs;
  },
});

export const getAppliedJobs = query({
  args: {},
  handler: async (ctx) => {
    const userId = await getAuthUserId(ctx);
    if (!userId) {
      throw new Error("Not authenticated");
    }

    const applications = await ctx.db
      .query("applications")
      .withIndex("by_user", (q) => q.eq("userId", userId))
      .filter((q) => q.eq(q.field("status"), "applied"))
      .collect();

    const appliedJobs = await Promise.all(
      applications.map(async (application) => {
        const job = await ctx.db.get(application.jobId);
        if (!job) return null;
        
        return {
          ...job,
          appliedAt: application.appliedAt,
          userStatus: application.status,
        };
      })
    );

    return appliedJobs
      .filter((job) => job !== null)
      .sort((a, b) => b.appliedAt - a.appliedAt);
  },
});

export const checkIfJobsExist = query({
  args: {},
  handler: async (ctx) => {
    const jobs = await ctx.db.query("jobs").take(1);
    return jobs.length > 0;
  },
});

export const withdrawApplication = mutation({
  args: {
    jobId: v.id("jobs"),
  },
  handler: async (ctx, args) => {
    const userId = await getAuthUserId(ctx);
    if (!userId) {
      throw new Error("Not authenticated");
    }

    const existingApplication = await ctx.db
      .query("applications")
      .withIndex("by_user_and_job", (q) => q.eq("userId", userId).eq("jobId", args.jobId))
      .unique();

    if (!existingApplication) {
      throw new Error("Application not found");
    }
    if (existingApplication.status !== "applied") {
      throw new Error("No active application to withdraw");
    }

    await ctx.db.delete(existingApplication._id);
    return { success: true };
  },
});

export const normalizeDevTestJobs = mutation({
  args: {},
  handler: async (ctx) => {
    const jobs = await ctx.db.query("jobs").collect();
    const needsFix = jobs.filter((j: any) => {
      const tooShort = (s: any) => typeof s === "string" && s.trim().length <= 2;
      return (
        (j.title && (j.title.startsWith("HC-") || tooShort(j.title))) ||
        tooShort(j.company) ||
        tooShort(j.location) ||
        tooShort(j.description) ||
        (typeof j.totalCompensation === "number" && j.totalCompensation <= 10) ||
        j.company === "Health Co"
      );
    });

    const titles = [
      "Software Engineer",
      "Frontend Developer",
      "Backend Engineer",
      "Full Stack Developer",
      "Data Engineer",
    ];
    const companies = ["Acme Corp", "SampleSoft", "Initech", "Globex", "Umbrella Labs"];
    const locations = ["Remote - US", "San Francisco, CA", "New York, NY", "Austin, TX", "Seattle, WA"];

    let updates = 0;
    for (const j of needsFix) {
      const pick = (arr: string[]) => arr[Math.floor(Math.random() * arr.length)];
      const comp = 100000 + Math.floor(Math.random() * 90000);
      await ctx.db.patch(j._id, {
        title: pick(titles),
        company: pick(companies),
        location: pick(locations),
        description:
          "This is a realistic sample listing used for development. Replace with real scraped data in production.",
        totalCompensation: comp,
        remote: j.location?.toLowerCase().includes("remote") ?? true,
      });
      updates++;
    }
    return { success: true, updated: updates };
  },
});

export const deleteJob = mutation({
  args: {
    jobId: v.id("jobs"),
  },
  handler: async (ctx, args) => {
    await ctx.db.delete(args.jobId);
    return { success: true };
  },
});
