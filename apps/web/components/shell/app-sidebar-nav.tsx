"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { BarChart3, KeyRound, ListTree, Zap, type LucideIcon } from "lucide-react";

import { cn } from "@/lib/utils";

interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
  exact?: boolean;
}

const NAV: NavItem[] = [
  { href: "/app", label: "Dashboard", icon: BarChart3, exact: true },
  { href: "/app/traces", label: "Traces", icon: ListTree },
  { href: "/app/console", label: "Console", icon: KeyRound },
  { href: "/app/quickstart", label: "Quickstart", icon: Zap },
];

export function AppSidebarNav() {
  const pathname = usePathname();
  return (
    <nav className="flex flex-col gap-0.5 px-2">
      {NAV.map((item) => {
        const active = item.exact
          ? pathname === item.href
          : pathname.startsWith(item.href);
        const Icon = item.icon;
        return (
          <Link
            key={item.href}
            href={item.href}
            className={cn(
              "flex items-center gap-2.5 rounded-md px-2.5 py-1.5 text-sm transition-colors",
              active
                ? "bg-secondary text-foreground"
                : "text-muted-foreground hover:bg-secondary/60 hover:text-foreground",
            )}
          >
            <Icon className="h-4 w-4" />
            <span>{item.label}</span>
          </Link>
        );
      })}
    </nav>
  );
}
