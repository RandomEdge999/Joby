"use client";
import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { api, API_BASE } from "@/lib/api";

type ApplicationStatus = "saved" | "applied" | "interviewing" | "offer" | "rejected" | "archived";
type SearchIntent = "explore" | "match" | "strict";

type Contact = {
  id: number;
  name?: string;
  title?: string;
  email?: string;
  linkedin_url?: string;
  source?: string;
  confidence?: number;
  evidence?: any;
};

type ApplicationRecord = {
  id: number;
  job_id: number;
  status: ApplicationStatus;
  applied_at?: string;
  next_action_at?: string;
  portal_url?: string;
  notes_summary?: string;
  created_at?: string;
  updated_at?: string;
};

type NoteRecord = {
  id: number;
  job_id?: number;
  company_id?: number;
  body: string;
  created_at: string;
  updated_at: string;
};

type Job = {
  id: number;
  title: string;
  url?: string;
  source: string;
  company?: { id?: number; name?: string; tier?: string };
  location: { raw?: string; city?: string; state?: string; remote_type?: string };
  employment_type?: string;
  level_guess?: string;
  salary: { min?: number; max?: number; currency?: string };
  posted_at?: string;
  description_text?: string;
  description_html?: string;
  ranking?: { fit: number; opportunity: number; urgency: number; composite: number; reason_json: any };
  screening?: { prefilter_passed: boolean; prefilter_reasons: any; llm_status: string; screening_json: any };
  eligibility?: {
    label: string;
    summary: string;
    visa_tier: string;
    sponsorship_signal: string;
    sponsorship_summary: string;
    clearance_status: string;
    citizenship_status: string;
    employment_status: string;
    level_status: string;
    location_status: string;
    evidence: string[];
  };
  trust?: {
    label: string;
    score: number;
    summary: string;
    evidence: string[];
    warnings: string[];
  };
  contacts?: Contact[];
};

type ListResp = { total: number; items: Job[]; page: number; page_size: number; run_id?: number | null };
type SourceAttempt = {
  key: string;
  type?: string;
  label?: string;
  status?: string;
  count?: number;
  duration_ms?: number;
  cache?: { status?: string; age_seconds?: number | null };
  error?: string;
};
type SourceSummary = {
  details?: Record<string, SourceAttempt>;
  cache?: Record<string, any>;
};
type RunDetail = {
  id: number;
  status: "pending" | "running" | "completed" | "failed" | "skipped" | string;
  stats?: { events?: any[]; totals?: any; search?: any };
  search?: any;
  source_summary?: SourceSummary | null;
  totals?: any;
  error?: any;
};
type RecentRun = RunDetail & {
  trigger_type?: string;
  started_at?: string;
  finished_at?: string;
};

const ACTIVE_RUN_STORAGE_KEY = "joby.activeRunId";
const RESULT_RUN_STORAGE_KEY = "joby.resultRunId";
const FILTER_STORAGE_KEY = "joby.jobsFilters";
const SEARCH_RESULT_LIMIT_OPTIONS = [100, 200, 500, 1000];
const SEARCH_INTENT_OPTIONS: { value: SearchIntent; label: string; help: string }[] = [
  { value: "explore", label: "Explore", help: "Broader discovery with resume skill matching relaxed for this run." },
  { value: "match", label: "Match", help: "Balanced ranking using your saved profile and search text." },
  { value: "strict", label: "Strict", help: "Only show run results that pass deterministic profile screening." },
];

const RUN_STAGE_PROGRESS: Record<string, number> = {
  loading_profile: 8,
  search_config: 12,
  search_scope: 16,
  loading_sources: 22,
  scraping: 38,
  normalizing: 56,
  deduplicating: 66,
  persisted: 74,
  tier_classifying: 80,
  contact_discovery: 84,
  screening: 90,
  ranking_progress: 94,
  diffing: 98,
  completed: 100,
};

const RUN_STAGE_LABELS: Record<string, string> = {
  loading_profile: "Preparing your profile",
  search_config: "Configuring search",
  search_scope: "Setting search scope",
  loading_sources: "Opening sources",
  scraping: "Searching the web",
  normalizing: "Normalizing jobs",
  deduplicating: "Removing duplicates",
  persisted: "Saving results",
  tier_classifying: "Checking companies",
  contact_discovery: "Looking for contacts",
  contact_discovery_limited: "Contact lookup limited",
  screening: "Scoring eligibility",
  ranking_progress: "Ranking jobs",
  diffing: "Recording changes",
  completed: "Search complete",
};

const EMPLOYMENT_OPTIONS = [
  { value: "full_time", label: "Full-time" },
  { value: "internship", label: "Internship" },
  { value: "co_op", label: "Co-op" },
  { value: "contract", label: "Contract" },
];

const REMOTE_OPTIONS = [
  { value: "remote", label: "Remote" },
  { value: "hybrid", label: "Hybrid" },
  { value: "onsite", label: "Onsite" },
];

const LEVEL_OPTIONS = [
  { value: "intern", label: "Intern" },
  { value: "entry", label: "Entry-level" },
  { value: "mid", label: "Mid-level" },
  { value: "senior", label: "Senior" },
  { value: "lead", label: "Lead" },
];

const COMPANY_TIER_OPTIONS = [
  { value: "top", label: "Top-tier" },
  { value: "strong", label: "Strong" },
  { value: "standard", label: "Standard" },
  { value: "unknown", label: "Unknown" },
];

const VISA_TIER_OPTIONS = [
  { value: "likely", label: "Likely" },
  { value: "possible", label: "Possible" },
  { value: "unlikely", label: "Unlikely" },
  { value: "unknown", label: "Unknown" },
  { value: "not_applicable", label: "Not needed" },
];

const SORT_OPTIONS = [
  { value: "composite", label: "Best match", help: "Balanced score across fit, company quality, sponsorship, and freshness." },
  { value: "fit", label: "Your fit", help: "Roles that most closely match your profile and skills." },
  { value: "urgency", label: "Newest / urgent", help: "Fresh postings and roles with urgency signals." },
  { value: "posted", label: "Newest posting", help: "Sort by posting date when it is available." },
];

const ELIGIBILITY_LABELS: Record<string, string> = {
  compatible: "Compatible",
  uncertain: "Uncertain",
  review_required: "Review",
  likely_blocked: "Likely blocked",
};

const TRUST_LABELS: Record<string, string> = {
  verified_source: "Verified source",
  low_risk: "Low risk",
  review_recommended: "Review source",
  suspicious_signals: "Review safety",
  unknown_source: "Unknown source",
};

const APPLICATION_STATUS_OPTIONS: { key: ApplicationStatus; label: string }[] = [
  { key: "saved", label: "Saved" },
  { key: "applied", label: "Applied" },
  { key: "interviewing", label: "Interviewing" },
  { key: "offer", label: "Offer" },
  { key: "rejected", label: "Rejected" },
  { key: "archived", label: "Archived" },
];

function badgeClass(kind: "eligibility" | "trust", value?: string) {
  if (kind === "eligibility") {
    if (value === "compatible") return "badge bg-emerald-50 text-emerald-700";
    if (value === "likely_blocked") return "badge bg-rose-50 text-rose-700";
    if (value === "review_required") return "badge bg-amber-50 text-amber-800";
    return "badge bg-slate-100 text-slate-700";
  }
  if (value === "verified_source" || value === "low_risk") return "badge bg-emerald-50 text-emerald-700";
  if (value === "suspicious_signals") return "badge bg-rose-50 text-rose-700";
  if (value === "review_recommended") return "badge bg-amber-50 text-amber-800";
  return "badge bg-slate-100 text-slate-700";
}

function runEventMessage(item: any) {
  const cache = item?.cache?.status ? ` (${item.cache.status})` : "";
  const label = RUN_STAGE_LABELS[item?.stage || ""] || item?.stage || "Run";
  return `${label}${item?.message ? `: ${item.message}` : ""}${cache}`;
}

function locationQuery(value: string) {
  return value.split(",").map((item) => item.trim()).filter(Boolean).join(", ");
}

function sourceAttemptsFromSummary(summary?: SourceSummary | null) {
  const details = summary?.details || {};
  const attempts = Object.values(details);
  const hasJobSpySiteRows = attempts.some((item) => item.type === "jobspy_site");
  const visible = hasJobSpySiteRows
    ? attempts.filter((item) => item.type !== "jobspy_bundle")
    : attempts;
  return visible.sort((a, b) => {
    const aError = a.status === "error" || a.error ? 1 : 0;
    const bError = b.status === "error" || b.error ? 1 : 0;
    if (aError !== bError) return bError - aError;
    return (b.count || 0) - (a.count || 0);
  });
}

function normalizeLevelFilter(value: string) {
  return value === "new_grad" ? "entry" : value;
}

