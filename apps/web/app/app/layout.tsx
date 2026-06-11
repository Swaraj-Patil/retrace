import { redirect } from "next/navigation";

import { AppSidebar } from "@/components/shell/app-sidebar";
import { getAuthContext } from "@/lib/auth/server";

/**
 * Authenticated app shell.
 *
 * Validates the session by calling ``backendMe`` (via the cached
 * ``getAuthContext``); no session, or a 401 response, sends the
 * visitor to /login. The same call also produces the user info and
 * project list the sidebar renders, so the auth gate and the data
 * fetch are the same round-trip.
 *
 * Anything thrown that isn't a 401 propagates - we'd rather surface a
 * 500 than render the shell against half-loaded state.
 */
export default async function AppLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const ctx = await getAuthContext();
  if (!ctx) {
    redirect("/login");
  }
  if (!ctx.activeProject) {
    // Degenerate case: a logged-in user with zero projects. Register
    // seeds a default project so this shouldn't happen, but if a
    // future admin tool deletes it we'd otherwise render a broken
    // shell. Bounce to /login - a future onboarding flow can take
    // over here.
    redirect("/login");
  }

  return (
    <div className="flex min-h-screen">
      <AppSidebar
        me={ctx.me}
        projects={ctx.projects}
        activeProjectId={ctx.activeProject.id}
      />
      <main className="flex-1 overflow-hidden">{children}</main>
    </div>
  );
}
