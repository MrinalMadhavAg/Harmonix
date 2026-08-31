"use client";

import type { ReactNode } from "react";

import { Crumb, Header } from "./Header";
import { Sidebar } from "./Sidebar";

export function AppShell({
  crumbs,
  children,
}: {
  crumbs: Crumb[];
  children: ReactNode;
}) {
  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar />
      <div className="flex flex-col flex-1 min-w-0">
        <Header crumbs={crumbs} />
        <main className="flex-1 overflow-y-auto p-4 lg:p-6">{children}</main>
      </div>
    </div>
  );
}
