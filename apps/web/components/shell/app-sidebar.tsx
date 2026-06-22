import Link from "next/link";

import { AppSidebarNav } from "@/components/shell/app-sidebar-nav";
import { Brand } from "@/components/shell/brand";
import { ProjectSwitcher } from "@/components/shell/project-switcher";
import { UserMenu } from "@/components/shell/user-menu";
import type { MeResponse, ProjectListItem } from "@/lib/types";

interface Props {
  me: MeResponse;
  projects: ProjectListItem[];
  activeProjectId: string;
}

/** User-aware sidebar. Same dimensions and resting style as the demo
 *  sidebar; differs only in content (project switcher above the nav,
 *  user identity + logout in the footer). */
export function AppSidebar({ me, projects, activeProjectId }: Props) {
  return (
    <aside className="sticky top-0 hidden h-screen w-[220px] shrink-0 flex-col border-r border-border bg-card/50 md:flex">
      <div className="flex h-14 items-center px-4">
        <Link href="/" aria-label="Retrace home">
          <Brand />
        </Link>
      </div>

      <div className="border-b border-border py-1">
        <ProjectSwitcher projects={projects} activeProjectId={activeProjectId} />
      </div>

      <div className="flex-1 py-2">
        <AppSidebarNav />
      </div>

      <div className="border-t border-border">
        <UserMenu email={me.email} name={me.name} />
      </div>
    </aside>
  );
}
