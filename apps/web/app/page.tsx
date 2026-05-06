"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";

type LLMHealth = { available: boolean; model?: string; base_url: string; error?: string };
type Summary = {
  active_jobs: number; total_jobs: number; new_last_7d: number;
  high_ranked: number; companies_total: number;
  applications_by_status: Record<string, number>;
};
type Charts = {
  jobs_over_time: { date: string; count: number }[];
  sources: Record<string, number>;
  score_distribution: { bucket?: string; range?: string; count: number }[];
};
type RecentEvent = {
  id: number; event_type: string; occurred_at?: string;
  job: { id: number; title: string; company?: string };
};

const DASHBOARD_RUN_STORAGE_KEY = "joby.dashboardRunId";

export default function Dashboard() {
  const [llm, setLlm] = useState<LLMHealth | null>(null);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [charts, setCharts] = useState<Charts | null>(null);
  const [events, setEvents] = useState<RecentEvent[]>([]);
  const [runBusy, setRunBusy] = useState(false);
  const [runMsg, setRunMsg] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  async function load() {
    setLoading(true);
    await Promise.allSettled([
      api<LLMHealth>("/api/llm/health").then(setLlm),
      api<Summary>("/api/dashboard/summary").then(setSummary),
      api<Charts>("/api/dashboard/charts").then(setCharts),
      api<{ items: RecentEvent[] }>("/api/watches/events/recent?limit=8").then((r) => setEvents(r.items)),
    ]);
    setLastUpdated(new Date());
    setLoading(false);
  }
  useEffect(() => { load(); }, []);

  useEffect(() => {
    function refreshWhenVisible() {
      if (document.visibilityState === "visible") load();
    }
    window.addEventListener("focus", load);
    document.addEventListener("visibilitychange", refreshWhenVisible);
    return () => {
      window.removeEventListener("focus", load);
      document.removeEventListener("visibilitychange", refreshWhenVisible);
    };
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const stored = window.localStorage.getItem(DASHBOARD_RUN_STORAGE_KEY);
    const runId = stored ? Number(stored) : 0;
    if (runId > 0) attachRunStream(runId, { resume: true });
    // eslint-disable-next-line
  }, []);

  function clearStoredRun(runId: number) {
    if (typeof window === "undefined") return;
    if (window.localStorage.getItem(DASHBOARD_RUN_STORAGE_KEY) === String(runId)) {
      window.localStorage.removeItem(DASHBOARD_RUN_STORAGE_KEY);
    }
  }

  async function attachRunStream(runId: number, options: { resume?: boolean } = {}) {
    setRunBusy(true);
    if (typeof window !== "undefined") {
      window.localStorage.setItem(DASHBOARD_RUN_STORAGE_KEY, String(runId));
    }
    try {
      const snapshot = await api<any>(`/api/runs/${runId}`);
      const lastEvent = (snapshot.stats?.events || []).at(-1);
      setRunMsg(lastEvent ? `${lastEvent.stage}: ${lastEvent.message || ""}` : `${options.resume ? "resuming" : "run"} #${runId}: ${snapshot.status}`);
      if (["completed", "failed", "skipped"].includes(snapshot.status)) {
        clearStoredRun(runId);
        setRunBusy(false);
        if (snapshot.status === "completed") {
          setRunMsg(`done — ${JSON.stringify(snapshot.stats?.totals || {})}`);
          load();
        } else {
          setRunMsg(`${snapshot.status}: ${JSON.stringify(snapshot.error || {})}`);
        }
        return;
      }
    } catch (err: any) {
      setRunMsg(`error resuming run #${runId}: ${err.message}`);
    }

    const base = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
    const es = new EventSource(`${base}/api/runs/${runId}/events`);
    es.onmessage = (e) => { try { const ev = JSON.parse(e.data); setRunMsg(`${ev.stage}: ${ev.message || ""}`); } catch {} };
    es.addEventListener("done", (e: MessageEvent) => {
      try { const d = JSON.parse(e.data); setRunMsg(`done — ${JSON.stringify(d.totals || {})}`); } catch {}
      clearStoredRun(runId);
      es.close(); setRunBusy(false); load();
    });
    es.onerror = () => {
      es.close();
      setRunBusy(false);
      setRunMsg(`Run #${runId} is still in progress. Reopen the dashboard to reconnect.`);
    };
  }

  async function scrape() {
    setRunBusy(true); setRunMsg("starting…");
    try {
      const { run_id } = await api<{ run_id: number }>("/api/runs/trigger", { method: "POST" });
      await attachRunStream(run_id);
    } catch (err: any) { setRunMsg(`error: ${err.message}`); setRunBusy(false); }
  }

  return (
    <div className="flex flex-col gap-5">
      <div className="rounded-[28px] border border-white/70 bg-white/75 p-5 shadow-card backdrop-blur-xl">
      <div className="flex items-end justify-between flex-wrap gap-3">
        <div>
          <div className="text-xs font-semibold uppercase tracking-[0.16em] text-brand-600">Dashboard</div>
          <h1 className="mt-1 text-2xl font-semibold tracking-tight sm:text-3xl">Your search cockpit</h1>
          <p className="mt-1 text-sm text-ink-500">Live local stats, tracked-board refreshes, and application movement.</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Link href="/jobs" className="btn-primary">Search jobs</Link>
          <button onClick={scrape} disabled={runBusy} className="btn-primary">
            {runBusy ? "Refreshing…" : "Refresh tracked boards"}
          </button>
          <Link href="/watches" className="btn-secondary">Watches</Link>
        </div>
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-ink-500">
        <span>{loading ? "Refreshing dashboard..." : lastUpdated ? `Updated ${lastUpdated.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}` : "Ready"}</span>
        {summary && summary.total_jobs === 0 && <span className="badge-ink">No indexed jobs yet</span>}
      </div>
      </div>

      {runMsg && (
        <div className="card text-sm text-ink-700">
          <span className="badge-brand mr-2">refresh</span>{runMsg}
        </div>
      )}

      {/* Top row: 3 metric cards + featured brand card */}
      <div className="grid grid-cols-12 gap-5">
        <MetricCard tint="sky" label="Active jobs"
          value={summary?.active_jobs} loading={loading && !summary} sub={summary ? `${summary.total_jobs} total indexed` : "waiting for API"} />
        <MetricCard tint="butter" label="New this week"
          value={summary?.new_last_7d} loading={loading && !summary} sub="first-seen in last 7 days" />
        <MetricCard tint="mint" label="High-ranked"
          value={summary?.high_ranked} loading={loading && !summary} sub="match score 70+" />

        {/* Brand CTA card */}
        <div className="col-span-12 md:col-span-6 lg:col-span-3 card-brand flex flex-col justify-between min-h-[160px] relative overflow-hidden">
          <div className="absolute -right-10 -bottom-10 h-40 w-40 rounded-full bg-white/10 blur-2xl" />
          <div className="absolute right-6 top-6 h-16 w-16 rounded-full bg-white/10" />
          <div>
            <div className="text-xs uppercase tracking-wider opacity-80">Companies</div>
            <div className="text-3xl font-semibold mt-1">{summary ? summary.companies_total : "--"}</div>
          </div>
          <Link href="/companies" className="text-sm underline/0 hover:underline self-start">
            Browse companies →
          </Link>
        </div>
      </div>

      {/* Middle: large chart + utility stack */}
      <div className="grid grid-cols-12 gap-5">
        <div className="col-span-12 lg:col-span-8 card">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h2 className="font-semibold">Jobs over time</h2>
              <p className="text-xs text-ink-500">New job rows per day (last 14 days)</p>
            </div>
            <div className="flex items-center gap-2 text-xs text-ink-500">
              <span className="inline-block h-2 w-2 rounded-full bg-brand-500" />
              first_seen
            </div>
          </div>
          <TimeChart data={charts?.jobs_over_time || []} />
        </div>

        <div className="col-span-12 lg:col-span-4 flex flex-col gap-5">
          <div className="card">
            <div className="text-xs uppercase tracking-wider text-ink-500">Ranking mode</div>
            <div className={`text-sm font-medium mt-1 ${llm?.available ? "text-emerald-700" : "text-slate-700"}`}>
              {llm?.available ? `LM Studio ${llm.model || "ready"}` : "Deterministic ranking active"}
            </div>
            <div className="text-xs text-ink-500 mt-1">
              {llm?.available ? "Local model analysis can augment the heuristic score." : "LM Studio is optional; Joby still screens and ranks jobs locally."}
            </div>
            {llm?.base_url && <div className="text-xs text-ink-400 mt-1 break-all">{llm.base_url}</div>}
          </div>

          <div className="card">
            <div className="flex items-center justify-between mb-3">
              <div className="text-xs uppercase tracking-wider text-ink-500">Applications</div>
              <Link className="text-xs text-brand-600 hover:underline" href="/applications">View →</Link>
            </div>
            <div className="grid grid-cols-2 gap-2 text-sm">
              {["saved","applied","interviewing","offer"].map((k) => (
                <div key={k} className="flex items-center justify-between rounded-xl bg-ink-300/10 px-3 py-2">
                  <span className="capitalize text-ink-700">{k}</span>
                  <span className="tabular-nums font-semibold">
                    {summary?.applications_by_status?.[k] ?? 0}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Bottom: score distribution + recent events */}
      <div className="grid grid-cols-12 gap-5">
        <div className="col-span-12 lg:col-span-7 card">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h2 className="font-semibold">Score distribution</h2>
              <p className="text-xs text-ink-500">Composite scores across active jobs</p>
            </div>
          </div>
          <Histogram data={charts?.score_distribution || []} />
        </div>

        <div className="col-span-12 lg:col-span-5 card">
          <div className="flex items-center justify-between mb-3">
            <h2 className="font-semibold">Recent events</h2>
            <Link className="text-xs text-brand-600 hover:underline" href="/watches">All →</Link>
          </div>
          {events.length === 0 ? (
            <p className="text-sm text-ink-500">No events yet. Run a scrape or schedule a watch.</p>
          ) : (
            <ul className="space-y-2">
              {events.map((e) => (
                <li key={e.id} className="flex items-center gap-3 rounded-xl px-3 py-2 hover:bg-ink-300/10">
                  <EventBadge type={e.event_type} />
                  <div className="min-w-0 flex-1">
                    <Link href={`/jobs?id=${e.job.id}`} className="text-sm font-medium truncate hover:underline block">
                      {e.job.title}
                    </Link>
                    <div className="text-xs text-ink-500 truncate">{e.job.company || "—"}</div>
                  </div>
                  <div className="text-[11px] text-ink-400 tabular-nums">
                    {e.occurred_at ? new Date(e.occurred_at).toLocaleDateString() : ""}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}

/* ---------- subcomponents ---------- */

function MetricCard({ tint, label, value, sub, loading }: {
  tint: "sky" | "butter" | "mint"; label: string; value?: number; sub: string; loading?: boolean;
}) {
  const cls = tint === "sky" ? "card-tint-sky" : tint === "butter" ? "card-tint-butter" : "card-tint-mint";
  return (
    <div className={`col-span-12 sm:col-span-6 lg:col-span-3 ${cls} min-h-[160px] flex flex-col justify-between`}>
      <div className="text-xs uppercase tracking-wider text-ink-500">{label}</div>
      <div>
        <div className="text-4xl font-semibold tracking-tight">{loading ? "--" : value ?? 0}</div>
        <div className="text-xs text-ink-500 mt-1">{sub}</div>
      </div>
    </div>
  );
}

function TimeChart({ data }: { data: { date: string; count: number }[] }) {
  const total = data.reduce((sum, item) => sum + item.count, 0);
  if (total === 0) {
    return <ChartEmpty label="No new jobs in the current 14-day window." />;
  }
  const max = Math.max(1, ...data.map((d) => d.count));
  const width = 100; // svg viewBox width
  const height = 40;
  const step = data.length > 1 ? width / (data.length - 1) : 0;
  const pts = data.map((d, i) => `${i * step},${height - (d.count / max) * (height - 4) - 2}`).join(" ");
  return (
    <div>
      <svg viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none"
           className="w-full h-40">
        <defs>
          <linearGradient id="g1" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor="#6E4FD1" stopOpacity="0.35" />
            <stop offset="100%" stopColor="#6E4FD1" stopOpacity="0" />
          </linearGradient>
        </defs>
        {data.length > 0 && (
          <>
            <polygon fill="url(#g1)"
              points={`0,${height} ${pts} ${width},${height}`} />
            <polyline fill="none" stroke="#6E4FD1" strokeWidth="0.8" points={pts} />
          </>
        )}
      </svg>
      <div className="flex justify-between text-[10px] text-ink-400 mt-1">
        <span>{data[0]?.date?.slice(5) ?? ""}</span>
        <span>{data[Math.floor(data.length / 2)]?.date?.slice(5) ?? ""}</span>
        <span>{data[data.length - 1]?.date?.slice(5) ?? ""}</span>
      </div>
    </div>
  );
}

function Histogram({ data }: { data: { bucket?: string; range?: string; count: number }[] }) {
  const total = data.reduce((sum, item) => sum + item.count, 0);
  if (total === 0) {
    return <ChartEmpty label="No ranking distribution yet. Run a search or refresh tracked boards." />;
  }
  const max = Math.max(1, ...data.map((d) => d.count));
  return (
    <div className="flex items-end gap-2 h-40">
      {data.map((d) => (
        <div key={d.bucket || d.range} className="flex-1 flex flex-col items-center gap-1.5">
          <div className="w-full rounded-t-md bg-brand-300/70 hover:bg-brand-500 transition"
               style={{ height: `${(d.count / max) * 100}%`, minHeight: 4 }}
               title={`${d.bucket || d.range}: ${d.count}`} />
          <div className="text-[10px] text-ink-400">{d.bucket || d.range}</div>
        </div>
      ))}
    </div>
  );
}

function ChartEmpty({ label }: { label: string }) {
  return (
    <div className="flex h-40 items-center justify-center rounded-2xl border border-dashed border-ink-300/40 bg-ink-300/10 px-4 text-center text-sm text-ink-500">
      {label}
    </div>
  );
}

function EventBadge({ type }: { type: string }) {
  const map: Record<string, string> = {
    new: "badge-mint", material_change: "badge-brand",
    reappeared: "badge-sky", disappeared: "badge-rose",
  };
  const label: Record<string, string> = {
    new: "New", material_change: "Changed",
    reappeared: "Reappeared", disappeared: "Gone",
  };
  return <span className={map[type] || "badge-ink"}>{label[type] || type}</span>;
}

