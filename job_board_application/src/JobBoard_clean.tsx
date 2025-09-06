import { useState, useEffect, useRef } from "react";
import { usePaginatedQuery, useMutation, useQuery } from "convex/react";
import { api } from "../convex/_generated/api";
import { toast } from "sonner";

type Level = "junior" | "mid" | "senior" | "staff";

interface Filters {
  search: string;
  remote: boolean | null;
  level: Level | null;
  minCompensation: number | null;
  maxCompensation: number | null;
}

export function JobBoard() {
  const [activeTab, setActiveTab] = useState<"jobs" | "applied" | "live">("jobs");
  const [filters, setFilters] = useState<Filters>({
    search: "",
    remote: null,
    level: null,
    minCompensation: null,
    maxCompensation: null,
  });

  // Track applied/rejected jobs locally for immediate UI updates
  const [locallyAppliedJobs, setLocallyAppliedJobs] = useState<Set<string>>(new Set());

  // Live Feed: animation + sound state
  const [liveMuted, setLiveMuted] = useState<boolean>(() => {
    if (typeof window === "undefined") return true;
    try {
      const stored = localStorage.getItem("liveFeedMuted");
      return stored ? stored === "true" : true; // default muted
    } catch {
      return true;
    }
  });
  const audioCtxRef = useRef<AudioContext | null>(null);
  const seenLiveJobIdsRef = useRef<Set<string>>(new Set());
  const initialLiveLoadRef = useRef<boolean>(false);
  const [animatedLiveJobIds, setAnimatedLiveJobIds] = useState<Set<string>>(new Set());

  const { results, status, loadMore } = usePaginatedQuery(
    api.jobs.listJobs,
    {
      search: filters.search || undefined,
      remote: filters.remote ?? undefined,
      level: filters.level ?? undefined,
      minCompensation: filters.minCompensation ?? undefined,
      maxCompensation: filters.maxCompensation ?? undefined,
    },
    { initialNumItems: 20 }
  );

  const recentJobs = useQuery(api.jobs.getRecentJobs);
  const appliedJobs = useQuery(api.jobs.getAppliedJobs);
  const applyToJob = useMutation(api.jobs.applyToJob);
  const rejectJob = useMutation(api.jobs.rejectJob);

  const handleApply = async (jobId: string, type: "ai" | "manual", url: string) => {
    try {
      // Immediately update local state to remove the job from UI
      setLocallyAppliedJobs(prev => new Set([...prev, jobId]));
      
      await applyToJob({ jobId: jobId as any, type });
      toast.success(`Applied to job successfully!`);
      
      // Open the appropriate link
      if (type === "manual") {
        window.open(url, "_blank");
      } else {
        // AI Apply placeholder - would integrate with AI application system
        toast.info("AI application feature coming soon!");
      }
    } catch (error) {
      // Revert local state if the mutation failed
      setLocallyAppliedJobs(prev => {
        const newSet = new Set(prev);
        newSet.delete(jobId);
        return newSet;
      });
      toast.error("Failed to apply to job");
    }
  };

  const handleReject = async (jobId: string) => {
    try {
      // Immediately update local state to remove the job from UI
      setLocallyAppliedJobs(prev => new Set([...prev, jobId]));
      
      await rejectJob({ jobId: jobId as any });
      toast.success("Job rejected");
    } catch (error) {
      // Revert local state if the mutation failed
      setLocallyAppliedJobs(prev => {
        const newSet = new Set(prev);
        newSet.delete(jobId);
        return newSet;
      });
      toast.error("Failed to reject job");
    }
  };

  // Web Audio helpers for a subtle "ding"
  const ensureAudioContext = async (): Promise<AudioContext | null> => {
    try {
      const Ctx = (window as any).AudioContext || (window as any).webkitAudioContext;
      if (!Ctx) return null;
      if (!audioCtxRef.current) {
        audioCtxRef.current = new Ctx();
      }
      if (audioCtxRef.current.state === "suspended") {
        await audioCtxRef.current.resume();
      }
      return audioCtxRef.current;
    } catch {
      return null;
    }
  };

  const playDing = async (delayMs = 0) => {
    if (liveMuted) return;
    const ctx = await ensureAudioContext();
    if (!ctx || ctx.state !== "running") return;

    const startAt = ctx.currentTime + delayMs / 1000;
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();

    osc.type = "sine";
    osc.frequency.setValueAtTime(880, startAt);
    osc.frequency.exponentialRampToValueAtTime(1320, startAt + 0.09);

    gain.gain.setValueAtTime(0.0001, startAt);
    gain.gain.exponentialRampToValueAtTime(0.15, startAt + 0.02);
    gain.gain.exponentialRampToValueAtTime(0.0001, startAt + 0.25);

    osc.connect(gain);
    gain.connect(ctx.destination);

    osc.start(startAt);
    osc.stop(startAt + 0.3);
  };

  const toggleLiveSound = async () => {
    const next = !liveMuted;
    setLiveMuted(next);
    try {
      localStorage.setItem("liveFeedMuted", next ? "true" : "false");
    } catch {}
    if (!next) {
      await ensureAudioContext();
    }
  };

  const formatSalary = (amount: number) => {
    return new Intl.NumberFormat("en-US", {
      style: "currency",
      currency: "USD",
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(amount);
  };

  const clearFilters = () => {
    setFilters({
      search: "",
      remote: null,
      level: null,
      minCompensation: null,
      maxCompensation: null,
    });
  };

  // Filter out locally applied/rejected jobs from the results
  const filteredResults = results?.filter(job => !locallyAppliedJobs.has(job._id)) || [];

  // Live Feed: detect new jobs and trigger animation/sound
  useEffect(() => {
    if (!recentJobs) return;

    const ids = recentJobs.map((j: any) => j._id as string);

    if (!initialLiveLoadRef.current) {
      seenLiveJobIdsRef.current = new Set(ids);
      initialLiveLoadRef.current = true;
      return;
    }

    const newIds = ids.filter((id) => !seenLiveJobIdsRef.current.has(id));
    if (newIds.length === 0) return;

    newIds.forEach((id) => seenLiveJobIdsRef.current.add(id));

    setAnimatedLiveJobIds((prev) => new Set([...Array.from(prev), ...newIds]));

    if (activeTab === "live" && !liveMuted) {
      newIds.forEach((_, i) => {
        playDing(i * 100);
      });
    }
  }, [recentJobs, activeTab, liveMuted]);

  const renderJobCard = (job: any, showApplyButtons = true) => (
    <div key={job._id} className="bg-white p-3 shadow-sm border-b border-gray-200 first:rounded-t-lg last:rounded-b-lg last:border-b-0">
      <div className="flex justify-between items-start">
        <div className="flex-1">
          <div className="flex items-center gap-2 mb-1">
            <h3 className="text-lg font-semibold text-gray-900">{job.title}</h3>
            <span className="px-2 py-0.5 bg-blue-100 text-blue-800 text-xs font-medium rounded-full">
              {job.level}
            </span>
            {job.remote && (
              <span className="px-2 py-0.5 bg-green-100 text-green-800 text-xs font-medium rounded-full">
                Remote
              </span>
            )}
          </div>
          <p className="text-base font-medium text-gray-700 mb-0.5">{job.company}</p>
          <p className="text-sm text-gray-600 mb-1">{job.location}</p>
          <p className="text-sm text-gray-700 mb-2 line-clamp-2">{job.description}</p>
          <div className="flex items-center gap-4 text-xs text-gray-600">
            <span className="font-medium text-green-600">
              {formatSalary(job.totalCompensation)}
            </span>
            <span>{job.applicationCount || 0} applications</span>
            <span>Posted {new Date(job.postedAt).toLocaleDateString()}</span>
            {job.appliedAt && (
              <span className="text-blue-600 font-medium">
                Applied {new Date(job.appliedAt).toLocaleDateString()}
              </span>
            )}
          </div>
        </div>

        <div className="flex flex-col gap-1 ml-4">
          {!showApplyButtons || job.userStatus === "applied" ? (
            <div className="text-center">
              <span className="px-3 py-1.5 bg-gray-100 text-gray-500 rounded-md text-xs">
                Applied
              </span>
            </div>
          ) : (
            <>
              <button
                onClick={() => handleApply(job._id, "ai", job.url)}
                className="px-3 py-1.5 bg-blue-600 text-white rounded-md hover:bg-blue-700 transition-colors text-xs font-medium"
              >
                AI Apply
              </button>
              <button
                onClick={() => handleApply(job._id, "manual", job.url)}
                className="px-3 py-1.5 bg-green-600 text-white rounded-md hover:bg-green-700 transition-colors text-xs font-medium"
              >
                Manual Apply
              </button>
              <button
                onClick={() => handleReject(job._id)}
                className="px-3 py-1.5 bg-gray-200 text-gray-700 rounded-md hover:bg-gray-300 transition-colors text-xs font-medium"
              >
                Reject
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );

  return (
    <div className="max-w-7xl mx-auto p-6">
      {/* Tabs */}
      <div className="flex space-x-1 mb-6 bg-gray-100 p-1 rounded-lg w-fit">
        <button
          onClick={() => setActiveTab("jobs")}
          className={`px-4 py-2 rounded-md font-medium transition-colors ${
            activeTab === "jobs"
              ? "bg-white text-primary shadow-sm"
              : "text-gray-600 hover:text-gray-900"
          }`}
        >
          Job Search
        </button>
        <button
          onClick={() => setActiveTab("applied")}
          className={`px-4 py-2 rounded-md font-medium transition-colors ${
            activeTab === "applied"
              ? "bg-white text-primary shadow-sm"
              : "text-gray-600 hover:text-gray-900"
          }`}
        >
          Applied Jobs {appliedJobs && appliedJobs.length > 0 && (
            <span className="ml-1 px-2 py-0.5 bg-blue-100 text-blue-800 text-xs rounded-full">
              {appliedJobs.length}
            </span>
          )}
        </button>
        <button
          onClick={() => setActiveTab("live")}
          className={`px-4 py-2 rounded-md font-medium transition-colors ${
            activeTab === "live"
              ? "bg-white text-primary shadow-sm"
              : "text-gray-600 hover:text-gray-900"
          }`}
        >
          Live Feed
        </button>
      </div>

      {activeTab === "jobs" ? (
        <>
          {/* Search and Filters */}
          <div className="bg-white p-4 rounded-lg shadow-sm mb-6">
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              {/* First Row */}
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <div className="sm:col-span-2">
                  <input
                    type="text"
                    value={filters.search}
                    onChange={(e) => setFilters({ ...filters, search: e.target.value })}
                    placeholder="Search job titles..."
                    className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
                  />
                </div>

                <select
                  value={filters.remote === null ? "" : filters.remote.toString()}
                  onChange={(e) =>
                    setFilters({
                      ...filters,
                      remote: e.target.value === "" ? null : e.target.value === "true",
                    })
                  }
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
                >
                  <option value="">Any Location</option>
                  <option value="true">Remote</option>
                  <option value="false">On-site</option>
                </select>
              </div>

              {/* Second Row */}
              <div className="grid grid-cols-1 sm:grid-cols-4 gap-3">
                <select
                  value={filters.level || ""}
                  onChange={(e) =>
                    setFilters({
                      ...filters,
                      level: e.target.value === "" ? null : (e.target.value as Level),
                    })
                  }
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
                >
                  <option value="">Any Level</option>
                  <option value="junior">Junior</option>
                  <option value="mid">Mid</option>
                  <option value="senior">Senior</option>
                  <option value="staff">Staff</option>
                </select>

                <input
                  type="number"
                  value={filters.minCompensation || ""}
                  onChange={(e) =>
                    setFilters({
                      ...filters,
                      minCompensation: e.target.value ? parseInt(e.target.value) : null,
                    })
                  }
                  placeholder="Min $"
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
                />

                <input
                  type="number"
                  value={filters.maxCompensation || ""}
                  onChange={(e) =>
                    setFilters({
                      ...filters,
                      maxCompensation: e.target.value ? parseInt(e.target.value) : null,
                    })
                  }
                  placeholder="Max $"
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
                />
                <button
                  onClick={clearFilters}
                  className="px-3 py-2 text-sm text-gray-600 hover:text-gray-900 border border-gray-300 rounded-md hover:bg-gray-50 whitespace-nowrap"
                >
                  Clear
                </button>
              </div>
            </div>
          </div>

          {/* Job Results */}
          <div className="space-y-0">
            {filteredResults.map((job) => renderJobCard(job, true))}

            {status === "LoadingMore" && (
              <div className="flex justify-center py-4">
                <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-600"></div>
              </div>
            )}

            {status === "CanLoadMore" && (
              <div className="flex justify-center py-4">
                <button
                  onClick={() => loadMore(20)}
                  className="px-6 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 transition-colors"
                >
                  Load More Jobs
                </button>
              </div>
            )}

            {filteredResults.length === 0 && (
              <div className="text-center py-12">
                <p className="text-gray-500 text-lg">No jobs found matching your criteria.</p>
              </div>
            )}
          </div>
        </>
      ) : activeTab === "applied" ? (
        /* Applied Jobs Tab */
        <div className="bg-white rounded-lg shadow-sm">
          <div className="p-4 border-b">
            <h2 className="text-xl font-semibold text-gray-900">Applied Jobs</h2>
            <p className="text-gray-600 mt-1">Jobs you have applied to</p>
          </div>
          <div className="space-y-0">
            {appliedJobs && appliedJobs.length > 0 ? (
              appliedJobs.map((job) => renderJobCard(job, false))
            ) : (
              <div className="p-8 text-center">
                <p className="text-gray-500">You haven't applied to any jobs yet.</p>
                <button
                  onClick={() => setActiveTab("jobs")}
                  className="mt-4 px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 transition-colors"
                >
                  Browse Jobs
                </button>
              </div>
            )}
          </div>
        </div>
      ) : (
        /* Live Feed Tab */
        <div className="bg-white rounded-lg shadow-sm">
          <div className="p-4 border-b flex items-center justify-between">
            <div>
              <h2 className="text-xl font-semibold text-gray-900">Latest Jobs</h2>
              <p className="text-gray-600 mt-1">Real-time feed of newly posted jobs</p>
            </div>
            <button
              onClick={toggleLiveSound}
              className="px-3 py-1.5 text-xs rounded-md border border-gray-300 hover:bg-gray-50"
              title={liveMuted ? "Unmute notifications" : "Mute notifications"}
            >
              {liveMuted ? "🔕 Unmute" : "🔔 Mute"}
            </button>
          </div>
          <div className="divide-y">
            {recentJobs?.map((job) => (
              <div
                key={job._id}
                className={`px-3 py-2 hover:bg-gray-50 ${
                  animatedLiveJobIds.has(job._id) ? "live-job-enter" : ""
                }`}
              >
                <div className="flex justify-between items-start">
                  <div>
                    <div className="flex items-center gap-2 mb-1">
                      <h3 className="text-base font-semibold text-gray-900">{job.title}</h3>
                      <span className="px-2 py-0.5 bg-blue-100 text-blue-800 text-xs font-medium rounded-full">
                        {job.level}
                      </span>
                      {job.remote && (
                        <span className="px-2 py-0.5 bg-green-100 text-green-800 text-xs font-medium rounded-full">
                          Remote
                        </span>
                      )}
                    </div>
                    <p className="text-sm text-gray-700 font-medium">{job.company}</p>
                    <p className="text-sm text-gray-600">{job.location}</p>
                    <p className="text-green-600 font-medium text-sm mt-0.5">
                      {formatSalary(job.totalCompensation)}
                    </p>
                  </div>
                  <div className="text-right">
                    <p className="text-xs text-gray-500">
                      {new Date(job.postedAt).toLocaleString()}
                    </p>
                    <button
                      onClick={() => setActiveTab("jobs")}
                      className="mt-1 px-2 py-1 text-xs bg-blue-600 text-white rounded hover:bg-blue-700 transition-colors"
                    >
                      View Details
                    </button>
                  </div>
                </div>
              </div>
            ))}
            {recentJobs?.length === 0 && (
              <div className="p-8 text-center">
                <p className="text-gray-500">No recent jobs available.</p>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
