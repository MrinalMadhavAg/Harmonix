"use client";

import clsx from "clsx";
import {
  Building2,
  CircleHelp,
  Database,
  FileBarChart,
  GitCompareArrows,
  LayoutDashboard,
  ListChecks,
  Package,
  Settings,
  ShieldCheck,
  UserRound,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

const PRIMARY = [
  { href: "/", label: "Overview", icon: LayoutDashboard, exact: true },
  { href: "/materials", label: "Materials", icon: Package },
  { href: "/harmonization", label: "Harmonization", icon: GitCompareArrows },
  { href: "/review", label: "Review Queue", icon: ListChecks },
  { href: "/governance", label: "Governance Gate", icon: ShieldCheck },
  { href: "/cpses", label: "CPSEs", icon: Building2 },
  { href: "/data-sources", label: "Data Sources", icon: Database },
  { href: "/reports", label: "Reports", icon: FileBarChart },
];

const SECONDARY = [
  { href: "/settings", label: "Settings", icon: Settings },
  { href: "/help", label: "Help", icon: CircleHelp },
];

function NavLink({
  href,
  label,
  icon: Icon,
  active,
}: {
  href: string;
  label: string;
  icon: typeof Package;
  active: boolean;
}) {
  return (
    <Link
      href={href}
      aria-current={active ? "page" : undefined}
      className={clsx(
        "flex items-center gap-2.5 h-8 px-2.5 rounded text-sm transition-colors",
        active
          ? "bg-accent-500 text-white font-medium"
          : "text-ink-muted hover:bg-surface-muted hover:text-ink"
      )}
    >
      <Icon className="h-4 w-4 shrink-0" aria-hidden />
      <span className="truncate">{label}</span>
    </Link>
  );
}

export function Sidebar() {
  const pathname = usePathname() || "/";

  const isActive = (href: string, exact?: boolean) =>
    exact ? pathname === href : pathname === href || pathname.startsWith(`${href}/`);

  return (
    <aside className="hidden lg:flex w-56 shrink-0 flex-col border-r border-line bg-surface">
      <div className="h-14 flex items-center gap-2.5 px-4 border-b border-line">
        <div className="h-7 w-7 rounded bg-accent-500 flex items-center justify-center shrink-0">
          <GitCompareArrows className="h-4 w-4 text-white" aria-hidden />
        </div>
        <div className="min-w-0">
          <p className="text-sm font-semibold text-ink leading-tight">Harmonix</p>
          <p className="text-2xs text-ink-subtle leading-tight truncate">
            Material Data Governance
          </p>
        </div>
      </div>

      <nav className="flex-1 overflow-y-auto p-2 space-y-0.5">
        {PRIMARY.map((item) => (
          <NavLink key={item.href} {...item} active={isActive(item.href, item.exact)} />
        ))}
      </nav>

      <div className="p-2 border-t border-line space-y-0.5">
        {SECONDARY.map((item) => (
          <NavLink key={item.href} {...item} active={isActive(item.href)} />
        ))}
        <div className="flex items-center gap-2.5 h-11 px-2.5 mt-1 rounded">
          <div className="h-7 w-7 rounded-full bg-surface-sunken flex items-center justify-center shrink-0">
            <UserRound className="h-3.5 w-3.5 text-ink-muted" aria-hidden />
          </div>
          <div className="min-w-0">
            <p className="text-xs font-medium text-ink leading-tight truncate">
              Data Steward
            </p>
            <p className="text-2xs text-ink-subtle leading-tight truncate">
              demo.steward
            </p>
          </div>
        </div>
      </div>
    </aside>
  );
}
