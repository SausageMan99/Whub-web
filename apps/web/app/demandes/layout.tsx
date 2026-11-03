import { Suspense } from "react";
import { loadQueue } from "@/lib/workspace-data";
import { QueueList } from "@/components/workspace/QueueList";
import { WorkspaceShell } from "@/components/workspace/WorkspaceShell";

export const dynamic = "force-dynamic";

export default async function DemandesLayout({ children }: { children: React.ReactNode }) {
  const items = await loadQueue();
  return (
    <Suspense>
      <WorkspaceShell queue={<QueueList items={items} />}>{children}</WorkspaceShell>
    </Suspense>
  );
}
