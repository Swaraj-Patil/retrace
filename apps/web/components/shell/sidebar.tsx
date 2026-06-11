import Link from "next/link";

import { Brand } from "@/components/shell/brand";
import { SidebarNav } from "@/components/shell/sidebar-nav";
import { ThemeToggle } from "@/components/shell/theme-toggle";

/** Fixed left rail. ~220px wide. Sticky for tall content. */
export function Sidebar() {
  return (
    <aside className="sticky top-0 hidden h-screen w-[220px] shrink-0 flex-col border-r border-border bg-card/50 md:flex">
      <div className="flex h-14 items-center px-4">
        <Link href="/" aria-label="Retrace home">
          <Brand />
        </Link>
      </div>

      <div className="flex-1 py-2">
        <SidebarNav />
      </div>

      <div className="flex items-center justify-between border-t border-border px-3 py-2">
        <div className="flex flex-col leading-tight">
          <span className="text-xs font-medium">Demo Project</span>
          <span className="font-mono text-[10px] text-muted-foreground">read-only</span>
        </div>
        <ThemeToggle />
      </div>
    </aside>
  );
}
