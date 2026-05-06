"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import Link from "next/link";

type App = {
  id: number; status: string; applied_at?: string; next_action_at?: string;
  notes_summary?: string;
  job: { id: number; title: string; company?: string; location?: string; url?: string };
};

const COLUMNS: { key: string; label: string; tint: string }[] = [
  { key: "saved",        label: "Saved",        tint: "bg-ink-300/15" },
  { key: "applied",      label: "Applied",      tint: "bg-sky-50" },
  { key: "interviewing", label: "Interviewing", tint: "bg-butter-50" },
  { key: "offer",        label: "Offer",        tint: "bg-mint-50" },
  { key: "rejected",     label: "Rejected",     tint: "bg-rose-50" },
  { key: "archived",     label: "Archived",     tint: "bg-slate-100" },
];

export default function ApplicationsPage() {
  const [apps, setApps] = useState<App[]>([]);
  const [loading, setLoading] = useState(true);

  async function load() {
    setLoading(true);
    try {
      const r = await api<{ items: App[] }>("/api/applications");
      setApps(r.items || []);
    } catch { setApps([]); }
    setLoading(false);
  }
  useEffect(() => { load(); }, []);

  async function move(a: App, status: string) {
    await api(`/api/applications/${a.id}`, {
      method: "PATCH", body: JSON.stringify({ status }),
    });
    load();
  }

  const byStatus = (k: string) => apps.filter((a) => a.status === k);

  return (
    <div className="flex flex-col gap-5">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Applications</h1>
        <p className="text-sm text-ink-500">A simple Kanban tracker for the jobs you care about.</p>
      </div>

      {loading && <div className="card text-sm text-ink-500">Loading…</div>}

      <div className="grid grid-cols-1 md:grid-cols-3 xl:grid-cols-6 gap-4">
        {COLUMNS.map((col) => {
          const items = byStatus(col.key);
          return (
            <div key={col.key} className={`rounded-2xl border border-white/70 p-3 shadow-card ${col.tint} min-h-[240px]`}>
              <div className="flex items-center justify-between px-2 py-1">
                <h3 className="text-sm font-semibold">{col.label}</h3>
                <span className="text-xs text-ink-500">{items.length}</span>
              </div>
              <div className="space-y-2 mt-2">
                {items.length === 0 && <div className="text-xs text-ink-400 px-2 py-4">No jobs here yet.</div>}
                {items.map((a) => (
                  <div key={a.id} className="card p-3">
                    <Link href={`/jobs?id=${a.job.id}`}
                          className="font-medium text-sm hover:underline line-clamp-2">
                      {a.job.title}
                    </Link>
                    <div className="text-xs text-ink-500 mt-0.5">{a.job.company || "—"}</div>
                    {a.job.location && (
                      <div className="text-[11px] text-ink-400 mt-0.5">{a.job.location}</div>
                    )}
                    <div className="flex flex-wrap gap-1 mt-2">
                      {COLUMNS.filter((c) => c.key !== col.key).map((c) => (
                        <button key={c.key}
                          onClick={() => move(a, c.key)}
                          className="text-[11px] rounded-full bg-white px-2 py-0.5 border border-ink-300/40 hover:bg-brand-50 hover:border-brand-200 text-ink-600">
                          Move to {c.label}
                        </button>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
