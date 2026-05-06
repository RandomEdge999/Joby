"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";

type Preset = { key: string; name: string; preset: string };
type WeightKey = "w_fit" | "w_opportunity" | "w_urgency";
type BackupBundle = {
  schema_version: number;
  exported_at: string;
  tables: Record<string, Array<Record<string, unknown>>>;
  config?: { sources_user?: Array<Record<string, unknown>> };
  summary?: {
    table_counts?: Record<string, number>;
    sources_user_count?: number;
    total_rows?: number;
  };
};
type BackupImportResult = {
  restored: Record<string, number>;
  sources_user_count: number;
  total_rows: number;
};

function normalizedWeights(scoring: { w_fit: number; w_opportunity: number; w_urgency: number }) {
  const total = Number(scoring.w_fit || 0) + Number(scoring.w_opportunity || 0) + Number(scoring.w_urgency || 0);
  if (total <= 0) {
    return { w_fit: 1 / 3, w_opportunity: 1 / 3, w_urgency: 1 / 3 };
  }
  return {
    w_fit: scoring.w_fit / total,
    w_opportunity: scoring.w_opportunity / total,
    w_urgency: scoring.w_urgency / total,
  };
}

function weightLabel(key: WeightKey) {
  if (key === "w_fit") return "Fit";
  if (key === "w_opportunity") return "Opportunity";
  return "Urgency";
}

