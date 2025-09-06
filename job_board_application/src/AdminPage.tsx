import { useMutation, useQuery } from "convex/react";
import { api } from "../convex/_generated/api";
import { toast } from "sonner";
import { useState } from "react";
import type { FormEvent } from "react";

export function AdminPage() {
  const insertFakeJobs = useMutation(api.seedData.insertFakeJobs);
  const recentJobs = useQuery(api.jobs.getRecentJobs);
  const normalizeDevTestJobs = useMutation(api.jobs.normalizeDevTestJobs);
  const deleteJob = useMutation(api.jobs.deleteJob);

  // Sites admin state
  const [showDisabled, setShowDisabled] = useState(false);
  const sites = useQuery(api.router.listSites, { enabledOnly: !showDisabled });
  const allSites = useQuery(api.router.listSites, { enabledOnly: false });
  const disabledCount = allSites ? allSites.filter((s: any) => !s.enabled).length : 0;
  const upsertSite = useMutation(api.router.upsertSite);
  const updateSiteEnabled = useMutation(api.router.updateSiteEnabled);
  // Worker job results
  const successfulSites = useQuery(api.sites.listSuccessfulSites, { limit: 50 });
  const failedSites = useQuery(api.sites.listFailedSites, { limit: 50 });
  const retrySite = useMutation(api.sites.retrySite);
  const successUrls = (successfulSites || []).map((s: any) => s.url);
  const failedUrls = (failedSites || []).map((s: any) => s.url);
  const history = useQuery(api.sites.getScrapeHistoryForUrls, {
    urls: Array.from(new Set([...successUrls, ...failedUrls])),
    limit: 3,
  });
  const historyMap: Record<string, { _id: string; startedAt: number; completedAt: number }[]> = {};
  if (history) {
    for (const h of history as any[]) historyMap[h.sourceUrl] = h.entries;
  }

  // Add site form state
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [pattern, setPattern] = useState("");
  const [enabled, setEnabled] = useState(true);

  const handleInsertFakeJobs = async () => {
    try {
      const result = await insertFakeJobs({});
      toast.success(result.message);
    } catch (error) {
      toast.error("Failed to insert fake jobs");
    }
  };

  const handleAddSite = async (e: FormEvent) => {
    e.preventDefault();
    if (!url.trim()) {
      toast.error("URL is required");
      return;
    }
    try {
      await upsertSite({
        name: name.trim() || undefined,
        url: url.trim(),
        pattern: pattern.trim() || undefined,
        enabled,
      });
      toast.success("Site added");
      setName("");
      setUrl("");
      setPattern("");
      setEnabled(true);
    } catch (err) {
      toast.error("Failed to add site");
    }
  };

  const toggleEnabled = async (id: string, next: boolean) => {
    try {
      await updateSiteEnabled({ id: id as any, enabled: next });
      // Convex React queries auto-refresh; no manual refetch needed
    } catch (err) {
      toast.error("Failed to update site");
    }
  };

  return (
    <div className="max-w-4xl mx-auto p-6">
      <h1 className="text-3xl font-bold text-gray-900 mb-8">Admin Panel</h1>
      
      <div className="bg-white p-6 rounded-lg shadow-sm border mb-6">
        <h2 className="text-xl font-semibold text-gray-900 mb-4">Sites to Scrape</h2>
        <form onSubmit={handleAddSite} className="space-y-3 mb-6">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <input
              type="text"
              placeholder="Name (optional)"
              className="border rounded-md px-3 py-2"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
            <input
              type="url"
              placeholder="URL (required)"
              className="border rounded-md px-3 py-2"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              required
            />
            <input
              type="text"
              placeholder="Pattern (optional)"
              className="border rounded-md px-3 py-2 md:col-span-2"
              value={pattern}
              onChange={(e) => setPattern(e.target.value)}
            />
          </div>
          <div className="flex items-center gap-4">
            <label className="flex items-center gap-2 text-sm text-gray-700">
              <input
                type="checkbox"
                className="h-4 w-4"
                checked={enabled}
                onChange={(e) => setEnabled(e.target.checked)}
              />
              Enabled
            </label>
            <button
              type="submit"
              className="px-4 py-2 bg-green-600 text-white rounded-md hover:bg-green-700 transition-colors font-medium"
            >
              Add Site
            </button>
          </div>
        </form>

        <div className="flex items-center justify-between mb-3">
          <p className="text-sm text-gray-600">
            {sites ? `${sites.length} site${sites.length === 1 ? "" : "s"}` : "Loading sites..."}
          </p>
          <label className="flex items-center gap-2 text-sm text-gray-700">
            <input
              type="checkbox"
              className="h-4 w-4"
              checked={showDisabled}
              onChange={(e) => setShowDisabled(e.target.checked)}
            />
            <span className="flex items-center gap-2">
              Show disabled
              <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-800 border">
                {disabledCount}
              </span>
            </span>
          </label>
        </div>

        <div className="divide-y border rounded-md">
          {sites === undefined && (
            <div className="p-3 text-gray-500">Loading...</div>
          )}
          {sites && sites.length === 0 && (
            <div className="p-3 text-gray-500">No sites found.</div>
          )}
          {sites && sites.map((s) => (
            <div key={s._id} className={`p-3 flex flex-col md:flex-row md:items-center md:justify-between gap-2 ${s.enabled ? "" : "bg-gray-50 text-gray-500"}`}>
              <div>
                <div className="font-medium">{s.name || s.url}</div>
                <div className="text-sm text-gray-600 break-all">{s.url}</div>
                {s.pattern && (
                  <div className="text-xs text-gray-500 break-all">Pattern: {s.pattern}</div>
                )}
              </div>
              <div className="flex items-center gap-3">
                <span className={`text-xs px-2 py-1 rounded ${s.enabled ? "bg-green-100 text-green-800" : "bg-gray-200 text-gray-700"}`}>
                  {s.enabled ? "Enabled" : "Disabled"}
                </span>
                <button
                  onClick={() => toggleEnabled(s._id as unknown as string, !s.enabled)}
                  className={`px-3 py-1 rounded-md text-sm font-medium border ${s.enabled ? "bg-white hover:bg-gray-50" : "bg-white hover:bg-gray-50"}`}
                >
                  {s.enabled ? "Disable" : "Enable"}
                </button>
              </div>
            </div>
          ))}
        </div>
        <p className="text-xs text-gray-500 mt-2">
          Note: Workflows only fetch enabled sites via the `/api/sites` endpoint.
        </p>
      </div>

      <div className="bg-white p-6 rounded-lg shadow-sm border mb-6">
        <h2 className="text-xl font-semibold text-gray-900 mb-4">Database Management</h2>
        <button
          onClick={handleInsertFakeJobs}
          className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 transition-colors font-medium"
        >
          Insert 10 Fake Jobs
        </button>
        <button
          onClick={async () => {
            try {
              const res = await normalizeDevTestJobs({});
              toast.success(`Normalized ${res.updated} dev/test jobs`);
            } catch (e: any) {
              const msg = e?.message || e?.toString?.() || "Unknown error";
              toast.error(`Failed to normalize jobs: ${msg}`);
            }
          }}
          className="ml-3 px-4 py-2 bg-emerald-600 text-white rounded-md hover:bg-emerald-700 transition-colors font-medium"
        >
          Normalize Dev/Test Jobs
        </button>
        <p className="text-sm text-gray-600 mt-2">
          This will add 10 sample job listings to the database for testing purposes.
        </p>
      </div>

      <div className="bg-white p-6 rounded-lg shadow-sm border mb-6">
        <h2 className="text-xl font-semibold text-gray-900 mb-2">Worker Jobs</h2>
        <div className="grid md:grid-cols-2 gap-6">
          <div>
            <h3 className="font-medium text-green-800 mb-2">Successful</h3>
            <div className="border rounded-md divide-y">
              {successfulSites === undefined && (
                <div className="p-3 text-gray-500">Loading...</div>
              )}
              {successfulSites && successfulSites.length === 0 && (
                <div className="p-3 text-gray-500">No successful jobs yet.</div>
              )}
              {successfulSites && successfulSites.map((s: any) => (
                <div key={s._id} className="p-3">
                  <div className="font-medium">{s.name || s.url}</div>
                  <div className="text-xs text-gray-600 break-all">{s.url}</div>
                  <div className="text-xs text-gray-500">Last run: {s.lastRunAt ? new Date(s.lastRunAt).toLocaleString() : "N/A"}</div>
                  {historyMap[s.url] && historyMap[s.url].length > 0 && (
                    <div className="text-xs text-gray-500 mt-1">
                      History: {historyMap[s.url].map((e) => new Date(e.completedAt).toLocaleString()).join(", ")}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
          <div>
            <h3 className="font-medium text-red-800 mb-2">Failed</h3>
            <div className="border rounded-md divide-y">
              {failedSites === undefined && (
                <div className="p-3 text-gray-500">Loading...</div>
              )}
              {failedSites && failedSites.length === 0 && (
                <div className="p-3 text-gray-500">No failed jobs.</div>
              )}
              {failedSites && failedSites.map((s: any) => (
                <div key={s._id} className="p-3 flex items-start justify-between gap-3">
                  <div>
                    <div className="font-medium">{s.name || s.url}</div>
                    <div className="text-xs text-gray-600 break-all">{s.url}</div>
                    {s.lastError && (
                      <div className="text-xs text-red-600 mt-1">Error: {s.lastError}</div>
                    )}
                    <div className="text-xs text-gray-500 mt-1">
                      Failures: {s.failCount ?? 1} • Last at: {s.lastFailureAt ? new Date(s.lastFailureAt).toLocaleString() : "N/A"}
                    </div>
                    {historyMap[s.url] && historyMap[s.url].length > 0 && (
                      <div className="text-xs text-gray-500 mt-1">
                        History: {historyMap[s.url].map((e) => new Date(e.completedAt).toLocaleString()).join(", ")}
                      </div>
                    )}
                  </div>
                  <div>
                    <button
                      onClick={async () => {
                        try {
                          await retrySite({ id: s._id, clearError: true });
                          toast.success("Retry queued (site unlocked)");
                        } catch (e: any) {
                          toast.error(`Retry failed: ${e?.message || "Unknown error"}`);
                        }
                      }}
                      className="px-3 py-1.5 text-sm bg-amber-600 text-white rounded-md hover:bg-amber-700"
                    >
                      Retry
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      <div className="bg-white p-6 rounded-lg shadow-sm border">
        <h2 className="text-xl font-semibold text-gray-900 mb-4">Current Jobs in Database</h2>
        {recentJobs ? (
          <div className="space-y-3">
            <p className="text-sm text-gray-600">Total jobs: {recentJobs.length}</p>
            {recentJobs.map((job) => (
              <div key={job._id} className="border-l-4 border-blue-500 pl-4 py-2 flex items-start justify-between gap-4">
                <div>
                  <h3 className="font-medium text-gray-900">{job.title}</h3>
                  <p className="text-sm text-gray-600">{job.company} - {job.location}</p>
                  <p className="text-xs text-gray-500">
                    Posted: {new Date(job.postedAt).toLocaleString()}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={async () => {
                      try {
                        await deleteJob({ jobId: job._id as any });
                        toast.success("Job deleted");
                      } catch (e: any) {
                        toast.error(`Failed to delete: ${e?.message || "Unknown error"}`);
                      }
                    }}
                    className="px-3 py-1.5 text-sm bg-red-600 text-white rounded-md hover:bg-red-700"
                  >
                    Delete
                  </button>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-gray-500">Loading jobs...</p>
        )}
      </div>
    </div>
  );
}
