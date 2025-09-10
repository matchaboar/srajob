import { useState, useEffect, useRef } from "react";
import { usePaginatedQuery, useMutation, useQuery } from "convex/react";
import { api } from "../convex/_generated/api";
import { toast } from "sonner";
import { motion, AnimatePresence, LayoutGroup } from "framer-motion";
import ResumeEditor from "./components/ResumeEditor";
import DataDrawer from "./components/DataDrawer";

type Level = "junior" | "mid" | "senior" | "staff";

interface Filters {
  search: string;
  remote: boolean | null;
  level: Level | null;
  minCompensation: number | null;
  maxCompensation: number | null;
}

export function JobBoard() {
  const [activeTab, setActiveTab] = useState<"jobs" | "applied" | "ai" | "live">("jobs");
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
      return stored ? stored === "true" : true; // default muted to satisfy autoplay
    } catch {
      return true;
    }
  });
  const audioCtxRef = useRef<AudioContext | null>(null);
  const seenLiveJobIdsRef = useRef<Set<string>>(new Set());
  const initialLiveLoadRef = useRef<boolean>(false);
  const [animatedLiveJobIds, setAnimatedLiveJobIds] = useState<Set<string>>(new Set());

  // Track jobs that are exiting with animation
  const [exitingJobs, setExitingJobs] = useState<Record<string, "apply" | "reject">>({});
  // Track withdrawn applications locally to instantly hide from Applied tab
  const [locallyWithdrawnJobs, setLocallyWithdrawnJobs] = useState<Set<string>>(new Set());

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
  const aiApplications = useQuery((api as any).formFiller.listUserAIApplications, {} as any);
  const applyToJob = useMutation(api.jobs.applyToJob);
  const queueAIApplication = useMutation((api as any).formFiller.queueApplication);
  const rejectJob = useMutation(api.jobs.rejectJob);
  const withdrawApplication = useMutation(api.jobs.withdrawApplication);

  const handleApply = async (jobId: string, type: "ai" | "manual", url: string) => {
    try {
      // Ignore if already animating
      if (exitingJobs[jobId]) return;

      if (type === "manual") {
        // Mark as exiting with apply animation
        setExitingJobs(prev => ({ ...prev, [jobId]: "apply" }));
        // Wait for slide animation to complete, then remove from list
        setTimeout(() => {
          setLocallyAppliedJobs(prev => new Set([...prev, jobId]));
          setExitingJobs(prev => {
            const copy = { ...prev };
            delete copy[jobId];
            return copy;
          });
        }, 600);
        await applyToJob({ jobId: jobId as any, type });
        toast.success(`Applied to job successfully!`);
        window.open(url, "_blank");
      } else {
        // Queue AI application in Convex; worker will pick it up
        await queueAIApplication({ jobId: jobId as any, jobUrl: url } as any);
        toast.success("Queued for AI application");
        setActiveTab("ai");
      }
    } catch (error) {
      // Revert animation if mutation failed
      if (type === "manual") {
        setExitingJobs(prev => {
          const copy = { ...prev };
          delete copy[jobId];
          return copy;
        });
        setLocallyAppliedJobs(prev => {
          const newSet = new Set(prev);
          newSet.delete(jobId);
          return newSet;
        });
      }
      toast.error(type === "manual" ? "Failed to apply to job" : "Failed to queue AI application");
    }
  };

  const handleReject = async (jobId: string) => {
    try {
      // Ignore if already animating
      if (exitingJobs[jobId]) return;

      // Mark as exiting with reject animation
      setExitingJobs(prev => ({ ...prev, [jobId]: "reject" }));
      
      // Wait for slide animation to complete, then remove from list
      setTimeout(() => {
        setLocallyAppliedJobs(prev => new Set([...prev, jobId]));
        setExitingJobs(prev => {
          const copy = { ...prev };
          delete copy[jobId];
          return copy;
        });
      }, 600); // Slightly longer than animation duration for smooth exit
      
      await rejectJob({ jobId: jobId as any });
      toast.success("Job rejected");
    } catch (error) {
      // Revert animation if the mutation failed
      setExitingJobs(prev => {
        const copy = { ...prev };
        delete copy[jobId];
        return copy;
      });
      setLocallyAppliedJobs(prev => {
        const newSet = new Set(prev);
        newSet.delete(jobId);
        return newSet;
      });
      toast.error("Failed to reject job");
    }
  };

  const handleUndo = async (jobId: string) => {
    try {
      // Optimistically hide from Applied tab
      setLocallyWithdrawnJobs(prev => new Set([...prev, jobId]));

      await withdrawApplication({ jobId: jobId as any });

      // Allow it to reappear in Job Search tab (remove any local hide)
      setLocallyAppliedJobs(prev => {
        const next = new Set(prev);
        next.delete(jobId);
        return next;
      });

      toast.success("Application withdrawn");
    } catch (error) {
      // Rollback optimistic removal
      setLocallyWithdrawnJobs(prev => {
        const next = new Set(prev);
        next.delete(jobId);
        return next;
      });
      toast.error("Failed to withdraw application");
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

  // Applied list filtered by locally withdrawn jobs for instant UI update in Applied tab
  const appliedList = (appliedJobs || []).filter(job => !locallyWithdrawnJobs.has(job._id));

  const renderJobCard = (job: any, showApplyButtons = true) => {
    const exitType = exitingJobs[job._id as string];
    const isExiting = Boolean(exitType);
    
    // Build class list based on exit state
    let cardClasses = "p-3 shadow-sm border rounded-lg";
    
    if (exitType === "apply") {
      cardClasses += " bg-green-50 border-green-300";
    } else if (exitType === "reject") {
      cardClasses += " bg-red-50 border-red-300";
    }
    
    return (
    <div className={cardClasses}>
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
                disabled={isExiting}
                className="px-3 py-1.5 bg-blue-600 text-white rounded-md hover:bg-blue-700 transition-colors text-xs font-medium disabled:opacity-50 disabled:cursor-not-allowed">
                AI Apply
              </button>
              <button
                onClick={() => handleApply(job._id, "manual", job.url)}
                disabled={isExiting}
                className="px-3 py-1.5 bg-green-600 text-white rounded-md hover:bg-green-700 transition-colors text-xs font-medium disabled:opacity-50 disabled:cursor-not-allowed">
                Manual Apply
              </button>
              <button
                onClick={() => handleReject(job._id)}
                disabled={isExiting}
                className="px-3 py-1.5 bg-gray-200 text-gray-700 rounded-md hover:bg-gray-300 transition-colors text-xs font-medium disabled:opacity-50 disabled:cursor-not-allowed">
                Reject
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
  };

  // Drawer state for viewing filled data
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [drawerItem, setDrawerItem] = useState<any | null>(null);

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
          Applied Jobs {appliedJobs && appliedList.length > 0 && (
            <span className="ml-1 px-2 py-0.5 bg-blue-100 text-blue-800 text-xs rounded-full">
              {appliedList.length}
            </span>
          )}
        </button>
        <button
          onClick={() => setActiveTab("ai")}
          className={`px-4 py-2 rounded-md font-medium transition-colors ${
            activeTab === "ai"
              ? "bg-white text-primary shadow-sm"
              : "text-gray-600 hover:text-gray-900"
          }`}
        >
          AI Applied
          {aiApplications && (aiApplications as any[]).length > 0 && (
            <span className="ml-1 px-2 py-0.5 bg-blue-100 text-blue-800 text-xs rounded-full">
              {(aiApplications as any[]).length}
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
          <div className="space-y-2 overflow-hidden">
            <AnimatePresence>
              {filteredResults.map((job) => (
                <motion.div
                  key={job._id}
                  layout={!exitingJobs[job._id]} // Only animate layout if not exiting
                  initial={false} // Prevent initial animation for existing items
                  animate={{ 
                    opacity: 1, 
                    y: 0
                  }}
                  exit={{
                    x: exitingJobs[job._id] === "apply" ? window.innerWidth : 
                       exitingJobs[job._id] === "reject" ? -window.innerWidth : 0,
                    opacity: 0,
                    rotate: exitingJobs[job._id] === "apply" ? 5 : 
                            exitingJobs[job._id] === "reject" ? -5 : 0,
                    transition: {
                      duration: 0.4,
                      ease: "easeInOut"
                    }
                  }}
                  transition={{
                    layout: {
                      duration: 0.3,
                      delay: exitingJobs[job._id] ? 0 : 0.4, // Delay layout animation for non-exiting items
                      ease: "easeInOut"
                    }
                  }}
                  style={{
                    position: exitingJobs[job._id] ? 'relative' : 'static',
                    zIndex: exitingJobs[job._id] ? 10 : 1
                  }}
                >
                  {renderJobCard(job, true)}
                </motion.div>
              ))}
            </AnimatePresence>
          </div>

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
        </>
      ) : activeTab === "applied" ? (
        /* Applied Jobs Tab */
        <div className="bg-white rounded-lg shadow-sm">
          <div className="p-4 border-b">
            <h2 className="text-xl font-semibold text-gray-900">Applied Jobs</h2>
            <p className="text-gray-600 mt-1">Jobs you have applied to</p>
          </div>
          <div className="space-y-0">
            {appliedList && appliedList.length > 0 ? (
              appliedList.map((job) => renderJobCard(job, false))
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
      ) : activeTab === "ai" ? (
        /* AI Applied Tab */
        <div className="bg-white rounded-lg shadow-sm">
          <div className="p-4 border-b flex items-center justify-between">
            <h2 className="text-xl font-semibold text-gray-900">AI Applied Jobs</h2>
            <div className="flex items-center gap-2">
              <ResumeEditor />
            </div>
          </div>
          <div className="divide-y">
            {(aiApplications || []).map((item: any) => (
              <div key={item._id} className="px-3 py-2">
                <div className="flex justify-between items-center">
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="text-base font-semibold text-gray-900">{item.job?.title || item.jobUrl}</span>
                      {item.job?.level && (
                        <span className="px-2 py-0.5 bg-blue-100 text-blue-800 text-xs font-medium rounded-full">{item.job.level}</span>
                      )}
                      {item.job?.remote && (
                        <span className="px-2 py-0.5 bg-green-100 text-green-800 text-xs font-medium rounded-full">Remote</span>
                      )}
                    </div>
                    <p className="text-sm text-gray-700 font-medium">{item.job?.company || ""}</p>
                    <p className="text-sm text-gray-600">{item.job?.location || ""}</p>
                  </div>
                  <div className="text-right">
                    <span className={`px-2 py-1 text-xs rounded-md ${
                      item.status === 'completed' ? 'bg-green-100 text-green-800' :
                      item.status === 'running' ? 'bg-yellow-100 text-yellow-800' :
                      item.status === 'pending' ? 'bg-gray-100 text-gray-700' : 'bg-red-100 text-red-800'
                    }`}>
                      {item.status.toUpperCase()}
                    </span>
                    <div className="text-xs text-gray-500 mt-1">
                      Queued {new Date(item.queuedAt).toLocaleString()}
                    </div>
                    {item.completedAt && (
                      <div className="text-xs text-gray-500">Completed {new Date(item.completedAt).toLocaleString()}</div>
                    )}
                    {item.error && (
                      <div className="text-xs text-red-600 mt-1 truncate max-w-[240px]" title={item.error}>Error: {item.error}</div>
                    )}
                    {item.status === 'completed' && (
                      <div className="mt-2">
                        <button
                          onClick={() => { setDrawerItem(item); setDrawerOpen(true); }}
                          className="px-2 py-1 text-xs bg-blue-600 text-white rounded hover:bg-blue-700"
                        >
                          View Data
                        </button>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            ))}
            {(aiApplications?.length || 0) === 0 && (
              <div className="p-8 text-center">
                <p className="text-gray-500">No AI applications yet.</p>
              </div>
            )}
          </div>
          <DataDrawer
            open={drawerOpen}
            onClose={() => setDrawerOpen(false)}
            title={drawerItem?.job?.title || 'Filled Data'}
            data={drawerItem?.filledData || null}
            logs={drawerItem?.logs || null}
          />
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
                className={`px-3 py-2 hover:bg-gray-50 ${animatedLiveJobIds.has(job._id) ? "live-job-enter" : ""}`}
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
