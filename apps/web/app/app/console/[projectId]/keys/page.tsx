import Link from "next/link";
import { notFound, redirect } from "next/navigation";
import { ArrowLeft } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { ApiError, listApiKeys } from "@/lib/api";
import { getAuthContext } from "@/lib/auth/server";
import { dateOnly, relativeTime } from "@/lib/format";

import { CreateKeyForm } from "./_components/create-key-form";
import { RevokeKeyButton } from "./_components/revoke-key-button";

interface PageProps {
  params: { projectId: string };
}

export default async function ProjectKeysPage({ params }: PageProps) {
  const auth = await getAuthContext();
  if (!auth) {
    redirect("/login");
  }

  // The project must be one of the caller's memberships. We already
  // hold that list, so resolve the name here and 404 on a mismatch -
  // same outcome the backend would give for a cross-org id, just
  // without the extra round trip.
  const project = auth.projects.find((p) => p.id === params.projectId);
  if (!project) {
    notFound();
  }

  let keys;
  try {
    keys = (await listApiKeys(auth.token, project.id)).keys;
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) {
      notFound();
    }
    throw err;
  }

  return (
    <div className="mx-auto max-w-4xl px-6 py-8">
      <Link
        href="/app/console"
        className="inline-flex items-center gap-1.5 text-xs text-muted-foreground transition-colors hover:text-foreground"
      >
        <ArrowLeft className="h-3.5 w-3.5" />
        Console
      </Link>

      <header className="mb-6 mt-3">
        <p className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground/80">
          {project.slug}
        </p>
        <h1 className="mt-1 text-xl font-semibold tracking-tight">{project.name} · API keys</h1>
        <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
          Keys authorize the SDK to send telemetry to this project. The full key
          is shown once at creation. Store it somewhere safe; you can always
          revoke and create another.
        </p>
      </header>

      <section className="mb-8">
        <h2 className="mb-3 text-sm font-medium">Create a key</h2>
        <CreateKeyForm projectId={project.id} />
      </section>

      <section>
        <h2 className="mb-3 text-sm font-medium">Keys</h2>
        {keys.length === 0 ? (
          <p className="rounded-lg border border-dashed border-border px-4 py-8 text-center text-sm text-muted-foreground">
            No keys yet. Create one above to connect the SDK.
          </p>
        ) : (
          <div className="overflow-hidden rounded-lg border border-border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Name</TableHead>
                  <TableHead>Key</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Last used</TableHead>
                  <TableHead>Created</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {keys.map((k) => {
                  const revoked = k.revoked_at !== null;
                  return (
                    <TableRow key={k.id}>
                      <TableCell className="font-medium">{k.name}</TableCell>
                      <TableCell className="font-mono text-xs text-muted-foreground">
                        {k.key_prefix}…
                      </TableCell>
                      <TableCell>
                        {revoked ? (
                          <Badge variant="muted">Revoked</Badge>
                        ) : (
                          <Badge variant="success">Active</Badge>
                        )}
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground">
                        {k.last_used_at ? relativeTime(k.last_used_at) : "-"}
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground">
                        {dateOnly(k.created_at)}
                      </TableCell>
                      <TableCell className="text-right">
                        {!revoked && <RevokeKeyButton projectId={project.id} keyId={k.id} />}
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </div>
        )}
      </section>
    </div>
  );
}