export default function Settings() {
  const [profile, setProfile] = useState<any>(null);
  const [presets, setPresets] = useState<Preset[]>([]);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState("");
  const [backupBusy, setBackupBusy] = useState(false);
  const [backupMsg, setBackupMsg] = useState("");
  const [selectedBackup, setSelectedBackup] = useState<BackupBundle | null>(null);
  const [confirmRestore, setConfirmRestore] = useState(false);
  const [llm, setLlm] = useState<any>(null);

  async function load() {
    const p = await api<{ profile: any }>("/api/profile");
    setProfile(p.profile);
    const ps = await api<{ presets: Preset[] }>("/api/profile/presets");
    setPresets(ps.presets);
    try { setLlm(await api<any>("/api/llm/health")); } catch {}
  }
  useEffect(() => { load(); }, []);

  async function save() {
    setSaving(true);
    setMsg("");
    try {
      const saved = await api<{ reranked_jobs?: number }>("/api/profile", {
        method: "PUT",
        body: JSON.stringify(profile),
      });
      setMsg(saved.reranked_jobs ? `Saved and reranked ${saved.reranked_jobs} jobs` : "Saved");
    } catch (e: any) { setMsg(`error: ${e.message}`); }
    finally { setSaving(false); }
  }

  async function loadPreset(key: string) {
    const p = await api<any>(`/api/profile/presets/${key}`);
    setProfile(p);
  }

  async function exportWorkspaceBackup() {
    setBackupBusy(true);
    setBackupMsg("");
    try {
      const bundle = await api<BackupBundle>("/api/backup/export");
      const safeDate = (bundle.exported_at || new Date().toISOString()).replace(/[:.]/g, "-");
      const blob = new Blob([JSON.stringify(bundle, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `joby-workspace-backup-${safeDate}.json`;
      link.click();
      URL.revokeObjectURL(url);
      setBackupMsg(
        `Exported ${bundle.summary?.total_rows ?? 0} database rows and ${bundle.summary?.sources_user_count ?? 0} custom sources.`
      );
    } catch (e: any) {
      setBackupMsg(`error: ${e.message}`);
    } finally {
      setBackupBusy(false);
    }
  }

  async function chooseBackupFile(file?: File | null) {
    if (!file) return;
    setBackupBusy(true);
    setBackupMsg("");
    try {
      const text = await file.text();
      const parsed = JSON.parse(text) as BackupBundle;
      setSelectedBackup(parsed);
      setConfirmRestore(false);
      setBackupMsg(
        `Loaded backup from ${formatDateTime(parsed.exported_at)} with ${backupRowCount(parsed)} database rows and ${parsed.summary?.sources_user_count ?? (parsed.config?.sources_user || []).length} custom sources.`
      );
    } catch (e: any) {
      setSelectedBackup(null);
      setBackupMsg(`error: ${e.message}`);
    } finally {
      setBackupBusy(false);
    }
  }

  async function importWorkspaceBackup() {
    if (!selectedBackup) {
      setBackupMsg("error: choose a backup file first.");
      return;
    }
    if (!confirmRestore) {
      setBackupMsg("error: confirm that you want to replace the current workspace first.");
      return;
    }
    setBackupBusy(true);
    setBackupMsg("");
    try {
      const restored = await api<BackupImportResult>("/api/backup/import", {
        method: "POST",
        body: JSON.stringify({ backup: selectedBackup, confirm_replace: true }),
      });
      await load();
      setSelectedBackup(null);
      setConfirmRestore(false);
      setBackupMsg(`Restored ${restored.total_rows} database rows and ${restored.sources_user_count} custom sources.`);
    } catch (e: any) {
      setBackupMsg(`error: ${e.message}`);
    } finally {
      setBackupBusy(false);
    }
  }

  if (!profile) return <div className="card text-sm text-ink-500">Loading settings...</div>;

  const s = profile.scoring;
  const t = profile.targeting;
  const r = profile.resume;
  const id = profile.identity;
  const sc = profile.screening || { mode: "auto", llm_concurrency: 4, llm_per_run_cap: 0 };
  const src = profile.sources || {};
  const normalized = normalizedWeights(s);

  return (
    <div className="grid gap-4 max-w-5xl">
      <div className="rounded-[28px] border border-white/70 bg-white/75 p-5 shadow-card backdrop-blur-xl">
        <h1 className="text-2xl font-semibold">Settings</h1>
        <p className="mt-1 text-sm text-ink-500">Tune your profile, sources, ranking weights, and local workspace backup.</p>
      </div>

      <div className="card">
        <div className="font-medium mb-2">LM Studio</div>
        {llm ? (
          <div className={`text-sm ${llm.available ? "text-emerald-700" : "text-amber-700"}`}>
            {llm.available ? (llm.model || "available") : (llm.error || "unavailable")}
            <div className="text-xs text-slate-500 mt-1 break-all">{llm.base_url}</div>
          </div>
        ) : <div className="text-slate-500 text-sm">checking…</div>}
      </div>

      <div className="card">
        <div className="font-medium mb-2">Preset</div>
        <div className="flex flex-wrap gap-2">
          {presets.map((p) => (
            <button key={p.key} className="btn-secondary" onClick={() => loadPreset(p.key)}>{p.name}</button>
          ))}
        </div>
      </div>

      <div className="card grid gap-3">
        <div className="font-medium">Identity & sponsorship</div>
        <div className="grid md:grid-cols-2 gap-3">
          <label className="text-sm">Citizenship status
            <select className="select mt-1" value={id.citizenship_status}
                    onChange={(e) => setProfile({ ...profile, identity: { ...id, citizenship_status: e.target.value } })}>
              {["us_citizen","permanent_resident","international_student","h1b_holder","other","unknown"].map(k => <option key={k} value={k}>{humanizeOption(k)}</option>)}
            </select>
          </label>
          <label className="text-sm">Security clearance
            <select className="select mt-1" value={id.security_clearance}
                    onChange={(e) => setProfile({ ...profile, identity: { ...id, security_clearance: e.target.value } })}>
              {["none","secret","top_secret","ts_sci"].map(k => <option key={k} value={k}>{humanizeOption(k)}</option>)}
            </select>
          </label>
          <label className="text-sm flex items-center gap-2">
            <input type="checkbox" checked={id.needs_sponsorship_now}
                   onChange={(e) => setProfile({ ...profile, identity: { ...id, needs_sponsorship_now: e.target.checked } })} />
            Needs sponsorship now
          </label>
          <label className="text-sm flex items-center gap-2">
            <input type="checkbox" checked={id.needs_sponsorship_future}
                   onChange={(e) => setProfile({ ...profile, identity: { ...id, needs_sponsorship_future: e.target.checked } })} />
            Needs sponsorship in future
          </label>
        </div>
      </div>

      <div className="card grid gap-3">
        <div className="font-medium">Targeting</div>
        <label className="text-sm">Target roles (comma-separated)
          <input className="input mt-1" value={(t.target_roles || []).join(", ")}
                 onChange={(e) => setProfile({ ...profile, targeting: { ...t, target_roles: e.target.value.split(",").map((x: string) => x.trim()).filter(Boolean) } })} />
        </label>
        <div className="grid md:grid-cols-3 gap-3">
          <label className="text-sm">Remote preference
            <select className="select mt-1" value={t.remote_preference}
                    onChange={(e) => setProfile({ ...profile, targeting: { ...t, remote_preference: e.target.value } })}>
              {["onsite","hybrid","remote","hybrid_or_remote","any"].map(k => <option key={k} value={k}>{humanizeOption(k)}</option>)}
            </select>
          </label>
          <label className="text-sm">Salary floor (USD)
            <input type="number" className="input mt-1" value={t.salary_floor ?? ""}
                   onChange={(e) => setProfile({ ...profile, targeting: { ...t, salary_floor: e.target.value ? Number(e.target.value) : null } })} />
          </label>
          <label className="text-sm">Posted within (days)
            <input type="number" className="input mt-1" value={t.posted_within_days ?? 30}
                   onChange={(e) => setProfile({ ...profile, targeting: { ...t, posted_within_days: Number(e.target.value) } })} />
          </label>
        </div>
      </div>

      <div className="card grid gap-3">
        <div className="font-medium">Resume & skills</div>
        <label className="text-sm">Must-have skills (comma-separated)
          <input className="input mt-1" value={(r.must_have_skills || []).join(", ")}
                 onChange={(e) => setProfile({ ...profile, resume: { ...r, must_have_skills: e.target.value.split(",").map((x: string) => x.trim()).filter(Boolean) } })} />
        </label>
        <label className="text-sm">Nice-to-have skills (comma-separated)
          <input className="input mt-1" value={(r.nice_to_have_skills || []).join(", ")}
                 onChange={(e) => setProfile({ ...profile, resume: { ...r, nice_to_have_skills: e.target.value.split(",").map((x: string) => x.trim()).filter(Boolean) } })} />
        </label>
        <label className="text-sm">Years of experience
          <input type="number" className="input mt-1" value={r.years_experience ?? 0}
                 onChange={(e) => setProfile({ ...profile, resume: { ...r, years_experience: Number(e.target.value) } })} />
        </label>
      </div>

      <div className="card grid gap-3">
        <div className="font-medium">Ranking weights</div>
        <div className="text-sm text-slate-600">
          These sliders control the composite score used across Jobs and the Dashboard. Saving reranks
          your existing jobs immediately so the explanation cards match your current preferences.
        </div>
        <div className="grid md:grid-cols-3 gap-3">
          {(["w_fit", "w_opportunity", "w_urgency"] as const).map((k) => (
            <div key={`${k}-summary`} className="rounded-xl bg-slate-50 px-3 py-2">
              <div className="text-xs uppercase tracking-wide text-slate-500">{weightLabel(k)}</div>
              <div className="mt-1 text-lg font-semibold text-slate-900">{Math.round(normalized[k] * 100)}%</div>
              <div className="text-xs text-slate-500">of the composite score right now</div>
            </div>
          ))}
        </div>
        {(["w_fit","w_opportunity","w_urgency"] as const).map((k) => (
          <label key={k} className="text-sm">
            <div className="flex justify-between">
              <span>{weightLabel(k)}</span>
              <span className="tabular-nums">raw {Number(s[k]).toFixed(2)} | effective {Math.round(normalized[k] * 100)}%</span>
            </div>
            <input type="range" min={0} max={1} step={0.05} className="w-full"
                   value={s[k]}
                   onChange={(e) => setProfile({ ...profile, scoring: { ...s, [k]: Number(e.target.value) } })} />
          </label>
        ))}
        <label className="text-sm flex items-center gap-2">
          <input type="checkbox" checked={s.visa_hard_filter}
                 onChange={(e) => setProfile({ ...profile, scoring: { ...s, visa_hard_filter: e.target.checked } })} />
          Hard-filter jobs that are visa-unlikely
        </label>
      </div>

      <div className="card grid gap-3">
        <div className="font-medium">Screening mode</div>
        <div className="text-xs text-slate-500">
          auto works either way: use LM Studio when it is available, otherwise rank deterministically.
          heuristic is fully local and never calls an LLM. llm requires LM Studio for model screening.
        </div>
        <div className="grid md:grid-cols-3 gap-3">
          <label className="text-sm">Mode
            <select className="select mt-1" value={sc.mode}
                    onChange={(e) => setProfile({ ...profile, screening: { ...sc, mode: e.target.value } })}>
              {["auto","llm","heuristic"].map(k => <option key={k} value={k}>{humanizeOption(k)}</option>)}
            </select>
          </label>
          <label className="text-sm">LLM concurrency
            <input type="number" min={1} max={16} className="input mt-1" value={sc.llm_concurrency ?? 4}
                   onChange={(e) => setProfile({ ...profile, screening: { ...sc, llm_concurrency: Number(e.target.value) } })} />
          </label>
          <label className="text-sm">Per-run LLM cap (0 = all)
            <input type="number" min={0} className="input mt-1" value={sc.llm_per_run_cap ?? 0}
                   onChange={(e) => setProfile({ ...profile, screening: { ...sc, llm_per_run_cap: Number(e.target.value) } })} />
          </label>
        </div>
      </div>

      <div className="card grid gap-3">
        <div className="font-medium">Sources</div>
        <div className="grid md:grid-cols-2 gap-2 text-sm">
          {[
            ["enable_ats","ATS boards (Greenhouse/Lever/Ashby/…)"] ,
            ["enable_workday","Workday tenants"],
            ["enable_smartrecruiters","SmartRecruiters"],
            ["enable_workable","Workable"],
            ["enable_recruitee","Recruitee"],
            ["enable_jobspy","JobSpy (LinkedIn/Indeed/Glassdoor/ZipRecruiter/Google)"],
          ].map(([k,label]) => (
            <label key={k} className="flex items-center gap-2">
              <input type="checkbox" checked={!!src[k as string]}
                     onChange={(e) => setProfile({ ...profile, sources: { ...src, [k as string]: e.target.checked } })} />
              {label}
            </label>
          ))}
        </div>
        <label className="text-sm">JobSpy search terms (comma-separated)
          <input className="input mt-1" value={(src.jobspy_search_terms || []).join(", ")}
                 onChange={(e) => setProfile({ ...profile, sources: { ...src, jobspy_search_terms: e.target.value.split(",").map((x: string) => x.trim()).filter(Boolean) } })}
                 placeholder="software engineer, backend engineer, platform engineer" />
        </label>
        <label className="text-sm">JobSpy locations (comma-separated)
          <input className="input mt-1" value={(src.jobspy_locations || ["United States"]).join(", ")}
                 onChange={(e) => setProfile({ ...profile, sources: { ...src, jobspy_locations: e.target.value.split(",").map((x: string) => x.trim()).filter(Boolean) } })} />
        </label>
        <label className="text-sm">JobSpy results per term (per location)
          <input type="number" min={5} max={200} className="input mt-1" value={src.jobspy_results_per_term ?? 30}
                 onChange={(e) => setProfile({ ...profile, sources: { ...src, jobspy_results_per_term: Number(e.target.value) } })} />
        </label>
      </div>

      <div className="card grid gap-3">
        <div className="font-medium">Workspace backup</div>
        <div className="text-sm text-slate-600">
          Export a full JSON backup of your local workspace, including saved jobs, notes, applications,
          rankings, and custom source overlays. Restoring a backup replaces the current local workspace.
        </div>
        <div className="flex flex-wrap gap-3">
          <button className="btn-secondary" disabled={backupBusy} onClick={exportWorkspaceBackup}>
            {backupBusy ? "Working…" : "Export workspace backup"}
          </button>
          <label className="btn-secondary cursor-pointer">
            Choose backup file
            <input
              type="file"
              accept="application/json,.json"
              className="hidden"
              onChange={(e) => chooseBackupFile(e.target.files?.[0] || null)}
            />
          </label>
        </div>
        {selectedBackup && (
          <div className="rounded-xl bg-slate-50 px-3 py-3 text-sm text-slate-700">
            <div className="font-medium text-slate-900">Loaded backup</div>
            <div className="mt-1">Exported {formatDateTime(selectedBackup.exported_at)}</div>
            <div className="mt-1">
              Includes {backupRowCount(selectedBackup)} database rows and {selectedBackup.summary?.sources_user_count ?? (selectedBackup.config?.sources_user || []).length} custom sources.
            </div>
            <label className="mt-3 flex items-center gap-2 text-sm text-slate-800">
              <input
                type="checkbox"
                checked={confirmRestore}
                onChange={(e) => setConfirmRestore(e.target.checked)}
              />
              Replace the current local workspace with this backup.
            </label>
            <div className="mt-3">
              <button className="btn-primary" disabled={backupBusy || !confirmRestore} onClick={importWorkspaceBackup}>
                {backupBusy ? "Restoring…" : "Import and replace workspace"}
              </button>
            </div>
          </div>
        )}
        {backupMsg && <div className="text-sm text-slate-600">{backupMsg}</div>}
      </div>

      <div className="flex items-center gap-3">
        <button className="btn-primary" disabled={saving} onClick={save}>{saving ? "Saving…" : "Save profile"}</button>
        {msg && <div className="text-sm text-slate-600">{msg}</div>}
      </div>
    </div>
  );
}

function backupRowCount(bundle: BackupBundle) {
  if (bundle.summary?.total_rows != null) return bundle.summary.total_rows;
  return Object.values(bundle.tables || {}).reduce((sum, rows) => sum + rows.length, 0);
}

function formatDateTime(value?: string) {
  if (!value) return "—";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

function humanizeOption(value: string) {
  const labels: Record<string, string> = {
    us_citizen: "US citizen",
    permanent_resident: "Permanent resident",
    international_student: "International student",
    h1b_holder: "H-1B holder",
    ts_sci: "TS/SCI",
    hybrid_or_remote: "Hybrid or remote",
    llm: "LM Studio required",
    heuristic: "Local heuristic only",
    auto: "Auto",
  };
  return labels[value] || value.replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}
