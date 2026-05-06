"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";

type Company = {
  id: number; name: string; domain?: string; company_tier?: string;
  tier_source?: string; jobs_count?: number;
};

const TIER_CLASS: Record<string, string> = {
  top: "badge-brand", strong: "badge-sky",
  standard: "badge-mint", unknown: "badge-ink",
};

export default function CompaniesPage() {
  const [items, setItems] = useState<Company[]>([]);
  const [q, setQ] = useState("");
  const [loading, setLoading] = useState(true);
  const [tier, setTier] = useState<string>("");

  async function load() {
    setLoading(true);
    try {
      const qs = new URLSearchParams();
      if (q) qs.set("q", q);
      if (tier) qs.set("tier", tier);
      const r = await api<{ items: Company[] }>(`/api/companies?${qs.toString()}`);
      setItems(r.items || []);
    } catch { setItems([]); }
    setLoading(false);
  }
  useEffect(() => { load(); }, [tier]);

  return (
    <div className="flex flex-col gap-5">
      <div className="flex items-end justify-between gap-3 flex-wrap rounded-[28px] border border-white/70 bg-white/75 p-5 shadow-card backdrop-blur-xl">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Companies</h1>
          <p className="text-sm text-ink-500">Curated tiers + H-1B evidence, fully local.</p>
        </div>
        <form
          onSubmit={(e) => { e.preventDefault(); load(); }}
          className="flex w-full flex-wrap items-center gap-2 lg:w-auto"
        >
          <input
            value={q} onChange={(e) => setQ(e.target.value)}
            placeholder="Search name…" className="input min-w-[220px] flex-1 lg:w-64"
          />
          <select value={tier} onChange={(e) => setTier(e.target.value)} className="select w-36">
            <option value="">All tiers</option>
            <option value="top">Top</option>
            <option value="strong">Strong</option>
            <option value="standard">Standard</option>
            <option value="unknown">Unknown</option>
          </select>
          <button className="btn-primary">Search</button>
        </form>
      </div>

      <div className="card overflow-x-auto p-0">
        <table className="min-w-[760px] w-full text-sm">
          <thead className="bg-ink-300/10 text-ink-500">
            <tr>
              <th className="text-left font-medium px-5 py-3">Company</th>
              <th className="text-left font-medium px-5 py-3">Tier</th>
              <th className="text-left font-medium px-5 py-3">Source</th>
              <th className="text-left font-medium px-5 py-3">Domain</th>
              <th className="text-right font-medium px-5 py-3">Jobs</th>
            </tr>
          </thead>
          <tbody>
            {loading && <tr><td className="px-5 py-6 text-ink-400" colSpan={5}>Loading…</td></tr>}
            {!loading && items.length === 0 && (
              <tr><td className="px-5 py-6 text-ink-400" colSpan={5}>No companies yet — run a scrape.</td></tr>
            )}
            {items.map((c) => (
              <tr key={c.id} className="border-t border-ink-300/20 hover:bg-ink-300/5">
                <td className="px-5 py-3 font-medium">{c.name}</td>
                <td className="px-5 py-3">
                  <span className={TIER_CLASS[c.company_tier || "unknown"] || "badge-ink"}>
                    {c.company_tier || "unknown"}
                  </span>
                </td>
                <td className="px-5 py-3 text-ink-500">{c.tier_source || "—"}</td>
                <td className="px-5 py-3 text-ink-500">{c.domain || "—"}</td>
                <td className="px-5 py-3 text-right tabular-nums">
                  <Link href={`/jobs?company=${encodeURIComponent(c.name)}`}
                        className="hover:underline text-brand-600">
                    {c.jobs_count ?? 0}
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
