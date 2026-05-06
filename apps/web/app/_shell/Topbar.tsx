"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { api } from "@/lib/api";
import BrandLogo from "../_components/BrandLogo";

type LLM = { available: boolean; model?: string };

const MOBILE_NAV = [
  { href: "/", label: "Dashboard" },
  { href: "/jobs", label: "Jobs" },
  { href: "/companies", label: "Companies" },
  { href: "/applications", label: "Applications" },
  { href: "/sources", label: "Sources" },
];

export default function Topbar() {
  const [llm, setLlm] = useState<LLM | null>(null);
  const [q, setQ] = useState("");
  const path = usePathname() || "/";

  useEffect(() => {
    api<LLM>("/api/llm/health").then(setLlm).catch(() => setLlm({ available: false }));
  }, []);

  return (
    <header className="sticky top-0 z-10 px-4 sm:px-6 lg:px-8 pt-4 pb-3 bg-canvas/70 backdrop-blur-xl">
      <div className="max-w-[1400px] mx-auto flex flex-wrap sm:flex-nowrap items-center gap-3 sm:gap-4">
        <Link href="/" className="shrink-0 lg:hidden">
          <BrandLogo className="h-9 w-auto" priority />
        </Link>

        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (q.trim()) window.location.href = `/jobs?q=${encodeURIComponent(q.trim())}`;
          }}
          className="relative order-3 sm:order-none w-full sm:flex-1 sm:max-w-xl min-w-0"
        >
          <span className="pointer-events-none absolute inset-y-0 left-0 flex w-12 items-center justify-center text-ink-400">
            <svg className="h-4 w-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/></svg>
          </span>
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search jobs, companies..."
            className="input h-11 pl-14 pr-4 leading-5 bg-white"
          />
        </form>

        <div className="ml-auto flex items-center gap-2 shrink-0">
          <div
            className={`badge whitespace-nowrap ${llm?.available ? "badge-mint" : "badge-ink"}`}
            title={llm?.available ? "Local model scoring is available." : "LM Studio is optional. Joby ranks with deterministic local signals when it is unavailable."}
          >
            <span className={`inline-block h-1.5 w-1.5 rounded-full mr-1.5 ${llm?.available ? "bg-emerald-600" : "bg-slate-500"}`} />
            {llm?.available ? `LM Studio ${llm.model ? `• ${llm.model}` : "ready"}` : "Local ranking"}
          </div>
        </div>
      </div>
      <nav className="mx-auto mt-3 flex max-w-[1400px] gap-2 overflow-x-auto pb-1 lg:hidden" aria-label="Primary navigation">
        {MOBILE_NAV.map((item) => {
          const active = item.href === "/" ? path === "/" : path.startsWith(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`shrink-0 rounded-full px-3 py-1.5 text-xs font-medium transition ${active ? "bg-brand-500 text-white shadow-sm" : "bg-white/75 text-ink-600 hover:bg-white"}`}
            >
              {item.label}
            </Link>
          );
        })}
      </nav>
    </header>
  );
}
