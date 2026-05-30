"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { BarChart3, ListTree, LucideIcon } from "lucide-react";

import { cn } from "@/lib/utils";

interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
  disabled?: boolean;
}

const NAV: NavItem[] = [
  { href: "/traces", label: "Traces", icon: ListTree },
  { href: "/metrics", label: "Metrics", icon: BarChart3, disabled: true },
];

export function SidebarNav() {
  const pathname = usePathname();
  return (
    <nav className="flex flex-col gap-0.5 px-2">
      {NAV.map((item) => {
        const active = pathname.startsWith(item.href);
        const Icon = item.icon;
        const content = (
          <>
            <Icon className="h-4 w-4" />
            <span>{item.label}</span>
            {item.disabled && (
              <span className="ml-auto text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
                Soon
              </span>
            )}
          </>
        );
        const baseClass =
          "flex items-center gap-2.5 rounded-md px-2.5 py-1.5 text-sm transition-colors";
        if (item.disabled) {
          return (
            <span
              key={item.href}
              className={cn(baseClass, "cursor-not-allowed text-muted-foreground/70")}
            >
              {content}
            </span>
          );
        }
        return (
          <Link
            key={item.href}
            href={item.href}
            className={cn(
              baseClass,
              active
                ? "bg-secondary text-foreground"
                : "text-muted-foreground hover:bg-secondary/60 hover:text-foreground",
            )}
          >
            {content}
          </Link>
        );
      })}
    </nav>
  );
}