export default function JobsClient() {
  const params = useSearchParams();
  const initialId = params.get("id");
  const initialQuery = params.get("q") || "";
  const initialCompany = params.get("company") || "";
  const [q, setQ] = useState(initialQuery);
  const [company, setCompany] = useState(initialCompany);
  const [searchLocations, setSearchLocations] = useState("United States");
  const [useJobSpy, setUseJobSpy] = useState(true);
  const [useCache, setUseCache] = useState(false);
  const [searchIntent, setSearchIntent] = useState<SearchIntent>("match");
  const [resultLimit, setResultLimit] = useState("200");
  const [employment, setEmployment] = useState("");
  const [level, setLevel] = useState("");
  const [remote, setRemote] = useState("");
  const [sort, setSort] = useState<"composite" | "posted" | "fit" | "urgency">("composite");
  const [page, setPage] = useState(1);
  const [data, setData] = useState<ListResp | null>(null);
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState<Job | null>(null);
  const [showAdvanced, setShowAdvanced] = useState(true);
  const [companyTier, setCompanyTier] = useState("");
  const [visaTier, setVisaTier] = useState("");
  const [salaryFloor, setSalaryFloor] = useState<string>("");
  const [postedWithin, setPostedWithin] = useState<string>("");
  const [hasContacts, setHasContacts] = useState<"" | "true" | "false">("");
  const [saveMsg, setSaveMsg] = useState("");
  const [runBusy, setRunBusy] = useState(false);
  const [runMsg, setRunMsg] = useState("");
  const [runProgress, setRunProgress] = useState(0);
  const [activeRunId, setActiveRunId] = useState<number | null>(null);
  const [resultRunId, setResultRunId] = useState<number | null>(null);
  const [selectedApplication, setSelectedApplication] = useState<ApplicationRecord | null>(null);
  const [selectedNotes, setSelectedNotes] = useState<NoteRecord[]>([]);
  const [noteDraft, setNoteDraft] = useState("");
  const [detailBusy, setDetailBusy] = useState(false);
  const [detailMsg, setDetailMsg] = useState("");
  const [noteBusy, setNoteBusy] = useState(false);
  const [filtersRestored, setFiltersRestored] = useState(false);
  const [recentRuns, setRecentRuns] = useState<RecentRun[]>([]);
  const [sourceSummary, setSourceSummary] = useState<SourceSummary | null>(null);

  const qs = useMemo(() => {
    const u = new URLSearchParams();
    if (q) u.set("q", q);
    if (company) u.set("company", company);
    const location = locationQuery(searchLocations);
    if (location) u.set("location", location);
    if (employment) u.set("employment_type", employment);
    if (level) u.set("level", level);
    if (remote) u.set("remote_type", remote);
    if (companyTier) u.set("company_tier", companyTier);
    if (visaTier) u.set("visa_tier", visaTier);
    if (salaryFloor) u.set("salary_floor", salaryFloor);
    if (postedWithin) u.set("posted_within_days", postedWithin);
    if (hasContacts) u.set("has_contacts", hasContacts);
    if (resultRunId) u.set("run_id", String(resultRunId));
    u.set("sort", sort);
    u.set("page", String(page));
    u.set("page_size", "50");
    return u.toString();
  }, [q, company, searchLocations, employment, level, remote, companyTier, visaTier, salaryFloor, postedWithin, hasContacts, resultRunId, sort, page]);

  const activeFilterCount = useMemo(() => [
    company,
    employment,
    level,
    remote,
    companyTier,
    visaTier,
    salaryFloor,
    postedWithin,
    hasContacts,
  ].filter(Boolean).length, [company, employment, level, remote, companyTier, visaTier, salaryFloor, postedWithin, hasContacts]);

  const totalPages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;
  const sourceAttempts = useMemo(() => sourceAttemptsFromSummary(sourceSummary), [sourceSummary]);
  const sourceErrorCount = sourceAttempts.filter((item) => item.status === "error" || item.error).length;
  const sourceTotalCount = sourceAttempts.reduce((sum, item) => sum + (item.count || 0), 0);

  async function load() {
    setLoading(true);
    try {
      const d = await api<ListResp>(`/api/jobs?${qs}`);
      setData(d);
    } finally {
      setLoading(false);
    }
  }

  async function loadRecentRuns() {
    try {
      const data = await api<{ items: RecentRun[] }>("/api/runs?limit=8");
      setRecentRuns(data.items || []);
    } catch {}
  }

  async function loadRunSnapshot(runId: number) {
    try {
      const snapshot = await api<RunDetail>(`/api/runs/${runId}`);
      setSourceSummary(snapshot.source_summary || null);
      return snapshot;
    } catch {
      return null;
    }
  }
  useEffect(() => {
    if (!filtersRestored) return;
    load();
    // eslint-disable-next-line
  }, [qs, filtersRestored]);

  useEffect(() => {
    if (initialId) openDetail(parseInt(initialId));
    // eslint-disable-next-line
  }, [initialId]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    try {
      const saved = JSON.parse(window.localStorage.getItem(FILTER_STORAGE_KEY) || "null");
      if (saved && typeof saved === "object") {
        if (!initialQuery && typeof saved.q === "string") setQ(saved.q);
        if (!initialCompany && typeof saved.company === "string") setCompany(saved.company);
        if (typeof saved.searchLocations === "string") setSearchLocations(saved.searchLocations);
        if (typeof saved.useJobSpy === "boolean") setUseJobSpy(saved.useJobSpy);
        if (typeof saved.useCache === "boolean") setUseCache(saved.useCache);
        if (["explore", "match", "strict"].includes(saved.searchIntent)) setSearchIntent(saved.searchIntent);
        if (typeof saved.resultLimit === "string") setResultLimit(saved.resultLimit);
        if (typeof saved.employment === "string") setEmployment(saved.employment);
        if (typeof saved.level === "string") setLevel(normalizeLevelFilter(saved.level));
        if (typeof saved.remote === "string") setRemote(saved.remote);
        if (typeof saved.companyTier === "string") setCompanyTier(saved.companyTier);
        if (typeof saved.visaTier === "string") setVisaTier(saved.visaTier);
        if (typeof saved.salaryFloor === "string") setSalaryFloor(saved.salaryFloor);
        if (typeof saved.postedWithin === "string") setPostedWithin(saved.postedWithin);
        if (typeof saved.hasContacts === "string") setHasContacts(saved.hasContacts);
        if (saved.showAdvanced === true) setShowAdvanced(true);
      }
    } catch {}
    const stored = window.localStorage.getItem(ACTIVE_RUN_STORAGE_KEY);
    const runId = stored ? Number(stored) : 0;
    if (runId > 0) attachRunStream(runId, { resume: true });
    const storedResultRun = Number(window.localStorage.getItem(RESULT_RUN_STORAGE_KEY) || 0);
    if (storedResultRun > 0) {
      setResultRunId(storedResultRun);
      loadRunSnapshot(storedResultRun);
    }
    loadRecentRuns();
    setFiltersRestored(true);
    // eslint-disable-next-line
  }, []);

  useEffect(() => {
    if (!filtersRestored || typeof window === "undefined") return;
    window.localStorage.setItem(FILTER_STORAGE_KEY, JSON.stringify({
      q,
      company,
      searchLocations,
      useJobSpy,
      useCache,
      searchIntent,
      resultLimit,
      employment,
      level,
      remote,
      companyTier,
      visaTier,
      salaryFloor,
      postedWithin,
      hasContacts,
      showAdvanced,
    }));
  }, [filtersRestored, q, company, searchLocations, useJobSpy, useCache, searchIntent, resultLimit, employment, level, remote, companyTier, visaTier, salaryFloor, postedWithin, hasContacts, showAdvanced]);

  function rememberResultRun(runId: number) {
    setResultRunId(runId);
    if (typeof window !== "undefined") {
      window.localStorage.setItem(RESULT_RUN_STORAGE_KEY, String(runId));
    }
  }

  function clearResultRun() {
    setResultRunId(null);
    setSourceSummary(null);
    if (typeof window !== "undefined") {
      window.localStorage.removeItem(RESULT_RUN_STORAGE_KEY);
    }
    setPage(1);
  }

  function applyRunSearchState(search: any) {
    if (search?.query) setQ(search.query);
    if (Array.isArray(search?.locations) && search.locations.length) {
      setSearchLocations(search.locations.join(", "));
    }
    if (Array.isArray(search?.sources)) {
      setUseJobSpy(search.sources.includes("jobspy"));
    }
    if (["explore", "match", "strict"].includes(search?.intent)) setSearchIntent(search.intent);
    if (search?.results_per_source) setResultLimit(String(search.results_per_source));
    if (typeof search?.use_cache === "boolean") setUseCache(search.use_cache);
    if (search?.posted_within_days) setPostedWithin(String(search.posted_within_days));
  }

  function showRunResults(run: RecentRun) {
    const search = run.stats?.search || run.search;
    applyRunSearchState(search);
    setSourceSummary(run.source_summary || null);
    if (run.status === "completed") {
      rememberResultRun(run.id);
      setRunProgress(100);
      setRunMsg(formatRunDone(run.totals || run.stats?.totals));
      setPage(1);
      return;
    }
    attachRunStream(run.id, { resume: true });
  }

  function clearStoredRun(runId: number) {
    if (typeof window === "undefined") return;
    if (window.localStorage.getItem(ACTIVE_RUN_STORAGE_KEY) === String(runId)) {
      window.localStorage.removeItem(ACTIVE_RUN_STORAGE_KEY);
    }
  }

  function applyRunEvent(item: any) {
    setRunMsg(runEventMessage(item));
    setRunProgress((current) => Math.max(current, RUN_STAGE_PROGRESS[item?.stage || ""] || current));
  }

  function formatRunDone(totals: any) {
    if (!totals || typeof totals !== "object") return "done";
    const persisted = totals.persisted ?? 0;
    const ranked = totals.ranked ?? 0;
    return `done: ${persisted} found, ${ranked} ranked`;
  }

  function clearFilters() {
    setCompany("");
    setEmployment("");
    setLevel("");
    setRemote("");
    setCompanyTier("");
    setVisaTier("");
    setSalaryFloor("");
    setPostedWithin("");
    setHasContacts("");
    setPage(1);
  }

  async function attachRunStream(runId: number, options: { resume?: boolean } = {}) {
    setActiveRunId(runId);
    setRunBusy(true);
    if (typeof window !== "undefined") {
      window.localStorage.setItem(ACTIVE_RUN_STORAGE_KEY, String(runId));
    }
    try {
      const snapshot = await loadRunSnapshot(runId);
      if (!snapshot) throw new Error("run not found");
      const search = snapshot.stats?.search || snapshot.search;
      applyRunSearchState(search);
      const lastEvent = (snapshot.stats?.events || []).at(-1);
      if (lastEvent) {
        applyRunEvent(lastEvent);
      } else {
        setRunMsg(`${options.resume ? "resuming" : "run"} #${runId}: ${snapshot.status}`);
      }
      if (["completed", "failed", "skipped"].includes(snapshot.status)) {
        clearStoredRun(runId);
        setRunBusy(false);
        setActiveRunId(null);
        if (snapshot.status === "completed") {
          rememberResultRun(runId);
          setSourceSummary(snapshot.source_summary || null);
          setRunProgress(100);
          setRunMsg(formatRunDone(snapshot.stats?.totals));
          setPage(1);
        } else {
          setRunMsg(`${snapshot.status}: ${JSON.stringify(snapshot.error || {})}`);
        }
        return;
      }
    } catch (e: any) {
      setRunMsg(`error resuming run #${runId}: ${e.message}`);
    }

    const es = new EventSource(`${API_BASE}/api/runs/${runId}/events`);
    es.onmessage = (event) => {
      try {
        applyRunEvent(JSON.parse(event.data));
      } catch {}
    };
    es.addEventListener("done", (event: MessageEvent) => {
      let done: any = null;
      try {
        done = JSON.parse(event.data);
        setRunMsg(formatRunDone(done.totals));
      } catch {
        setRunMsg("done");
      }
      clearStoredRun(runId);
      rememberResultRun(runId);
      es.close();
      setRunBusy(false);
      setActiveRunId(null);
      setRunProgress(100);
      setPage(1);
      loadRunSnapshot(runId);
      loadRecentRuns();
    });
    es.onerror = () => {
      es.close();
      setRunBusy(false);
      setRunMsg(`Run #${runId} is still running in the background. Reopen Jobs to reconnect.`);
    };
  }

  async function openDetail(id: number) {
    const preview = data?.items.find((item) => item.id === id) || null;
    if (preview) setSelected(preview);
    setSelectedApplication(null);
    setSelectedNotes([]);
    setNoteDraft("");
    setDetailMsg("");
    setDetailBusy(true);
    try {
      const j = await api<Job>(`/api/jobs/${id}`);
      setSelected(j);
      const [applications, notes] = await Promise.all([
        api<{ items: ApplicationRecord[] }>("/api/applications"),
        api<NoteRecord[]>(`/api/notes?job_id=${id}`),
      ]);
      setSelectedApplication((applications.items || []).find((item) => item.job_id === id) || null);
      setSelectedNotes(notes || []);
    } catch (e: any) {
      setDetailMsg(`error: ${e.message}`);
    } finally {
      setDetailBusy(false);
    }
  }

  async function updateApplication(status: ApplicationStatus) {
    if (!selected) return;
    try {
      const payload = { status, portal_url: selected.url };
      const application = selectedApplication
        ? await api<ApplicationRecord>(`/api/applications/${selectedApplication.id}`, {
            method: "PATCH",
            body: JSON.stringify(payload),
          })
        : await api<ApplicationRecord>("/api/applications", {
            method: "POST",
            body: JSON.stringify({ job_id: selected.id, ...payload }),
          });
      setSelectedApplication(application);
      const label = APPLICATION_STATUS_OPTIONS.find((option) => option.key === status)?.label || status;
      setSaveMsg(`Marked ${label.toLowerCase()}`);
      setDetailMsg(`Application status: ${label}.`);
      setTimeout(() => setSaveMsg(""), 2000);
    } catch (e: any) {
      setSaveMsg(`error: ${e.message}`);
      setDetailMsg(`error: ${e.message}`);
    }
  }

  async function addNote() {
    if (!selected || !noteDraft.trim()) return;
    setNoteBusy(true);
    try {
      const created = await api<NoteRecord>("/api/notes", {
        method: "POST",
        body: JSON.stringify({ job_id: selected.id, body: noteDraft.trim() }),
      });
      setSelectedNotes((prev) => [created, ...prev]);
      setNoteDraft("");
      setDetailMsg("Note added.");
    } catch (e: any) {
      setDetailMsg(`error: ${e.message}`);
    } finally {
      setNoteBusy(false);
    }
  }

  async function runSearch() {
    const query = q.trim();
    if (!query) {
      setRunMsg("Enter a role or keyword first.");
      return;
    }
    const sources = [
      useJobSpy ? "jobspy" : null,
    ].filter(Boolean) as string[];
    if (sources.length === 0) {
      setRunMsg("Select at least one source.");
      return;
    }
    const locations = searchLocations
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean);
    setRunBusy(true);
    setRunProgress(4);
    setRunMsg("starting...");
    setSourceSummary(null);
    try {
      const requestedLimit = Math.min(1000, Math.max(10, Number(resultLimit) || 200));
      const payload: Record<string, any> = {
        query,
        intent: searchIntent,
        locations: locations.length ? locations : ["United States"],
        sources,
        results_per_source: requestedLimit,
        use_cache: useCache,
      };
      if (postedWithin) payload.posted_within_days = Number(postedWithin);
      const { run_id } = await api<{ run_id: number }>("/api/search/run", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      await attachRunStream(run_id);
    } catch (e: any) {
      setRunMsg(`error: ${e.message}`);
      setRunBusy(false);
    }
  }

  return (
    <div className="grid gap-5">
      <section className="relative overflow-hidden rounded-[28px] border border-white/70 bg-white/75 p-4 shadow-card backdrop-blur-xl sm:p-5">
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div className="min-w-0">
            <div className="text-xs font-semibold uppercase tracking-[0.16em] text-brand-600">Job search</div>
            <h1 className="mt-1 text-2xl font-semibold tracking-tight text-ink-900 sm:text-3xl">Find roles worth applying to</h1>
            <p className="mt-1 max-w-2xl text-sm text-ink-500">
              Search broad job sites, then narrow the list with plain-language filters and local ranking.
            </p>
          </div>
          <div className="flex items-center gap-2">
            {saveMsg && <span className="badge-mint">{saveMsg}</span>}
            {resultRunId && <span className="badge-sky">Run #{resultRunId}</span>}
          </div>
        </div>

        <div className="mt-5 grid gap-4">
        <div className="grid lg:grid-cols-[minmax(220px,1.5fr)_minmax(170px,0.9fr)_140px_auto] gap-3">
          <FieldGroup label="Role or keyword">
            <input className="input" placeholder="AI engineer, data analyst, backend intern"
                   value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} />
          </FieldGroup>
          <FieldGroup label="Search location">
            <input className="input" placeholder="United States, Remote, New York"
                   value={searchLocations} onChange={(e) => setSearchLocations(e.target.value)} />
          </FieldGroup>
          <FieldGroup label="Search size">
            <select className="select" value={resultLimit} onChange={(e) => setResultLimit(e.target.value)}>
              {SEARCH_RESULT_LIMIT_OPTIONS.map((option) => (
                <option key={option} value={option}>{option} jobs</option>
              ))}
            </select>
          </FieldGroup>
          <div className="flex items-end">
            <button className="btn-primary whitespace-nowrap w-full lg:w-auto" disabled={runBusy} onClick={runSearch}>
              {runBusy ? "Running..." : "Run search"}
            </button>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-3 text-xs text-ink-500">
          <label className="inline-flex items-center gap-1.5">
            <input type="checkbox" checked={useJobSpy} onChange={(e) => setUseJobSpy(e.target.checked)} />
            Broad web search
          </label>
          <label className="inline-flex items-center gap-1.5">
            <input type="checkbox" checked={useCache} onChange={(e) => setUseCache(e.target.checked)} />
            Reuse cache
          </label>
          <span className="badge-sky">LinkedIn, Indeed, Glassdoor, ZipRecruiter, Google</span>
          <span className="badge-ink">Tracked company boards live on Dashboard</span>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs font-semibold uppercase tracking-[0.14em] text-ink-500">Mode</span>
          <div className="inline-flex rounded-full border border-ink-300/20 bg-white/75 p-1 shadow-sm">
            {SEARCH_INTENT_OPTIONS.map((option) => {
              const active = searchIntent === option.value;
              return (
                <button
                  key={option.value}
                  type="button"
                  aria-pressed={active}
                  title={option.help}
                  className={`rounded-full px-3 py-1.5 text-xs font-medium transition ${active ? "bg-ink-900 text-white shadow-sm" : "text-ink-600 hover:bg-ink-50"}`}
                  onClick={() => setSearchIntent(option.value)}
                >
                  {option.label}
                </button>
              );
            })}
          </div>
        </div>

        {runMsg && (
          <div className="rounded-2xl border border-sky-100 bg-sky-50/80 px-3 py-3 text-xs text-sky-900 break-words whitespace-normal">
            <div className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-2 font-medium">
                {runBusy && <span className="h-3 w-3 rounded-full border-2 border-sky-200 border-t-sky-700 animate-spin" />}
                <span>{activeRunId ? `Run #${activeRunId}` : resultRunId ? `Run #${resultRunId}` : "Search"}</span>
              </div>
              <span className="tabular-nums">{runProgress}%</span>
            </div>
            <div className="mt-2 h-1.5 rounded-full bg-sky-100 overflow-hidden">
              <div className="h-full rounded-full bg-sky-600 transition-all" style={{ width: `${runProgress}%` }} />
            </div>
            <div className="mt-2">{runMsg}</div>
          </div>
        )}

        <div className="rounded-2xl border border-ink-300/20 bg-white/70 p-3 grid gap-3">
          <div className="flex items-center justify-between gap-2 flex-wrap">
            <div className="flex items-center gap-2">
              <h2 className="text-sm font-semibold text-ink-900">Filters</h2>
              {activeFilterCount > 0 && <span className="badge-ink">{activeFilterCount}</span>}
            </div>
            <div className="flex items-center gap-2">
              <button className="btn-secondary text-xs" onClick={() => setShowAdvanced(v => !v)}>
                {showAdvanced ? "Fewer filters" : "More filters"}
              </button>
              {activeFilterCount > 0 && (
                <button className="btn-secondary text-xs" onClick={clearFilters}>Clear filters</button>
              )}
            </div>
          </div>
          <div className="grid md:grid-cols-3 xl:grid-cols-6 gap-2">
            <FieldGroup label="Company">
              <input className="input" placeholder="Any company"
                     value={company} onChange={(e) => { setCompany(e.target.value); setPage(1); }} />
            </FieldGroup>
            <FieldGroup label="Job type">
              <select className="select" value={employment} onChange={(e) => { setEmployment(e.target.value); setPage(1); }}>
                <option value="">Any job type</option>
                {EMPLOYMENT_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>{option.label}</option>
                ))}
              </select>
            </FieldGroup>
            <FieldGroup label="Location type">
              <select className="select" value={remote} onChange={(e) => { setRemote(e.target.value); setPage(1); }}>
                <option value="">Any location type</option>
                {REMOTE_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>{option.label}</option>
                ))}
              </select>
            </FieldGroup>
            <FieldGroup label="Level">
              <select className="select" value={level} onChange={(e) => { setLevel(e.target.value); setPage(1); }}>
                <option value="">Any level</option>
                {LEVEL_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>{option.label}</option>
                ))}
              </select>
            </FieldGroup>
            <FieldGroup label="Sponsorship">
              <select className="select" value={visaTier} onChange={(e) => { setVisaTier(e.target.value); setPage(1); }}>
                <option value="">Any sponsorship</option>
                {VISA_TIER_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>{option.label}</option>
                ))}
              </select>
            </FieldGroup>
            <FieldGroup label="Company strength">
              <select className="select" value={companyTier} onChange={(e) => { setCompanyTier(e.target.value); setPage(1); }}>
                <option value="">Any strength</option>
                {COMPANY_TIER_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>{option.label}</option>
                ))}
              </select>
            </FieldGroup>
          </div>
          {showAdvanced && (
            <div className="grid md:grid-cols-3 gap-2">
              <FieldGroup label="Salary floor">
                <input className="input" placeholder="USD minimum" type="number"
                       value={salaryFloor} onChange={(e) => { setSalaryFloor(e.target.value); setPage(1); }} />
              </FieldGroup>
              <FieldGroup label="Posted in last">
                <input className="input" placeholder="Days, e.g. 30"
                       type="number" value={postedWithin} onChange={(e) => { setPostedWithin(e.target.value); setPage(1); }} />
              </FieldGroup>
              <FieldGroup label="Contacts">
                <select className="select" value={hasContacts}
                        onChange={(e) => { setHasContacts(e.target.value as any); setPage(1); }}>
                  <option value="">Any contacts</option>
                  <option value="true">Has contacts</option>
                  <option value="false">No contacts</option>
                </select>
              </FieldGroup>
            </div>
          )}
        </div>
        </div>
      </section>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
        <section className="grid gap-3 min-w-0">
          <div className="rounded-2xl border border-white/70 bg-white/80 p-4 shadow-card backdrop-blur-xl">
            <div className="flex items-start justify-between gap-4 flex-wrap">
              <div>
                <h2 className="text-lg font-semibold text-ink-900">Results</h2>
                <p className="mt-1 text-sm text-ink-500">
                  {data ? `${data.total} matching job${data.total === 1 ? "" : "s"}` : loading ? "Loading jobs..." : "Run a search or adjust filters to begin."}
                  {resultRunId ? ` Showing search run #${resultRunId}.` : ""}
                </p>
              </div>
              <div className="flex items-center gap-2">
                {resultRunId && <button className="btn-secondary text-xs" onClick={clearResultRun}>All local jobs</button>}
                <select
                  className="select w-[180px]"
                  value={sort}
                  onChange={(e) => setSort(e.target.value as any)}
                  title={SORT_OPTIONS.find((option) => option.value === sort)?.help}
                >
                  {SORT_OPTIONS.map((option) => (
                    <option key={option.value} value={option.value}>{option.label}</option>
                  ))}
                </select>
              </div>
            </div>
          </div>

          <div className="grid gap-3">
            {loading && !data && Array.from({ length: 5 }).map((_, index) => <LoadingJobCard key={index} />)}
            {!loading && data?.items.map((job) => (
              <JobResultCard key={job.id} job={job} onOpen={() => openDetail(job.id)} />
            ))}
            {!loading && data && data.items.length === 0 && <EmptyResults onClearFilters={clearFilters} hasFilters={activeFilterCount > 0} />}
          </div>
        </section>

        <aside className="grid gap-4 content-start min-w-0">
          {sourceSummary && (
            <SearchCoverageCard
              attempts={sourceAttempts}
              summary={sourceSummary}
              sourceErrorCount={sourceErrorCount}
              sourceTotalCount={sourceTotalCount}
            />
          )}

          {recentRuns.length > 0 && (
            <div className="rounded-2xl border border-white/70 bg-white/80 p-4 shadow-card backdrop-blur-xl">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <h2 className="text-sm font-semibold text-ink-900">Search history</h2>
                  <p className="text-xs text-ink-500">Reload a previous run without losing context.</p>
                </div>
                <button className="btn-secondary text-xs" onClick={loadRecentRuns}>Refresh</button>
              </div>
              <div className="mt-3 grid gap-2">
                {recentRuns.slice(0, 5).map((run) => (
                  <button
                    key={run.id}
                    className="rounded-xl border border-ink-300/30 bg-white/70 px-3 py-2 text-left hover:border-brand-200 hover:bg-brand-50/50 transition"
                    onClick={() => showRunResults(run)}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <div className="font-medium text-sm text-ink-900 truncate">{runSearchLabel(run)}</div>
                        <div className="text-xs text-ink-500 mt-0.5 truncate">{runLocationLabel(run)}</div>
                      </div>
                      <span className={runStatusClass(run.status)}>{run.status}</span>
                    </div>
                    <div className="flex flex-wrap items-center gap-2 mt-2 text-xs text-ink-500">
                      <span>Run #{run.id}</span>
                      <span>{searchIntentLabel((run.stats?.search || run.search)?.intent)}</span>
                      <span>{runTotalsLabel(run)}</span>
                      <span>{runCacheLabel(run)}</span>
                      {runSourceErrorCount(run) > 0 && <span className="text-amber-700">{runSourceErrorCount(run)} source issue{runSourceErrorCount(run) === 1 ? "" : "s"}</span>}
                    </div>
                  </button>
                ))}
              </div>
            </div>
          )}
        </aside>
      </div>

      {data && data.total > data.page_size && (
        <div className="flex items-center justify-center gap-2">
          <button className="btn-secondary" disabled={page === 1} onClick={() => setPage(page - 1)}>Prev</button>
          <span className="text-sm text-slate-600">Page {data.page} of {totalPages}</span>
          <button className="btn-secondary"
                  disabled={page * data.page_size >= data.total}
                  onClick={() => setPage(page + 1)}>Next</button>
        </div>
      )}

      {selected && (
        <div className="fixed inset-0 bg-ink-900/45 backdrop-blur-sm z-40" onClick={() => setSelected(null)}>
          <div
            role="dialog"
            aria-modal="true"
            aria-label={selected.title}
            className="absolute right-0 top-0 h-full w-full max-w-5xl bg-white/95 shadow-2xl overflow-y-auto p-4 sm:p-6"
               onClick={(e) => e.stopPropagation()}>
            <div className="sticky -top-4 z-10 -mx-4 -mt-4 border-b border-ink-300/20 bg-white/90 px-4 py-4 backdrop-blur-xl sm:-top-6 sm:-mx-6 sm:-mt-6 sm:px-6">
              <div className="flex items-start justify-between gap-4">
                <div className="min-w-0">
                  <div className="text-xs font-semibold uppercase tracking-[0.16em] text-brand-600">Job detail</div>
                  <h2 className="mt-1 text-xl font-semibold leading-tight text-ink-900 sm:text-2xl">{selected.title}</h2>
                  <div className="mt-1 text-sm text-ink-500">
                    {selected.company?.name || "Unknown company"} - {selected.location.raw || "Location unknown"}
                  </div>
                </div>
                <div className="flex shrink-0 flex-wrap items-center justify-end gap-2">
                  {detailBusy && (
                    <span className="inline-flex items-center gap-1.5 text-xs text-sky-700">
                      <span className="h-3 w-3 rounded-full border-2 border-sky-200 border-t-sky-700 animate-spin" />
                      Loading
                    </span>
                  )}
                  {selected.url && (
                    <a className="btn-primary" href={selected.url} target="_blank" rel="noreferrer">
                      Open posting
                    </a>
                  )}
                  <button className="btn-secondary" onClick={() => setSelected(null)}>Close</button>
                </div>
              </div>
            </div>

            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mt-4">
              {(["fit", "opportunity", "urgency", "composite"] as const).map((k) => (
                <div key={k} className="card !p-3">
                  <div className="text-xs uppercase text-slate-500">{scoreLabel(k)}</div>
                  <div className="text-xl font-semibold">
                    {selected.ranking ? formatScore((selected.ranking as any)[k]) : "--"}
                  </div>
                </div>
              ))}
            </div>

            <div className="mt-4 grid gap-2">
              <div className="flex flex-wrap gap-2 text-xs">
                {selected.employment_type && <span className="badge bg-slate-100 text-slate-700">{employmentLabel(selected.employment_type)}</span>}
                {selected.level_guess && <span className="badge bg-slate-100 text-slate-700">{levelLabel(selected.level_guess)}</span>}
                {selected.location.remote_type && <span className="badge bg-slate-100 text-slate-700">{remoteLabel(selected.location.remote_type)}</span>}
                {selected.salary.min && (
                  <span className="badge bg-emerald-50 text-emerald-700">
                    {formatSalaryRange(selected.salary)}
                  </span>
                )}
                {selectedApplication && (
                  <span className={applicationBadgeClass(selectedApplication.status)}>
                    {applicationLabel(selectedApplication.status)}
                  </span>
                )}
              </div>
              {detailMsg && (
                <div className={`text-sm ${detailMsg.startsWith("error:") ? "text-rose-700" : "text-emerald-700"}`}>
                  {detailMsg}
                </div>
              )}
            </div>

            <div className="grid xl:grid-cols-[minmax(0,1.2fr)_minmax(320px,0.8fr)] gap-4 mt-4">
              <div className="space-y-4">
                <div className="card !p-4">
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <div className="font-medium">What should I do next?</div>
                      <div className="text-sm text-slate-600 mt-1">
                        {nextStepMessage(selected, selectedApplication)}
                      </div>
                    </div>
                    {selectedApplication && (
                      <span className={applicationBadgeClass(selectedApplication.status)}>
                        {applicationLabel(selectedApplication.status)}
                      </span>
                    )}
                  </div>
                  <div className="flex flex-wrap gap-2 mt-4">
                    <button className="btn-secondary" disabled={detailBusy} onClick={() => updateApplication("saved")}>Save</button>
                    <button className="btn-secondary" disabled={detailBusy} onClick={() => updateApplication("applied")}>Mark applied</button>
                    <button className="btn-secondary" disabled={detailBusy} onClick={() => updateApplication("archived")}>Skip for now</button>
                  </div>
                  <div className="grid sm:grid-cols-2 gap-2 mt-4 text-xs text-slate-600">
                    <SignalLine label="Status" value={selectedApplication ? applicationLabel(selectedApplication.status) : "Not tracked"} />
                    <SignalLine label="Applied at" value={formatDateTime(selectedApplication?.applied_at)} />
                    <SignalLine label="Saved at" value={formatDateTime(selectedApplication?.created_at)} />
                    <SignalLine label="Next action" value={formatDateTime(selectedApplication?.next_action_at)} />
                  </div>
                  {selectedApplication?.notes_summary && (
                    <div className="mt-3 rounded-xl bg-slate-50 px-3 py-2 text-sm text-slate-700">
                      {selectedApplication.notes_summary}
                    </div>
                  )}
                  <div className="text-xs text-slate-500 mt-3">
                    Apply manually through the original posting. Joby tracks your decision state locally.
                  </div>
                </div>

                <div className="card !p-4">
                  <div className="font-medium">Why is this here?</div>
                  <div className="grid md:grid-cols-3 gap-3 mt-3">
                    <ReasonCard
                      title="Fit"
                      score={selected.ranking?.fit}
                      reasons={selected.ranking?.reason_json?.fit?.reasons}
                      weight={selected.ranking?.reason_json?.weights?.fit}
                      composite={selected.ranking?.composite}
                    />
                    <ReasonCard
                      title="Opportunity"
                      score={selected.ranking?.opportunity}
                      reasons={selected.ranking?.reason_json?.opportunity?.reasons}
                      weight={selected.ranking?.reason_json?.weights?.opportunity}
                      composite={selected.ranking?.composite}
                    />
                    <ReasonCard
                      title="Urgency"
                      score={selected.ranking?.urgency}
                      reasons={selected.ranking?.reason_json?.urgency?.reasons}
                      weight={selected.ranking?.reason_json?.weights?.urgency}
                      composite={selected.ranking?.composite}
                    />
                  </div>
                </div>

                {selected.screening && (
                  <div className="card !p-4">
                    <div className="flex items-center justify-between gap-2">
                      <div className="font-medium">Profile screening</div>
                      <span className={selected.screening.prefilter_passed ? "badge bg-emerald-50 text-emerald-700" : "badge bg-amber-50 text-amber-800"}>
                        {selected.screening.prefilter_passed ? "Prefilter passed" : "Needs review"}
                      </span>
                    </div>
                    <div className="text-sm text-slate-600 mt-2">{llmStatusMessage(selected.screening.llm_status)}</div>
                    <SignalList items={screeningSignals(selected.screening)} />
                  </div>
                )}
              </div>

              <div className="space-y-4">
                <div className="card !p-4">
                  <div className="font-medium">Original source</div>
                  <div className="text-sm text-slate-700 mt-2">{sourceKind(selected.source)} · {sourceLabel(selected.source)}</div>
                  <div className="grid grid-cols-2 gap-2 mt-3 text-xs text-slate-600">
                    <SignalLine label="Host" value={hostFromUrl(selected.url)} />
                    <SignalLine label="Posted" value={formatDateTime(selected.posted_at)} />
                    <SignalLine label="Company tier" value={selected.company?.tier} />
                    <SignalLine label="Source" value={selected.source} />
                  </div>
                </div>

                {(selected.eligibility || selected.trust) && (
                  <div className="grid gap-3">
                    {selected.eligibility && (
                      <div className="card !p-4">
                        <div className="flex items-center justify-between gap-2">
                          <div className="font-medium">Can I apply?</div>
                          <span className={badgeClass("eligibility", selected.eligibility.label)}>
                            {ELIGIBILITY_LABELS[selected.eligibility.label] || selected.eligibility.label}
                          </span>
                        </div>
                        <div className="text-sm text-slate-700 mt-2">{selected.eligibility.summary}</div>
                        <div className="grid grid-cols-2 gap-2 mt-3 text-xs text-slate-600">
                          <SignalLine label="Visa" value={selected.eligibility.sponsorship_signal} />
                          <SignalLine label="Clearance" value={selected.eligibility.clearance_status} />
                          <SignalLine label="Citizenship" value={selected.eligibility.citizenship_status} />
                          <SignalLine label="Location" value={selected.eligibility.location_status} />
                        </div>
                        <SignalList items={selected.eligibility.evidence} />
                      </div>
                    )}

                    {selected.trust && (
                      <div className="card !p-4">
                        <div className="flex items-center justify-between gap-2">
                          <div className="font-medium">Is it safe?</div>
                          <span className={badgeClass("trust", selected.trust.label)}>
                            {TRUST_LABELS[selected.trust.label] || selected.trust.label}
                          </span>
                        </div>
                        <div className="text-sm text-slate-700 mt-2">{selected.trust.summary}</div>
                        <div className="text-xs text-slate-500 mt-2">Score {selected.trust.score.toFixed(2)}</div>
                        <SignalList items={[...(selected.trust.warnings || []), ...(selected.trust.evidence || [])]} />
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>

            <div className="grid xl:grid-cols-[minmax(0,1fr)_minmax(320px,0.9fr)] gap-4 mt-4">
              <div className="card !p-4">
                <div className="font-medium mb-2">Description</div>
                <div className="text-sm text-slate-700 whitespace-pre-wrap">
                  {selected.description_text || "—"}
                </div>
              </div>

              <div className="space-y-4">
                <div className="card !p-4">
                  <div className="font-medium">Contacts</div>
                  <div className="mt-3 space-y-3">
                    {selected.contacts?.length ? selected.contacts.slice(0, 6).map((contact) => (
                      <div key={contact.id} className="rounded-xl border border-slate-200 p-3">
                        <div className="flex items-start justify-between gap-3">
                          <div>
                            <div className="font-medium text-sm text-slate-900">{contact.name || "Unknown contact"}</div>
                            <div className="text-xs text-slate-500 mt-0.5">{contact.title || contact.source || "Contact"}</div>
                          </div>
                          {typeof contact.confidence === "number" && (
                            <span className="badge bg-slate-100 text-slate-700">{contact.confidence.toFixed(2)}</span>
                          )}
                        </div>
                        <div className="flex flex-wrap gap-3 mt-2 text-xs">
                          {contact.email && <a className="text-blue-700 hover:underline" href={`mailto:${contact.email}`}>{contact.email}</a>}
                          {contact.linkedin_url && <a className="text-blue-700 hover:underline" href={contact.linkedin_url} target="_blank" rel="noreferrer">LinkedIn ↗</a>}
                        </div>
                      </div>
                    )) : (
                      <div className="text-sm text-slate-500">No recruiter or hiring contacts surfaced yet.</div>
                    )}
                  </div>
                </div>

                <div className="card !p-4">
                  <div className="font-medium">Notes</div>
                  <div className="space-y-3 mt-3">
                    <textarea
                      className="w-full min-h-[112px] rounded-xl border border-slate-200 px-3 py-2 text-sm outline-none focus:border-slate-400"
                      placeholder="Capture why this role matters, what to verify, or who to contact next."
                      value={noteDraft}
                      onChange={(e) => setNoteDraft(e.target.value)}
                    />
                    <div className="flex items-center justify-between gap-3">
                      <div className="text-xs text-slate-500">Notes stay local to your Joby workspace.</div>
                      <button className="btn-secondary" disabled={noteBusy || !noteDraft.trim()} onClick={addNote}>
                        {noteBusy ? "Saving..." : "Add note"}
                      </button>
                    </div>
                    <div className="space-y-2">
                      {selectedNotes.length ? selectedNotes.slice(0, 5).map((note) => (
                        <div key={note.id} className="rounded-xl bg-slate-50 px-3 py-2">
                          <div className="text-xs text-slate-500">{formatDateTime(note.updated_at)}</div>
                          <div className="text-sm text-slate-700 whitespace-pre-wrap mt-1">{note.body}</div>
                        </div>
                      )) : (
                        <div className="text-sm text-slate-500">No notes yet for this job.</div>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <details className="card mt-4 !p-4">
              <summary className="cursor-pointer font-medium text-slate-900">Raw model details</summary>
              <div className="grid lg:grid-cols-2 gap-3 mt-4">
                {selected.ranking?.reason_json && (
                  <div>
                    <div className="text-sm font-medium mb-2">Ranking JSON</div>
                    <pre className="text-xs whitespace-pre-wrap text-slate-700 rounded-xl bg-slate-50 p-3">
{JSON.stringify(selected.ranking.reason_json, null, 2)}
                    </pre>
                  </div>
                )}
                {selected.screening && (
                  <div>
                    <div className="text-sm font-medium mb-2">Screening JSON</div>
                    <pre className="text-xs whitespace-pre-wrap text-slate-700 rounded-xl bg-slate-50 p-3">
{JSON.stringify({
  prefilter_passed: selected.screening.prefilter_passed,
  llm_status: selected.screening.llm_status,
  prefilter_reasons: selected.screening.prefilter_reasons,
  screening_json: selected.screening.screening_json,
}, null, 2)}
                    </pre>
                  </div>
                )}
              </div>
            </details>
          </div>
        </div>
      )}
    </div>
  );
}

function JobResultCard({ job, onOpen }: { job: Job; onOpen: () => void }) {
  const score = job.ranking?.composite;
  const fit = job.ranking?.fit;
  const opportunity = job.ranking?.opportunity;
  const urgency = job.ranking?.urgency;
  const sponsorship = sponsorshipLabel(job.eligibility?.visa_tier || job.eligibility?.sponsorship_signal);

  return (
    <button
      type="button"
      onClick={onOpen}
      className="group rounded-2xl border border-white/70 bg-white/85 p-4 text-left shadow-card backdrop-blur-xl transition hover:-translate-y-0.5 hover:border-brand-200 hover:shadow-ring focus:outline-none focus:ring-2 focus:ring-brand-300"
    >
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(210px,0.34fr)] lg:items-start">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2 text-xs text-ink-500">
            <span className="font-medium text-brand-700">{sourceLabel(job.source)}</span>
            {job.posted_at && <span>{postedLabel(job.posted_at)}</span>}
            {job.employment_type && <span>{employmentLabel(job.employment_type)}</span>}
          </div>
          <div className="mt-2 flex items-start justify-between gap-3">
            <div className="min-w-0">
              <h3 className="text-base font-semibold leading-snug text-ink-900 group-hover:text-brand-700 sm:text-lg">{job.title}</h3>
              <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-ink-600">
                <span className="font-medium text-ink-800">{job.company?.name || "Unknown company"}</span>
                <span>{job.location.raw || "Location unknown"}</span>
              </div>
            </div>
            <ScoreBadge score={score} />
          </div>

          <div className="mt-3 flex flex-wrap gap-2">
            {job.level_guess && <span className="badge-ink">{levelLabel(job.level_guess)}</span>}
            {job.location.remote_type && job.location.remote_type !== "unknown" && <span className="badge-sky">{remoteLabel(job.location.remote_type)}</span>}
            {sponsorship && <span className="badge-mint">Sponsorship: {sponsorship}</span>}
            {job.company?.tier && <span className="badge-ink">{companyStrengthLabel(job.company.tier)}</span>}
            {formatSalaryRange(job.salary) && <span className="badge-mint">{formatSalaryRange(job.salary)}</span>}
            {job.eligibility && (
              <span className={badgeClass("eligibility", job.eligibility.label)}>
                {ELIGIBILITY_LABELS[job.eligibility.label] || job.eligibility.label}
              </span>
            )}
          </div>

          {job.eligibility?.summary && (
            <p className="mt-3 line-clamp-2 text-sm text-ink-500">{job.eligibility.summary}</p>
          )}
        </div>

        <div className="grid gap-2 rounded-2xl bg-ink-300/10 p-3">
          <MiniScore label="Fit" value={fit} />
          <MiniScore label="Opportunity" value={opportunity} />
          <MiniScore label="Freshness" value={urgency} />
        </div>
      </div>
    </button>
  );
}

function ScoreBadge({ score }: { score?: number }) {
  return (
    <div className="shrink-0 rounded-2xl border border-ink-300/20 bg-white px-3 py-2 text-center shadow-sm">
      <div className="text-[10px] font-semibold uppercase tracking-wider text-ink-400">Match</div>
      <div className="text-lg font-semibold tabular-nums text-ink-900">{formatScore(score)}</div>
    </div>
  );
}

function MiniScore({ label, value }: { label: string; value?: number }) {
  return (
    <div>
      <div className="mb-1 flex items-center justify-between gap-2 text-xs text-ink-500">
        <span>{label}</span>
        <span className="tabular-nums text-ink-700">{formatScore(value)}</span>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-white">
        <div className="h-full rounded-full bg-brand-500" style={{ width: `${scoreWidth(value)}%` }} />
      </div>
    </div>
  );
}

function LoadingJobCard() {
  return (
    <div className="rounded-2xl border border-white/70 bg-white/80 p-4 shadow-card">
      <div className="flex items-start justify-between gap-4">
        <div className="grid flex-1 gap-2">
          <div className="h-4 w-28 rounded bg-ink-300/20 animate-pulse" />
          <div className="h-6 w-2/3 rounded bg-ink-300/20 animate-pulse" />
          <div className="h-4 w-1/2 rounded bg-ink-300/20 animate-pulse" />
        </div>
        <div className="h-14 w-20 rounded-2xl bg-ink-300/20 animate-pulse" />
      </div>
    </div>
  );
}

function EmptyResults({ hasFilters, onClearFilters }: { hasFilters: boolean; onClearFilters: () => void }) {
  return (
    <div className="rounded-2xl border border-dashed border-ink-300/50 bg-white/75 p-8 text-center shadow-card">
      <div className="text-lg font-semibold text-ink-900">No matching jobs yet</div>
      <p className="mx-auto mt-2 max-w-md text-sm text-ink-500">
        Try a broader role, increase search size, or loosen sponsorship and level filters. Joby keeps the run scoped so you can safely explore.
      </p>
      {hasFilters && <button className="btn-secondary mt-4" onClick={onClearFilters}>Clear filters</button>}
    </div>
  );
}

function SearchCoverageCard({
  attempts,
  summary,
  sourceErrorCount,
  sourceTotalCount,
}: {
  attempts: SourceAttempt[];
  summary: SourceSummary;
  sourceErrorCount: number;
  sourceTotalCount: number;
}) {
  return (
    <div className="rounded-2xl border border-white/70 bg-white/80 p-4 shadow-card backdrop-blur-xl">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold text-ink-900">Search coverage</h2>
          <p className="text-xs text-ink-500">Where this run found jobs.</p>
        </div>
        {sourceErrorCount > 0 ? <span className="badge bg-amber-50 text-amber-800">{sourceErrorCount} issue{sourceErrorCount === 1 ? "" : "s"}</span> : <span className="badge-mint">Healthy</span>}
      </div>

      <div className="mt-3 grid grid-cols-2 gap-2 text-xs text-ink-600">
        <SignalLine label="Fetched" value={String(sourceTotalCount)} />
        <SignalLine label="Cache mode" value={cacheSummaryLabel(summary)} />
      </div>

      <div className="mt-3 grid gap-2">
        {attempts.slice(0, 6).map((attempt) => (
          <div key={attempt.key} className="rounded-xl border border-ink-300/20 bg-white/70 px-3 py-2">
            <div className="flex items-center justify-between gap-3">
              <div className="min-w-0">
                <div className="truncate text-sm font-medium text-ink-900">{attempt.label || attempt.key}</div>
                <div className="text-xs text-ink-500">{formatDuration(attempt.duration_ms)} {attempt.cache?.status ? `• ${attempt.cache.status}` : ""}</div>
              </div>
              <div className="text-right">
                <div className="text-sm font-semibold tabular-nums text-ink-900">{attempt.count ?? 0}</div>
                <span className={sourceStatusClass(attempt.status)}>{attempt.status || "unknown"}</span>
              </div>
            </div>
            {attempt.error && <div className="mt-2 text-xs text-rose-700 break-words">{attempt.error}</div>}
          </div>
        ))}
      </div>
    </div>
  );
}

function runSearchLabel(run: RecentRun) {
  const search = run.stats?.search || run.search;
  return search?.query || (run.trigger_type === "search" ? "Search run" : "Tracked board refresh");
}

function searchIntentLabel(intent?: string) {
  return SEARCH_INTENT_OPTIONS.find((option) => option.value === intent)?.label || "Match";
}

function runLocationLabel(run: RecentRun) {
  const search = run.stats?.search || run.search;
  if (Array.isArray(search?.locations) && search.locations.length) return search.locations.join(", ");
  return formatDateTime(run.started_at);
}

function runTotalsLabel(run: RecentRun) {
  const totals = run.totals || run.stats?.totals;
  if (!totals) return "no totals yet";
  return `${totals.persisted ?? 0} found, ${totals.ranked ?? 0} ranked`;
}

function runCacheLabel(run: RecentRun) {
  return cacheSummaryLabel(run.source_summary);
}

function runSourceErrorCount(run: RecentRun) {
  const attempts = sourceAttemptsFromSummary(run.source_summary);
  const attemptErrors = attempts.filter((item) => item.status === "error" || item.error).length;
  const runErrors = Array.isArray(run.error?.errors) ? run.error.errors.length : 0;
  return Math.max(attemptErrors, runErrors);
}

function cacheSummaryLabel(summary?: SourceSummary | null) {
  const cache = summary?.cache;
  if (!cache) return "cache unknown";
  if (cache.used_cache === false || (cache.bypassed || 0) > 0) return "fresh search";
  if ((cache.hit || 0) > 0) return `${cache.hit} cache hit${cache.hit === 1 ? "" : "s"}`;
  if ((cache.miss || 0) > 0) return `${cache.miss} cache miss${cache.miss === 1 ? "" : "es"}`;
  return "cache unused";
}

function runStatusClass(status?: string) {
  if (status === "completed") return "badge bg-emerald-50 text-emerald-700";
  if (status === "failed" || status === "skipped") return "badge bg-rose-50 text-rose-700";
  if (status === "running" || status === "pending") return "badge bg-blue-50 text-blue-700";
  return "badge bg-slate-100 text-slate-700";
}

function sourceStatusClass(status?: string) {
  if (status === "ok") return "badge bg-emerald-50 text-emerald-700";
  if (status === "error") return "badge bg-rose-50 text-rose-700";
  return "badge bg-slate-100 text-slate-700";
}

function formatDuration(value?: number) {
  if (typeof value !== "number") return "—";
  if (value < 1000) return `${value}ms`;
  return `${(value / 1000).toFixed(1)}s`;
}

function FieldGroup({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="grid gap-1 text-xs font-medium text-slate-600">
      <span>{label}</span>
      {children}
    </label>
  );
}

function SignalLine({ label, value }: { label: string; value?: string }) {
  return (
    <div className="rounded-md bg-slate-50 px-2 py-1">
      <div className="uppercase text-[10px] text-slate-400">{label}</div>
      <div>{value || "unknown"}</div>
    </div>
  );
}

function SignalList({ items }: { items?: string[] }) {
  const visible = (items || []).filter(Boolean).slice(0, 6);
  if (!visible.length) return null;
  return (
    <div className="flex flex-wrap gap-1.5 mt-3">
      {visible.map((item) => (
        <span key={item} className="badge bg-slate-100 text-slate-700">{item}</span>
      ))}
    </div>
  );
}

function ReasonCard({
  title,
  score,
  reasons,
  weight,
  composite,
}: {
  title: string;
  score?: number;
  reasons?: string[];
  weight?: number;
  composite?: number;
}) {
  const contribution = typeof score === "number" && typeof weight === "number"
    ? score * weight
    : undefined;
  return (
    <div className="rounded-xl bg-slate-50 p-3">
      <div className="flex items-center justify-between gap-2">
        <div className="text-sm font-medium text-slate-900">{title}</div>
        <div className="text-sm font-semibold text-slate-900">{typeof score === "number" ? score.toFixed(2) : "—"}</div>
      </div>
      <div className="text-[11px] text-slate-500 mt-1">
        Weight {typeof weight === "number" ? `${Math.round(weight * 100)}%` : "—"}
        {typeof contribution === "number" && typeof composite === "number"
          ? ` • contributes ${Math.round(contribution * 100)} of ${Math.round(composite * 100)} match points`
          : ""}
      </div>
      <ul className="mt-3 space-y-1.5 text-xs text-slate-600">
        {(reasons || []).length ? (reasons || []).map((reason) => (
          <li key={reason}>{humanizeReason(reason)}</li>
        )) : <li>No structured reason recorded.</li>}
      </ul>
    </div>
  );
}

function applicationLabel(status?: ApplicationStatus | null) {
  if (!status) return "Not tracked";
  return APPLICATION_STATUS_OPTIONS.find((option) => option.key === status)?.label || status;
}

function applicationBadgeClass(status?: ApplicationStatus | null) {
  if (status === "applied") return "badge bg-sky-50 text-sky-700";
  if (status === "interviewing") return "badge bg-amber-50 text-amber-800";
  if (status === "offer") return "badge bg-emerald-50 text-emerald-700";
  if (status === "rejected" || status === "archived") return "badge bg-slate-100 text-slate-700";
  return "badge bg-slate-100 text-slate-700";
}

function sourceKind(source?: string) {
  const normalized = (source || "").toLowerCase();
  if (["greenhouse", "lever", "ashby", "smartrecruiters", "workable", "recruitee", "workday"].some((prefix) => normalized.startsWith(prefix))) {
    return "Direct source";
  }
  if (normalized.startsWith("jobspy")) return "Web source";
  return "Source";
}

function sourceLabel(source?: string) {
  const normalized = (source || "unknown").toLowerCase();
  const jobSpyMatch = normalized.match(/^jobspy[:_\-\s]*(.+)$/);
  if (jobSpyMatch?.[1]) {
    return `${sourceDisplayName(jobSpyMatch[1])} via JobSpy`;
  }
  return sourceDisplayName(normalized);
}

function sourceDisplayName(value: string) {
  const normalized = value.replace(/[_:-]+/g, " ").replace(/\s+/g, " ").trim().toLowerCase();
  const known: Record<string, string> = {
    linkedin: "LinkedIn",
    indeed: "Indeed",
    glassdoor: "Glassdoor",
    ziprecruiter: "ZipRecruiter",
    google: "Google",
    greenhouse: "Greenhouse",
    lever: "Lever",
    ashby: "Ashby",
    workday: "Workday",
    smartrecruiters: "SmartRecruiters",
  };
  return known[normalized] || titleCase(normalized);
}

function titleCase(value: string) {
  return value
    .replace(/[_:-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function levelLabel(level?: string) {
  const labels: Record<string, string> = {
    intern: "Intern",
    new_grad: "Entry-level",
    entry: "Entry-level",
    mid: "Mid-level",
    senior: "Senior",
    lead: "Lead",
    unknown: "Level not stated",
  };
  return labels[level || ""] || (level || "Unknown").replace(/_/g, " ");
}

function employmentLabel(value?: string) {
  const labels: Record<string, string> = {
    full_time: "Full-time",
    internship: "Internship",
    co_op: "Co-op",
    contract: "Contract",
  };
  return labels[value || ""] || (value || "Job").replace(/_/g, " ");
}

function remoteLabel(value?: string) {
  const labels: Record<string, string> = {
    remote: "Remote",
    hybrid: "Hybrid",
    onsite: "Onsite",
  };
  return labels[value || ""] || (value || "").replace(/_/g, " ");
}

function sponsorshipLabel(value?: string) {
  const normalized = (value || "").toLowerCase();
  const labels: Record<string, string> = {
    likely: "Likely",
    possible: "Possible",
    unlikely: "Unlikely",
    unknown: "Unknown",
    not_applicable: "Not needed",
    sponsor_likely: "Likely",
    sponsor_possible: "Possible",
    sponsor_unlikely: "Unlikely",
  };
  return labels[normalized] || "";
}

function companyStrengthLabel(value?: string) {
  const labels: Record<string, string> = {
    top: "Top-tier company",
    strong: "Strong company",
    standard: "Standard company",
    unknown: "Company strength unknown",
  };
  return labels[value || ""] || (value || "").replace(/_/g, " ");
}

function formatSalaryRange(salary?: Job["salary"]) {
  if (!salary?.min && !salary?.max) return "";
  const currency = salary.currency || "USD";
  const formatter = new Intl.NumberFormat(undefined, {
    style: "currency",
    currency,
    maximumFractionDigits: 0,
  });
  if (salary.min && salary.max) return `${formatter.format(salary.min)}-${formatter.format(salary.max)}`;
  if (salary.min) return `${formatter.format(salary.min)}+`;
  return `Up to ${formatter.format(salary.max || 0)}`;
}

function postedLabel(value?: string) {
  if (!value) return "";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "Posted date unknown";
  const days = Math.max(0, Math.round((Date.now() - parsed.getTime()) / 86_400_000));
  if (days === 0) return "Posted today";
  if (days === 1) return "Posted yesterday";
  if (days < 30) return `Posted ${days} days ago`;
  return parsed.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function formatScore(value?: number) {
  if (typeof value !== "number") return "--";
  return `${Math.round(value * 100)}`;
}

function scoreWidth(value?: number) {
  if (typeof value !== "number") return 0;
  return Math.max(4, Math.min(100, Math.round(value * 100)));
}

function scoreLabel(value: string) {
  if (value === "composite") return "Match";
  if (value === "opportunity") return "Opportunity";
  if (value === "urgency") return "Freshness";
  return "Fit";
}

function llmStatusMessage(status?: string) {
  if (status === "ok") return "Local model reviewed this job.";
  if (status === "disabled") return "Ranked with deterministic local signals.";
  if (status === "unavailable") return "LM Studio was unavailable; ranked with deterministic local signals.";
  if (status === "capped") return "Model review skipped by the per-run cap; deterministic ranking still applied.";
  if (status === "skipped") return "Model review skipped because the deterministic prefilter did not pass.";
  if (status === "error") return "Model review failed; deterministic ranking still applied.";
  return "Ranked with deterministic local signals.";
}

function hostFromUrl(url?: string) {
  if (!url) return undefined;
  try {
    return new URL(url).host.replace(/^www\./, "");
  } catch {
    return undefined;
  }
}

function formatDateTime(value?: string) {
  if (!value) return "—";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

function nextStepMessage(job: Job, application?: ApplicationRecord | null) {
  if (application?.status === "applied") {
    return "Already marked applied. Track follow-up from Applications and use notes to capture next steps.";
  }
  if (job.trust?.label === "suspicious_signals") {
    return "Review the source evidence before sharing personal information. Only apply if the original posting checks out.";
  }
  if (job.eligibility?.label === "likely_blocked") {
    return "Treat this as a likely blocker unless the original posting or a recruiter clarifies sponsorship, citizenship, or clearance requirements.";
  }
  if (job.eligibility?.label === "review_required" || job.trust?.label === "review_recommended") {
    return "Open the original posting, verify the requirements, then decide whether to save it, apply manually, or skip it.";
  }
  if (job.url) {
    return "Open the original posting, confirm the details, and apply manually if it still matches your goals.";
  }
  return "Review the description and signals, then save or skip it in Joby so your search stays organized.";
}

function screeningSignals(screening?: Job["screening"]) {
  const signals = screening?.prefilter_reasons?.signals;
  if (!signals || typeof signals !== "object") return [];
  return Object.entries(signals).map(([key, value]) => {
    const formatted = Array.isArray(value) ? value.join(", ") : String(value);
    return `${key.replace(/_/g, " ")}: ${formatted}`;
  });
}

function humanizeReason(reason: string) {
  if (reason.startsWith("title_sim=")) return `Title match ${reason.split("=")[1]}`;
  if (reason.startsWith("must_skills=")) return `Must-have skill hits ${reason.split("=")[1]}`;
  if (reason.startsWith("nice_skills=")) return `Nice-to-have skill hits ${reason.split("=")[1]}`;
  if (reason.startsWith("yoe_score=")) return `Experience fit ${reason.split("=")[1]}`;
  if (reason.startsWith("visa=")) return `Sponsorship ${sponsorshipLabel(reason.split("=")[1]) || reason.split("=")[1]}`;
  if (reason.startsWith("tier=")) return `Company strength ${companyStrengthLabel(reason.split("=")[1]) || reason.split("=")[1]}`;
  if (reason.startsWith("salary_score=")) return `Salary signal ${reason.split("=")[1]}`;
  if (reason.startsWith("age_days=")) return `Posted about ${reason.split("=")[1]} days ago`;
  if (reason === "closing_language") return "Description includes closing-soon language";
  if (reason === "age_unknown") return "Posting date unavailable";
  return reason.replace(/_/g, " ");
}
