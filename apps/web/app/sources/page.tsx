"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";

type Match = { type: string; slug: string; job_count: number };
type Row = {
  company: string;
  type: string;
  slug: string;
  enabled: boolean;
  user_added?: boolean;
};
type HealthRow = {
  key: string;
  type: string;
  label: string;
  enabled: boolean;
  last_status: string;
  last_success_at?: string | null;
  last_error_at?: string | null;
  last_error?: string | null;
  last_count?: number | null;
  last_duration_ms?: number | null;
  last_cache_status?: string | null;
  last_cache_age_seconds?: number | null;
  recent_history?: {
    at?: string | null;
    status: string;
    count?: number | null;
    duration_ms?: number | null;
    cache_status?: string | null;
  }[];
};
type SourceHealth = {
  jobspy: {
    enabled: boolean;
    available: boolean;
    version?: string | null;
    cached_queries: number;
    total_calls: number;
    total_hits: number;
    ttl_seconds: number;
    last_error?: string | null;
  };
  search_cache: {
    used_cache?: boolean | null;
    freshness_window_hours?: number | null;
    latest_run_at?: string | null;
    total_queries: number;
    hit: number;
    miss: number;
    stale: number;
    bypassed: number;
  };
  sources: HealthRow[];
  recent_errors: { run_id: number; at?: string | null; key: string; error: string }[];
};

