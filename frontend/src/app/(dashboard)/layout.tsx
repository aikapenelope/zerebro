import { SidebarNav } from "@/components/sidebar-nav";

/**
 * Dashboard layout -- sidebar + main content area.
 * Used by /agents, /agents/[id], /mcp pages.
 */
export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="flex h-screen">
      <SidebarNav />
      <main className="flex-1 overflow-y-auto">
        <div className="mx-auto max-w-5xl p-6">{children}</div>
      </main>
    </div>
  );
}
