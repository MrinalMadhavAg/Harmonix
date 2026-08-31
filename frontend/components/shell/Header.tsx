"use client";

import { Bell, Search } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import type { ReactNode } from "react";

export interface Crumb {
  label: string;
  href?: string;
}

export function Header({ crumbs }: { crumbs: Crumb[] }) {
  const router = useRouter();
  const [query, setQuery] = useState("");

  return (
    <header className="h-14 shrink-0 flex items-center gap-4 px-4 lg:px-6 border-b border-line bg-surface">
      <nav aria-label="Breadcrumb" className="min-w-0 flex-1">
        <ol className="flex items-center text-sm min-w-0">
          {crumbs.map((c, i) => (
            <li key={`${c.label}-${i}`} className="flex items-center min-w-0">
              {i > 0 && <span className="breadcrumb-sep" aria-hidden>/</span>}
              {c.href && i < crumbs.length - 1 ? (
                <Link href={c.href} className="text-ink-subtle hover:text-accent-500 truncate">
                  {c.label}
                </Link>
              ) : (
                <span
                  className="text-ink font-medium truncate"
                  aria-current={i === crumbs.length - 1 ? "page" : undefined}
                >
                  {c.label}
                </span>
              )}
            </li>
          ))}
        </ol>
      </nav>

      <form
        role="search"
        className="hidden md:block relative w-72"
        onSubmit={(e) => {
          e.preventDefault();
          const q = query.trim();
          if (q) router.push(`/materials?search=${encodeURIComponent(q)}`);
        }}
      >
        <Search
          className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-ink-faint pointer-events-none"
          aria-hidden
        />
        <input
          className="input pl-8"
          placeholder="Search materials, codes or NMIs"
          aria-label="Search materials, codes or NMIs"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
      </form>

      <button
        type="button"
        className="btn-ghost h-8 w-8 p-0 relative"
        aria-label="Notifications"
        title="Notifications"
      >
        <Bell className="h-4 w-4" aria-hidden />
      </button>
    </header>
  );
}

export function PageHeading({
  title,
  description,
  actions,
}: {
  title: string;
  description?: string;
  actions?: ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-3 mb-4">
      <div className="min-w-0">
        <h1 className="text-xl font-semibold text-ink tracking-tight">{title}</h1>
        {description && (
          <p className="text-sm text-ink-subtle mt-0.5 max-w-3xl">{description}</p>
        )}
      </div>
      {actions && <div className="flex items-center gap-2 shrink-0">{actions}</div>}
    </div>
  );
}
