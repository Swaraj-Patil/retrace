import { Sidebar } from "@/components/shell/sidebar";

/**
 * Demo shell. Wraps the public seeded showcase with the existing sidebar.
 * The /app shell (Commit 3) parallels this with the same layout shape so
 * the dashboard, traces, and trace-detail components render identically
 * on either side.
 */
export default function DemoLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <main className="flex-1 overflow-hidden">{children}</main>
    </div>
  );
}