export default function SourcesPage() {
  const [rows, setRows] = useState<Row[]>([]);
  const [counts, setCounts] = useState<any>(null);
  const [jobspyEnabled, setJobspyEnabled] = useState(false);
  const [workdayCount, setWorkdayCount] = useState(0);
  const [health, setHealth] = useState<SourceHealth | null>(null);

  const [company, setCompany] = useState("");
  const [website, setWebsite] = useState("");
  const [searching, setSearching] = useState(false);
  const [matches, setMatches] = useState<Match[] | null>(null);
  const [msg, setMsg] = useState("");

  async function load() {
    const data = await api<any>("/api/sources");
    setRows(data.ats_sources || []);
    setCounts(data.counts || null);
    setJobspyEnabled(Boolean(data.jobspy?.enabled));
    setWorkdayCount((data.workday?.organizations || []).length);
    try { setHealth(await api<SourceHealth>("/api/sources/health")); } catch {}
  }
  useEffect(() => { load(); }, []);

  async function discover() {
    setSearching(true);
    setMsg("");
    setMatches(null);
    try {
      const r = await api<{ matches: Match[] }>("/api/sources/discover", {
        method: "POST",
        body: JSON.stringify({ company, website: website || undefined }),
      });
      setMatches(r.matches);
      if (!r.matches.length) setMsg("No public ATS board found for that name. Try the company's careers-page domain as the website.");
    } catch (e: any) {
      setMsg(`error: ${e.message}`);
    } finally {
      setSearching(false);
    }
  }

  async function addMatch(m: Match) {
    await api("/api/sources/add", {
      method: "POST",
      body: JSON.stringify({
        company, type: m.type, slug: m.slug, enabled: true,
      }),
    });
    setMsg(`Added ${company} (${m.type}/${m.slug}). It will be scraped on the next run.`);
    setMatches(null);
    setCompany("");
    setWebsite("");
    load();
  }

  async function removeRow(r: Row) {
    if (!r.user_added) return;
    await api(`/api/sources/${r.type}/${r.slug}`, { method: "DELETE" });
    load();
  }

  const curated = rows.filter((r) => !r.user_added);
  const userAdded = rows.filter((r) => r.user_added);

  return (
    <div className="grid gap-4 min-w-0">
      <div className="rounded-[28px] border border-white/70 bg-white/75 p-5 shadow-card backdrop-blur-xl">
      <h1 className="text-2xl font-semibold">Sources</h1>
      <div className="mt-1 max-w-4xl text-sm text-ink-500">
        Joby scrapes company job boards directly (not LinkedIn/Indeed aggregators,
        unless you enable JobSpy). Add any company with a public ATS — Greenhouse,
        Lever, Ashby, SmartRecruiters, Workable, or Recruitee — and Joby will pull
        its jobs on every scheduled run.
      </div>
      </div>

      <div className="card min-w-0">
        <div className="font-medium mb-2">Add a company</div>
        <div className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto]">
          <input
            className="input"
            placeholder="Company name (e.g. Figma)"
            value={company}
            onChange={(e) => setCompany(e.target.value)}
          />
          <input
            className="input"
            placeholder="Website (optional, helps disambiguate)"
            value={website}
            onChange={(e) => setWebsite(e.target.value)}
          />
          <button
            className="btn-primary"
            onClick={discover}
            disabled={!company.trim() || searching}
          >
            {searching ? "Searching..." : "Find job board"}
          </button>
        </div>
        {msg && <div className="text-sm mt-2 text-ink-600">{msg}</div>}

        {matches && matches.length > 0 && (
          <div className="mt-3 grid gap-2">
            {matches.map((m) => (
              <div
                key={`${m.type}-${m.slug}`}
                className="flex items-center justify-between rounded-xl border border-ink-200 px-3 py-2"
              >
                <div>
                  <div className="font-medium">
                    {m.type} / {m.slug}
                  </div>
                  <div className="text-xs text-ink-500">
                    {m.job_count} job{m.job_count === 1 ? "" : "s"} currently listed
                  </div>
                </div>
                <button className="btn-secondary" onClick={() => addMatch(m)}>
                  Add
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {counts && (
        <div className="card min-w-0">
          <div className="font-medium mb-2">Summary</div>
          <div className="grid grid-cols-3 gap-3 text-sm">
            <Stat label="Curated ATS boards" value={counts.ats_enabled} />
            <Stat label="Your additions" value={counts.user_added} />
            <Stat label="Workday orgs" value={workdayCount} />
          </div>
          <div className="text-xs text-ink-500 mt-2">
            JobSpy aggregator: {jobspyEnabled ? "enabled" : "disabled"} (configure in
            Settings).
          </div>
        </div>
      )}

      {health && (
        <div className="card min-w-0">
          <div className="flex items-center justify-between gap-3 mb-3">
            <div className="font-medium">Health</div>
            <button className="btn-secondary text-sm" onClick={load}>Refresh</button>
          </div>
          <div className="grid sm:grid-cols-3 lg:grid-cols-6 gap-3 text-sm mb-4">
            <Stat label="JobSpy package" value={health.jobspy.available ? "ready" : "missing"} />
            <Stat label="JobSpy cache" value={health.jobspy.cached_queries} />
            <Stat label="Tracked queries" value={health.search_cache.total_queries} />
            <Stat label="Cache hits" value={health.search_cache.hit} />
            <Stat label="Cache stale" value={health.search_cache.stale} />
            <Stat label="Recent errors" value={health.recent_errors.length} />
          </div>
          <div className="rounded-xl bg-ink-300/10 px-3 py-3 text-sm text-ink-700 mb-4">
            <div className="font-medium text-ink-800">Search cache and freshness</div>
            <div className="mt-1">
              Mode: {cacheModeLabel(health.search_cache.used_cache)}
              {health.search_cache.freshness_window_hours ? ` • freshness window ${health.search_cache.freshness_window_hours}h` : ""}
              {health.search_cache.latest_run_at ? ` • latest tracked run ${new Date(health.search_cache.latest_run_at).toLocaleString()}` : ""}
            </div>
            <div className="mt-1 text-xs text-ink-500">
              Misses {health.search_cache.miss} • stale {health.search_cache.stale} • refresh-only queries {health.search_cache.bypassed}
            </div>
          </div>
          <HealthTable rows={health.sources.slice(0, 12)} />
          {health.recent_errors.length > 0 && (
            <div className="mt-4 grid gap-2">
              {health.recent_errors.map((item, index) => (
                <div key={`${index}-${item.run_id}-${item.key}-${item.error}`} className="rounded-md bg-rose-50 px-3 py-2 text-xs text-rose-800 break-words">
                  <span className="font-medium">{item.key}</span>: {item.error}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {userAdded.length > 0 && (
        <div className="card min-w-0">
          <div className="font-medium mb-2">Companies you added</div>
          <SourceTable rows={userAdded} onRemove={removeRow} />
        </div>
      )}

      <div className="card min-w-0">
        <div className="font-medium mb-2">
          Curated ({curated.length})
        </div>
        <SourceTable rows={curated} />
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="rounded-xl bg-ink-300/10 px-3 py-2">
      <div className="text-xs uppercase tracking-wider text-ink-500">{label}</div>
      <div className="text-lg font-semibold">{value}</div>
    </div>
  );
}

function SourceTable({
  rows,
  onRemove,
}: {
  rows: Row[];
  onRemove?: (r: Row) => void;
}) {
  if (!rows.length) {
    return <div className="text-sm text-ink-500">None yet.</div>;
  }
  return (
    <div className="max-w-full overflow-x-auto">
      <table className="min-w-[560px] w-full text-sm">
        <thead>
          <tr className="text-left text-xs uppercase tracking-wider text-ink-500">
            <th className="py-1 pr-3">Company</th>
            <th className="py-1 pr-3">Type</th>
            <th className="py-1 pr-3">Slug</th>
            <th className="py-1 pr-3">Enabled</th>
            {onRemove && <th className="py-1"></th>}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={`${r.type}-${r.slug}`} className="border-t border-ink-200/50">
              <td className="py-1 pr-3 max-w-[220px] break-words">{r.company}</td>
              <td className="py-1 pr-3">{r.type}</td>
              <td className="py-1 pr-3 font-mono text-xs max-w-[240px] break-all">{r.slug}</td>
              <td className="py-1 pr-3">{r.enabled ? "yes" : "no"}</td>
              {onRemove && (
                <td className="py-1 text-right">
                  <button
                    className="text-xs text-rose-600 hover:underline"
                    onClick={() => onRemove(r)}
                  >
                    Remove
                  </button>
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function HealthTable({ rows }: { rows: HealthRow[] }) {
  if (!rows.length) {
    return <div className="text-sm text-ink-500">No source runs yet.</div>;
  }
  return (
    <div className="max-w-full overflow-x-auto">
      <table className="min-w-[760px] w-full text-sm">
        <thead>
          <tr className="text-left text-xs uppercase tracking-wider text-ink-500">
            <th className="py-1 pr-3">Source</th>
            <th className="py-1 pr-3">Status</th>
            <th className="py-1 pr-3">Count</th>
            <th className="py-1 pr-3">Duration</th>
            <th className="py-1 pr-3">Cache</th>
            <th className="py-1 pr-3">Last success</th>
            <th className="py-1 pr-3">Recent history</th>
            <th className="py-1 pr-3">Last error</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.key} className="border-t border-ink-200/50">
              <td className="py-1 pr-3 max-w-[220px]">
                <div className="font-medium break-words">{row.label}</div>
                <div className="font-mono text-[11px] text-ink-500 break-all">{row.key}</div>
              </td>
              <td className="py-1 pr-3"><StatusPill status={row.last_status} /></td>
              <td className="py-1 pr-3 tabular-nums">{row.last_count ?? "-"}</td>
              <td className="py-1 pr-3 text-xs tabular-nums">{formatDuration(row.last_duration_ms)}</td>
              <td className="py-1 pr-3 text-xs">{formatCache(row.last_cache_status, row.last_cache_age_seconds)}</td>
              <td className="py-1 pr-3 text-xs">{row.last_success_at ? new Date(row.last_success_at).toLocaleString() : "-"}</td>
              <td className="py-1 pr-3"><HistoryTrail history={row.recent_history} /></td>
              <td className="py-1 pr-3 text-xs text-rose-700 max-w-[220px] break-words">{row.last_error || "-"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function StatusPill({ status }: { status: string }) {
  const cls =
    status === "ok"
      ? "bg-mint-50 text-emerald-700"
      : status === "error"
        ? "bg-rose-50 text-rose-700"
        : status === "degraded"
          ? "bg-butter-50 text-amber-800"
          : "bg-slate-100 text-slate-700";
  return <span className={`inline-flex rounded-full px-2 py-0.5 text-xs ${cls}`}>{status}</span>;
}

function HistoryTrail({ history }: { history?: HealthRow["recent_history"] }) {
  const items = (history || []).slice(0, 3);
  if (!items.length) return <span className="text-xs text-ink-400">-</span>;
  return (
    <div className="flex flex-wrap gap-1">
      {items.map((item, index) => (
        <span key={`${index}-${item.at || "unknown"}-${item.status}-${item.cache_status || "none"}`}
              className="rounded-full bg-ink-300/10 px-2 py-0.5 text-[11px] text-ink-600">
          {item.status}
          {typeof item.count === "number" ? ` ${item.count}` : ""}
          {item.cache_status ? ` ${item.cache_status}` : ""}
        </span>
      ))}
    </div>
  );
}

function formatDuration(value?: number | null) {
  if (typeof value !== "number") return "-";
  return `${value} ms`;
}

function formatCache(status?: string | null, ageSeconds?: number | null) {
  if (!status) return "-";
  if (typeof ageSeconds === "number") return `${status} • ${ageSeconds}s old`;
  return status;
}

function cacheModeLabel(value?: boolean | null) {
  if (value === true) return "cached";
  if (value === false) return "refresh-only";
  return "not tracked yet";
}
