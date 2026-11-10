import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { AutoRefreshWhenActive } from "@/components/AutoRefreshWhenActive";
import { ProofDesk } from "@/components/workspace/ProofDesk";
import { RetryButton, ValidateButton } from "@/components/workspace/ReviewActions";
import { IconBack, IconCheck, IconDownload } from "@/components/workspace/icons";
import { loadRequest } from "@/lib/workspace-data";
import { STATE_LABEL, STEPS, blockedReason, longAgo, proofNotes } from "@/lib/workspace";

export const dynamic = "force-dynamic";

type Props = {
  params: Promise<{ id: string }>;
  searchParams?: Promise<Record<string, string | string[] | undefined>>;
};

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { id } = await params;
  const data = await loadRequest(id);
  return { title: data?.request.candidate_first_name || "Demande" };
}

export default async function DemandePage({ params, searchParams }: Props) {
  const { id } = await params;
  const query = await searchParams;
  const data = await loadRequest(id);
  if (!data) notFound();

  const { request, versions, comments, group, step, validation } = data;
  const prenom = request.candidate_first_name || "Sans prénom";
  const latest = versions.at(-1) ?? null;
  const asked = Number(Array.isArray(query?.v) ? query?.v[0] : query?.v);
  const shown = versions.find((v) => v.ordinal === asked) ?? latest;
  const isLatest = Boolean(shown && latest && shown.id === latest.id);
  const poste = (shown as { poste?: string | null } | null)?.poste?.trim() || null;
  const canDownload = Boolean(shown?.final_pdf_path) && request.status !== "qa_failed";
  const nextOrdinal = (latest?.ordinal ?? 0) + 1;
  const reason = group === "bloque" ? blockedReason(request.status, latest?.qa_report) : null;
  const downloadHref = shown ? `/requests/${id}/download/${shown.id}` : "#";

  const facts = (
    <>
      <h3>Demande</h3>
      <dl className="facts">
        <dt>Créée</dt>
        <dd>{longAgo(request.created_at)}</dd>
        <dt>Consigne</dt>
        <dd>{request.instructions?.trim() || "Aucune"}</dd>
        <dt>Versions</dt>
        <dd>{versions.length || "Aucune pour l’instant"}</dd>
      </dl>
    </>
  );

  let actions: React.ReactNode = null;
  if (group === "relire" && isLatest && shown) {
    actions = (
      <>
        {canDownload && <a className="btn btn-quiet" href={downloadHref}><IconDownload />Télécharger l’épreuve</a>}
        <ValidateButton requestId={id} versionId={shown.id} />
      </>
    );
  } else if (group === "pret" && isLatest && shown) {
    actions = (
      <>
        <ValidateButton requestId={id} versionId={shown.id} cancel />
        <a className="btn btn-primary" href={downloadHref}><IconDownload />Télécharger le PDF</a>
      </>
    );
  } else if (shown && canDownload && !isLatest) {
    actions = <a className="btn btn-quiet" href={downloadHref}><IconDownload />Télécharger la version {shown.ordinal}</a>;
  } else if (reason?.action) {
    actions = <RetryButton requestId={id} label={reason.action} />;
  }

  const commentsView = comments
    .filter((c) => c.body?.trim())
    .map((c) => ({
      id: c.id,
      body: c.body,
      when: longAgo(c.created_at),
      author: typeof c.metadata?.author === "string" ? c.metadata.author : null,
    }));

  const reviewSummary =
    group === "pret" ? (
      <>
        <h3>Prêt à envoyer</h3>
        <p className="ok"><IconCheck /><span>{["Relu et validé", validation?.by ? ` par ${validation.by}` : "", validation?.at ? `, ${longAgo(validation.at)}` : "", "."].join("")}</span></p>
        <p className="ok"><IconCheck /><span>Coordonnées et nom de famille retirés par le contrôle.</span></p>
      </>
    ) : (
      <>
        <h3>Aucun point signalé</h3>
        <p className="ok"><IconCheck /><span>Le contrôle n’a rien relevé. Coordonnées et nom de famille retirés.</span></p>
      </>
    );

  return (
    <>
      <AutoRefreshWhenActive status={request.status} />
      <div className="head">
        <Link className="btn btn-ghost back" href="/demandes"><IconBack />Demandes</Link>
        <div className="t">
          <h1>{prenom}</h1>
          {poste && <p>{poste}</p>}
        </div>
        {group && <span className={`pill pill-${group}`}>{STATE_LABEL[group]}</span>}
        {actions && <div className="actions">{actions}</div>}
      </div>

      {versions.length > 1 && (
        <nav className="versions" aria-label="Versions">
          <span>Versions</span>
          {versions.map((v) => (
            <Link key={v.id} className="vtab" href={v.id === latest?.id ? `/demandes/${id}` : `/demandes/${id}?v=${v.ordinal}`} aria-current={v.id === shown?.id ? "page" : undefined} scroll={false}>
              V{v.ordinal}
            </Link>
          ))}
        </nav>
      )}

      {group === "fab" ? (
        <div className="bench">
          <div className="sheets">
            <div className="sheet">
              <div className="loading ghost" aria-hidden="true">
                <i className="big" /><i style={{ width: "55%" }} /><i style={{ width: "48%" }} /><i style={{ width: "52%", marginTop: "6cqw" }} /><i style={{ width: "40%" }} /><i style={{ width: "46%" }} /><i style={{ width: "50%" }} /><i style={{ width: "38%" }} />
              </div>
            </div>
          </div>
          <aside className="notes" aria-label="Avancement">
            <div className="box first">
              <h3>{request.status === "revision_requested" ? `Version ${nextOrdinal} en cours` : "Mise au format en cours"}</h3>
              <p>Compte 2 à 4 minutes. La page se met à jour seule ; tu peux la fermer, la demande continue.</p>
              <ol className="steps" aria-live="polite">
                {STEPS.map((label, i) => (
                  <li key={label} className={i < step ? "done" : i === step ? "now" : "todo"}>
                    <span className="b" aria-hidden="true" />
                    <span>{label}{i === step && <span className="sr-only"> (en cours)</span>}</span>
                  </li>
                ))}
              </ol>
            </div>
            {commentsView.length > 0 && (
              <div className="box">
                <h3>Corrections</h3>
                <ul className="thread">
                  {commentsView.map((c) => <li key={c.id}><span className="meta">{c.author ? `${c.author}, ` : ""}{c.when}</span>{c.body}</li>)}
                </ul>
              </div>
            )}
            <div className="box">{facts}</div>
          </aside>
        </div>
      ) : group === "bloque" && !(shown && request.status === "qa_failed") ? (
        <div className="bench">
          <div className="sheets">
            <div className="sheet scan" role="img" aria-label="Aucun CV produit">
              <div className="lines" aria-hidden="true">
                {[70, 45, 0, 88, 92, 80, 0, 60, 85, 90, 74, 0, 66, 82].map((w, i) => <i key={i} style={{ width: `${w}%`, visibility: w ? "visible" : "hidden" }} />)}
              </div>
              <span className="stamp">{request.status === "needs_human_review" ? "Texte illisible" : "Non produit"}</span>
            </div>
          </div>
          <aside className="notes" aria-label="Blocage">
            <div className="box first">
              <h3 style={{ color: "var(--bloque)" }}>{reason?.title}</h3>
              <p>{reason?.body}</p>
              {reason?.action && <div style={{ marginTop: 14, display: "flex", flexWrap: "wrap", gap: 8 }}><RetryButton requestId={id} label={reason.action} /></div>}
            </div>
            <div className="box">{facts}</div>
          </aside>
        </div>
      ) : shown ? (
        <>
          {reason && (
            <div style={{ padding: "16px 28px 0" }}>
              <p className="err" style={{ margin: 0 }}><b>{reason.title}.</b> {reason.body}</p>
            </div>
          )}
          <ProofDesk
            key={shown.id}
            requestId={id}
            pdfUrl={`/demandes/${id}/apercu/${shown.id}`}
            versionLabel={`version ${shown.ordinal}`}
            stacked={versions.length > 1}
            notes={proofNotes(shown.qa_report)}
            comments={commentsView}
            nextOrdinal={nextOrdinal}
            canCorrect={isLatest && (group === "relire" || group === "pret" || request.status === "qa_failed")}
            reviewSummary={reviewSummary}
            facts={facts}
          />
        </>
      ) : (
        <div className="welcome-empty"><p>Aucune version pour cette demande.</p></div>
      )}
    </>
  );
}
