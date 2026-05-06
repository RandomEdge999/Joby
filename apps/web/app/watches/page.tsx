"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";

type Watch = {
  id: number; name: string; cadence_minutes: number; enabled: boolean;
  last_run_at?: string | null; next_run_at?: string | null;
  query_json?: any;
};

type Ev = {
  id: number; event_type: string; occurred_at?: string; payload?: any;
  job: { id: number; title: string; company?: string };
};

export default function WatchesPage() {
  const [items, setItems] = useState<Watch[]>([]);
  const [name, setName] = useState("");
  const [cadence, setCadence] = useState(360);
  const [events, setEvents] = useState<Record<number, Ev[]>>({});
  const [busy, setBusy] = useState<number | null>(null);

  async function load() {
    try {
      const r = await api<{ items: Watch[] }>("/api/watches");
      setItems(r.items || []);
      const pairs: [number, Ev[]][] = await Promise.all(
        (r.items || []).map(async (w) => {
          try {
            const er = await api<{ items: Ev[] }>(`/api/watches/${w.id}/events?limit=5`);
            return [w.id, er.items || []] as [number, Ev[]];
          } catch { return [w.id, []] as [number, Ev[]]; }
        })
      );
      setEvents(Object.fromEntries(pairs));
    } catch { setItems([]); }
  }
  useEffect(() => { load(); }, []);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    await api("/api/watches", {
      method: "POST",
      body: JSON.stringify({ name: name.trim(), cadence_minutes: cadence, enabled: true }),
    });
    setName(""); setCadence(360); load();
  }

  async function toggle(w: Watch) {
    await api(`/api/watches/${w.id}`, {
      method: "PATCH", body: JSON.stringify({ enabled: !w.enabled }),
    });
    load();
  }

  async function runNow(w: Watch) {
    setBusy(w.id);
    try {
      await api(`/api/watches/${w.id}/run`, { method: "POST" });
    } finally {
      setTimeout(() => { setBusy(null); load(); }, 1200);
    }
  }

  async function remove(w: Watch) {
    if (!confirm(`Delete watch "${w.name}"?`)) return;
    await api(`/api/watches/${w.id}`, { method: "DELETE" });
    load();
  }

  return (
    <div className="flex flex-col gap-5">
      <div className="rounded-[28px] border border-white/70 bg-white/75 p-5 shadow-card backdrop-blur-xl">
        <h1 className="text-2xl font-semibold tracking-tight">Watches</h1>
        <p className="text-sm text-ink-500">
          Scheduled scrapes. Cadence is minutes between runs (minimum 5).
        </p>
      </div>

      <form onSubmit={create} className="card flex flex-wrap items-end gap-3">
        <div className="flex-1 min-w-[220px]">
          <label className="text-xs text-ink-500">Name</label>
          <input value={name} onChange={(e) => setName(e.target.value)}
                 className="input mt-1" placeholder="Nightly scrape" />
        </div>
        <div>
          <label className="text-xs text-ink-500">Cadence (min)</label>
          <input type="number" min={5} value={cadence}
                 onChange={(e) => setCadence(parseInt(e.target.value || "0", 10))}
                 className="input mt-1 w-32" />
        </div>
        <button className="btn-primary">Create watch</button>
      </form>

      {items.length === 0 && (
        <div className="card text-sm text-ink-500">
          No watches yet. Create one above.
        </div>
      )}

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        {items.map((w) => (
          <div key={w.id} className="card">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="font-semibold">{w.name}</div>
                <div className="text-xs text-ink-500 mt-0.5">
                  every {w.cadence_minutes} min ·{" "}
                  last run: {w.last_run_at ? new Date(w.last_run_at).toLocaleString() : "never"}
                </div>
              </div>
              <span className={w.enabled ? "badge-mint" : "badge-ink"}>
                {w.enabled ? "enabled" : "paused"}
              </span>
            </div>

            <div className="flex items-center gap-2 mt-3">
              <button onClick={() => runNow(w)} disabled={busy === w.id}
                      className="btn-primary text-xs px-3 py-1.5">
                {busy === w.id ? "Queued…" : "Run now"}
              </button>
              <button onClick={() => toggle(w)} className="btn-secondary text-xs px-3 py-1.5">
                {w.enabled ? "Pause" : "Resume"}
              </button>
              <button onClick={() => remove(w)} className="btn-ghost text-xs px-3 py-1.5 text-rose-700">
                Delete
              </button>
            </div>

            <div className="mt-4">
              <div className="text-[11px] uppercase tracking-wider text-ink-400 mb-1">
                Recent events
              </div>
              {(events[w.id]?.length ?? 0) === 0 ? (
                <div className="text-xs text-ink-400">No events yet.</div>
              ) : (
                <ul className="space-y-1.5">
                  {events[w.id].map((e) => (
                    <li key={e.id} className="flex items-center gap-2 text-xs">
                      <span className="badge-ink capitalize">{e.event_type.replace("_", " ")}</span>
                      <span className="truncate">{e.job.title}</span>
                      <span className="text-ink-400 ml-auto">
                        {e.occurred_at ? new Date(e.occurred_at).toLocaleDateString() : ""}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
