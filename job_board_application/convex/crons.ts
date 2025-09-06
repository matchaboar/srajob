import { cronJobs } from "convex/server";
import { internal } from "./_generated/api";
import { internalMutation } from "./_generated/server";

// Clear expired locks so stuck rows recover even if workers die without reporting failure.
export const clearExpiredSiteLocks = internalMutation({
  args: {},
  handler: async (ctx) => {
    const now = Date.now();
    const sites = await ctx.db.query("sites").collect();
    let cleared = 0;
    for (const s of sites as any[]) {
      if (s.lockExpiresAt && s.lockExpiresAt <= now && s.lockedBy) {
        await ctx.db.patch(s._id, { lockedBy: "", lockExpiresAt: 0 });
        cleared++;
      }
    }
    return { cleared };
  },
});

const crons = cronJobs();

// Every 2 minutes, clean expired locks
crons.interval(
  "clearExpiredSiteLocks",
  { minutes: 2 },
  internal.crons.clearExpiredSiteLocks,
);

export default crons;

