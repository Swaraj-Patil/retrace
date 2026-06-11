/**
 * Server-side auth resolution for the protected /app routes.
 *
 * The /app layout (and any /app page that needs the active project)
 * calls {@link getAuthContext} to validate the session and resolve
 * the active project in one place. The result is memoised per-request
 * via React's ``cache()``, so the layout's call and a child page's
 * call share a single backendMe + backendListProjects fan-out.
 *
 * If the session cookie is missing or the backend rejects it (401),
 * the function returns null and the layout sends the visitor to
 * /login. Anything else propagates - we'd rather a 500 than render
 * a degraded shell against half-loaded state.
 */
import "server-only";

import { cache } from "react";
import { cookies } from "next/headers";

import {
  ApiError,
  backendListProjects,
  backendMe,
} from "@/lib/api";
import { ACTIVE_PROJECT_COOKIE, SESSION_COOKIE } from "@/lib/auth/cookie";
import type { MeResponse, ProjectListItem } from "@/lib/types";

export interface AuthContext {
  token: string;
  me: MeResponse;
  projects: ProjectListItem[];
  /** The currently active project. Resolves from the
   *  ``retrace_active_project`` cookie when it matches one of the
   *  user's memberships; otherwise falls back to the first project
   *  (oldest by ``created_at``). Undefined only when the user has
   *  zero projects - degenerate, since register always seeds one. */
  activeProject: ProjectListItem | null;
}

export const getAuthContext = cache(async (): Promise<AuthContext | null> => {
  const cookieStore = cookies();
  const token = cookieStore.get(SESSION_COOKIE)?.value;
  if (!token) return null;

  let me: MeResponse;
  let projects: ProjectListItem[];
  try {
    const [meRes, projectsRes] = await Promise.all([
      backendMe(token),
      backendListProjects(token),
    ]);
    me = meRes;
    projects = projectsRes.projects;
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) return null;
    throw err;
  }

  const cookieProjectId = cookieStore.get(ACTIVE_PROJECT_COOKIE)?.value;
  const matched = cookieProjectId
    ? projects.find((p) => p.id === cookieProjectId)
    : undefined;
  const activeProject = matched ?? projects[0] ?? null;

  return { token, me, projects, activeProject };
});
