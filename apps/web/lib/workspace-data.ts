import { createSupabaseAdminClient } from "@/lib/supabase/admin";
import {
  currentStep,
  currentValidation,
  groupFor,
  numberVersions,
  proofNotes,
  type QueueGroup,
  type WorkspaceEvent,
  type WorkspaceVersion,
} from "@/lib/workspace";

export type QueueItem = {
  id: string;
  prenom: string;
  poste: string | null;
  status: string;
  group: QueueGroup;
  updatedAt: string;
  versionCount: number;
  notesCount: number;
  step: number;
  validatedBy: string | null;
};

// Événements utiles à la file : étapes de la tentative en cours et validations.
const QUEUE_EVENTS = [
  "worker_claimed",
  "extraction_done",
  "quality_source_profiled",
  "layout_variant_selected",
  "revision_requested",
  "retry_requested",
  "unlocked",
  "human_validated",
  "human_validation_cancelled",
];

type RequestRow = {
  id: string;
  candidate_first_name: string | null;
  title: string | null;
  status: string;
  created_at: string;
  updated_at: string | null;
};

type VersionRow = WorkspaceVersion & { poste?: string | null; layout_issues?: unknown; soft_warnings?: unknown };

export async function loadQueue(): Promise<QueueItem[]> {
  const admin = createSupabaseAdminClient();
  const { data: requests } = await admin
    .from("cv_requests")
    .select("id,candidate_first_name,title,status,created_at,updated_at")
    .order("created_at", { ascending: false })
    .limit(80);

  const rows = (requests ?? []) as RequestRow[];
  const ids = rows.map((r) => r.id);
  if (!ids.length) return [];

  const [{ data: versions }, { data: events }] = await Promise.all([
    admin
      .from("cv_versions")
      .select("id,request_id,version_number,created_at,poste:structured_json->>title,layout_issues:qa_report->layout_issues,soft_warnings:qa_report->quality_report->soft_warnings")
      .in("request_id", ids),
    admin
      .from("cv_events")
      .select("request_id,event_type,payload,created_at")
      .in("request_id", ids)
      .in("event_type", QUEUE_EVENTS),
  ]);

  const versionsBy = new Map<string, VersionRow[]>();
  for (const v of (versions ?? []) as VersionRow[]) {
    const list = versionsBy.get(v.request_id ?? "") ?? [];
    list.push(v);
    versionsBy.set(v.request_id ?? "", list);
  }
  const eventsBy = new Map<string, WorkspaceEvent[]>();
  for (const e of (events ?? []) as WorkspaceEvent[]) {
    const list = eventsBy.get(e.request_id ?? "") ?? [];
    list.push(e);
    eventsBy.set(e.request_id ?? "", list);
  }

  const items: QueueItem[] = [];
  for (const r of rows) {
    const numbered = numberVersions(versionsBy.get(r.id) ?? []);
    const latest = numbered.at(-1) ?? null;
    const evts = eventsBy.get(r.id) ?? [];
    const validation = currentValidation(evts, latest);
    const group = groupFor(r.status, Boolean(validation));
    if (!group) continue;
    const notes = latest ? proofNotes({ layout_issues: latest.layout_issues, quality_report: { soft_warnings: latest.soft_warnings } }) : [];
    items.push({
      id: r.id,
      prenom: r.candidate_first_name || "Sans prénom",
      poste: latest?.poste?.trim() || null,
      status: r.status,
      group,
      updatedAt: r.updated_at || r.created_at,
      versionCount: numbered.length,
      notesCount: notes.length,
      step: currentStep(r.status, evts),
      validatedBy: validation?.by ?? null,
    });
  }
  return items;
}

export async function loadRequest(id: string) {
  const admin = createSupabaseAdminClient();
  const [{ data: request }, { data: versions }, { data: comments }, { data: events }] = await Promise.all([
    admin
      .from("cv_requests")
      .select("id,candidate_first_name,title,status,instructions,source_file_name,created_at,updated_at")
      .eq("id", id)
      .maybeSingle(),
    admin
      .from("cv_versions")
      .select("id,request_id,version_number,created_at,final_pdf_path,qa_status,qa_report,poste:structured_json->>title")
      .eq("request_id", id),
    admin
      .from("cv_comments")
      .select("id,body,created_at,metadata,comment_type")
      .eq("request_id", id)
      .order("created_at", { ascending: true }),
    admin
      .from("cv_events")
      .select("event_type,payload,created_at")
      .eq("request_id", id)
      .order("created_at", { ascending: true }),
  ]);
  if (!request) return null;

  const numbered = numberVersions((versions ?? []) as VersionRow[]);
  const evts = (events ?? []) as WorkspaceEvent[];
  const latest = numbered.at(-1) ?? null;
  const validation = currentValidation(evts, latest);
  return {
    request: request as RequestRow & { instructions: string | null; source_file_name: string | null },
    versions: numbered,
    comments: (comments ?? []) as { id: string; body: string; created_at: string; metadata: Record<string, unknown> | null }[],
    group: groupFor(request.status, Boolean(validation)),
    step: currentStep(request.status, evts),
    validation,
  };
}
