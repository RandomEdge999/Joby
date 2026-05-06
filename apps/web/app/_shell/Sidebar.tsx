"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import BrandLogo from "../_components/BrandLogo";

const NAV_MAIN = [
  { href: "/",              label: "Dashboard",   icon: IconGrid },
  { href: "/jobs",          label: "Jobs",        icon: IconBriefcase },
  { href: "/companies",     label: "Companies",   icon: IconBuilding },
  { href: "/applications",  label: "Applications", icon: IconCheck },
  { href: "/watches",       label: "Watches",     icon: IconEye },
];

const NAV_SECONDARY = [
  { href: "/sources",    label: "Sources",    icon: IconBuilding },
  { href: "/onboarding", label: "Onboarding", icon: IconSpark },
  { href: "/settings",   label: "Settings",   icon: IconGear },
];

export default function Sidebar() {
  const path = usePathname() || "/";
  const isActive = (href: string) =>
    href === "/" ? path === "/" : path.startsWith(href);

  return (
    <aside className="hidden lg:flex w-[244px] shrink-0 flex-col gap-4 p-4 sticky top-0 h-screen">
      <div className="card !p-4">
        <Link href="/" className="block w-fit">
          <BrandLogo className="h-10 w-auto" priority />
        </Link>
        <div className="mt-3 text-xs text-ink-500">Private local job workspace</div>
      </div>

      {/* Nav */}
      <nav className="card flex-1 flex flex-col gap-1">
        <div className="px-2 pb-2 text-[11px] uppercase tracking-wider text-ink-400">
          Main
        </div>
        {NAV_MAIN.map((n) => {
          const Icon = n.icon;
          const active = isActive(n.href);
          return (
            <Link key={n.href} href={n.href}
              className={`sidebar-link ${active ? "sidebar-link-active" : ""}`}>
              <Icon className="h-4 w-4" />
              <span>{n.label}</span>
            </Link>
          );
        })}

        <div className="px-2 pt-4 pb-2 text-[11px] uppercase tracking-wider text-ink-400">
          Workspace
        </div>
        {NAV_SECONDARY.map((n) => {
          const Icon = n.icon;
          const active = isActive(n.href);
          return (
            <Link key={n.href} href={n.href}
              className={`sidebar-link ${active ? "sidebar-link-active" : ""}`}>
              <Icon className="h-4 w-4" />
              <span>{n.label}</span>
            </Link>
          );
        })}

        <div className="mt-auto pt-4">
          <div className="rounded-xl border border-brand-100 bg-brand-50/80 p-3 text-xs text-brand-700">
            <div className="font-semibold mb-1">Local-first</div>
            <div>All data lives in <code className="font-mono">./data/joby.db</code>.</div>
          </div>
        </div>
      </nav>
    </aside>
  );
}

/* ---------- inline icons (no extra deps) ---------- */
function IconGrid(p: any) { return (<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" {...p}><rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/></svg>); }
function IconBriefcase(p: any) { return (<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" {...p}><rect x="3" y="7" width="18" height="13" rx="2"/><path d="M8 7V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>); }
function IconBuilding(p: any) { return (<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" {...p}><rect x="4" y="3" width="16" height="18" rx="2"/><path d="M9 7h.01M15 7h.01M9 11h.01M15 11h.01M9 15h.01M15 15h.01"/></svg>); }
function IconCheck(p: any) { return (<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" {...p}><path d="M20 6 9 17l-5-5"/></svg>); }
function IconEye(p: any) { return (<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" {...p}><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/></svg>); }
function IconSpark(p: any) { return (<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" {...p}><path d="M12 3v4M12 17v4M4 12H2M22 12h-2M6 6l-1.5-1.5M19.5 19.5 18 18M6 18l-1.5 1.5M19.5 4.5 18 6"/><circle cx="12" cy="12" r="3"/></svg>); }
function IconGear(p: any) { return (<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" {...p}><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3h0a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8v0a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1Z"/></svg>); }
