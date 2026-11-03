"use client";

import { useEffect, useRef, useState, useTransition, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { addComment } from "@/app/requests/[id]/actions";
import { ensurePrenom } from "@/lib/prenom";
import type { ProofNote } from "@/lib/workspace";
import { IconCheck } from "./icons";

type Comment = { id: string; body: string; when: string; author: string | null };

type PageInfo = { width: number; height: number; textBottom: number | null };

const SPARSE = /^(last_page_sparse|page_too_sparse|continuation_tail_page):/;

/** Épreuve PDF rendue page par page, avec les points à vérifier placés sur la page concernée. */
export function ProofDesk({
  requestId,
  pdfUrl,
  versionLabel,
  stacked,
  notes,
  comments,
  nextOrdinal,
  canCorrect,
  reviewSummary,
  facts,
}: {
  requestId: string;
  pdfUrl: string;
  versionLabel: string;
  stacked: boolean;
  notes: ProofNote[];
  comments: Comment[];
  nextOrdinal: number;
  canCorrect: boolean;
  reviewSummary: React.ReactNode;
  facts: React.ReactNode;
}) {
  const [pages, setPages] = useState<PageInfo[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [active, setActive] = useState<string | null>(null);
  const canvases = useRef<(HTMLCanvasElement | null)[]>([]);
  const docRef = useRef<import("pdfjs-dist").PDFDocumentProxy | null>(null);
  const holder = useRef<HTMLDivElement>(null);
  const textarea = useRef<HTMLTextAreaElement>(null);
  const [draft, setDraft] = useState("");
  const [sent, setSent] = useState<string | null>(null);
  const [sendError, setSendError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();
  const router = useRouter();

  // Chargement du PDF
  useEffect(() => {
    let cancelled = false;
    setPages(null);
    setFailed(false);
    (async () => {
      try {
        const pdfjs = await import("pdfjs-dist");
        pdfjs.GlobalWorkerOptions.workerSrc = new URL("pdfjs-dist/build/pdf.worker.min.mjs", import.meta.url).toString();
        const doc = await pdfjs.getDocument({ url: pdfUrl, isEvalSupported: false, disableFontFace: true }).promise;
        if (cancelled) return;
        docRef.current = doc;
        const infos: PageInfo[] = [];
        for (let n = 1; n <= doc.numPages; n++) {
          const page = await doc.getPage(n);
          const vp = page.getViewport({ scale: 1 });
          const text = await page.getTextContent();
          let bottom: number | null = null;
          for (const item of text.items) {
            if (!("transform" in item) || !item.str?.trim()) continue;
            const y = vp.height - item.transform[5]; // distance depuis le haut
            bottom = bottom === null ? y : Math.max(bottom, y);
          }
          infos.push({ width: vp.width, height: vp.height, textBottom: bottom });
        }
        if (!cancelled) setPages(infos);
      } catch {
        if (!cancelled) setFailed(true);
      }
    })();
    return () => {
      cancelled = true;
      docRef.current?.destroy();
      docRef.current = null;
    };
  }, [pdfUrl]);

  // Rendu net à la largeur affichée, refait quand la largeur change
  useEffect(() => {
    if (!pages || !holder.current) return;
    let frame = 0;
    let lastWidth = 0;
    const tasks: { cancel: () => void }[] = [];
    const draw = async () => {
      const doc = docRef.current;
      const first = canvases.current[0];
      if (!doc || !first) return;
      const width = first.getBoundingClientRect().width;
      if (!width || Math.abs(width - lastWidth) < 2) return;
      lastWidth = width;
      tasks.splice(0).forEach((t) => t.cancel());
      const ratio = Math.min(window.devicePixelRatio || 1, 2);
      for (let i = 0; i < pages.length; i++) {
        const canvas = canvases.current[i];
        if (!canvas) continue;
        const page = await doc.getPage(i + 1);
        const scale = (width * ratio) / pages[i].width;
        const viewport = page.getViewport({ scale });
        canvas.width = Math.round(viewport.width);
        canvas.height = Math.round(viewport.height);
        const ctx = canvas.getContext("2d");
        if (!ctx) continue;
        const task = page.render({ canvasContext: ctx, viewport });
        tasks.push(task);
        await task.promise.catch(() => {});
      }
    };
    const observer = new ResizeObserver(() => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => void draw());
    });
    observer.observe(holder.current);
    void draw();
    return () => {
      observer.disconnect();
      cancelAnimationFrame(frame);
      tasks.forEach((t) => t.cancel());
    };
  }, [pages]);

  const pageNotes = (n: number) => notes.map((note, i) => ({ note, i })).filter(({ note }) => note.page === n);

  function prefill(text: string) {
    setDraft((d) => (d.trim() ? `${d.trim()}\n${text}` : text));
    textarea.current?.focus();
    textarea.current?.scrollIntoView({ block: "center", behavior: "smooth" });
  }

  async function send(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const body = draft.trim();
    if (!body) {
      textarea.current?.focus();
      return;
    }
    const author = await ensurePrenom();
    if (!author) return;
    setSendError(null);
    const fd = new FormData();
    fd.set("request_id", requestId);
    fd.set("body", body);
    fd.set("category", "other");
    fd.set("author", author);
    startTransition(async () => {
      try {
        await addComment(fd);
        setDraft("");
        setSent(`Correction envoyée. La version ${nextOrdinal} est en cours.`);
        router.refresh();
      } catch {
        setSendError("La correction n’a pas pu être envoyée. Réessaie dans un instant.");
      }
    });
  }

  return (
    <div className="bench">
      <div className="sheets" ref={holder} aria-label={`Épreuve, ${versionLabel}`}>
        {failed && (
          <div className="sheet"><p className="sheet-msg">L’aperçu n’a pas pu s’afficher. Le PDF reste téléchargeable avec le bouton en haut.</p></div>
        )}
        {!failed && !pages && (
          <div className="sheet"><div className="loading ghost" aria-label="Chargement de l’épreuve"><i className="big" /><i style={{ width: "55%" }} /><i style={{ width: "48%" }} /><i style={{ width: "52%", marginTop: "6cqw" }} /><i style={{ width: "40%" }} /><i style={{ width: "46%" }} /></div></div>
        )}
        {pages?.map((p, i) => {
          const list = pageNotes(i + 1);
          const sheet = (
            <div className="sheet" key={i} style={{ aspectRatio: `${p.width} / ${p.height}` }}>
              <canvas ref={(el) => { canvases.current[i] = el; }} role="img" aria-label={`Page ${i + 1} sur ${pages.length}`} />
              {list.map(({ note, i: index }, k) => {
                // Page presque vide : on encadre la zone vide sous le dernier texte.
                const sparse = SPARSE.test(note.key) && p.textBottom !== null;
                const top = sparse ? Math.min(90, (p.textBottom! / p.height) * 100 + 3) : 6 + k * 8;
                return (
                  <span key={note.key} className={active === note.key ? "hl" : undefined}>
                    {sparse && <span className="mark" style={{ top: `${top}%`, bottom: "5%" }} />}
                    {!sparse && active === note.key && <span className="mark" style={{ top: "2%", bottom: "2%" }} />}
                    <button
                      type="button"
                      className="pin"
                      style={{ left: "94%", top: `${sparse ? top : 6 + k * 8}%` }}
                      onClick={() => setActive((a) => (a === note.key ? null : note.key))}
                      aria-label={`Point ${index + 1} : ${note.title}`}
                    >
                      {index + 1}
                    </button>
                  </span>
                );
              })}
            </div>
          );
          return i === 0 && stacked ? <div className="stack" key={i}>{sheet}</div> : sheet;
        })}
      </div>

      <aside className="notes" aria-label="Relecture">
        {notes.length > 0 ? (
          <div className="box first">
            <h3>{notes.length} point{notes.length > 1 ? "s" : ""} à vérifier</h3>
            <p>Le contrôle a relevé ces détails. Rien n’a été inventé : vérifie-les avant l’envoi au client.</p>
            <ul className="qa">
              {notes.map((note, i) => (
                <li key={note.key} className={active === note.key ? "on" : undefined} onMouseEnter={() => setActive(note.key)} onMouseLeave={() => setActive(null)}>
                  <button type="button" className="note" onClick={() => setActive((a) => (a === note.key ? null : note.key))} aria-pressed={active === note.key}>
                    <span className="n" aria-hidden="true">{i + 1}</span>
                    <span>
                      <strong>{note.title}</strong>
                      <small>{note.page ? `Page ${note.page}. ` : ""}{note.detail}</small>
                    </span>
                  </button>
                  {note.fix && canCorrect && (
                    <button type="button" className="fix" onClick={() => prefill(note.fix!.text)}>{note.fix.label}</button>
                  )}
                </li>
              ))}
            </ul>
          </div>
        ) : (
          <div className="box first">{reviewSummary}</div>
        )}

        <div className="box">
          <h3>Corrections</h3>
          {comments.length ? (
            <ul className="thread">
              {comments.map((c) => (
                <li key={c.id}><span className="meta">{c.author ? `${c.author}, ` : ""}{c.when}</span>{c.body}</li>
              ))}
            </ul>
          ) : (
            <p>Aucune correction demandée.</p>
          )}
          {canCorrect && (
            <form className="compose" onSubmit={send}>
              <label htmlFor="correction">Demander une correction</label>
              <textarea id="correction" ref={textarea} rows={3} value={draft} onChange={(e) => setDraft(e.target.value)} placeholder="Ex. Remonte la mission la plus récente en premier." />
              <div className="row">
                <span className="hint">Crée la version {nextOrdinal}, depuis le même CV source.</span>
                <button className="btn btn-quiet" type="submit" disabled={pending}>{pending ? "Envoi…" : "Envoyer la correction"}</button>
              </div>
              {sent && <p className="ok" role="status"><IconCheck />{sent}</p>}
              {sendError && <p className="err" role="alert">{sendError}</p>}
            </form>
          )}
        </div>

        <div className="box">{facts}</div>
      </aside>
    </div>
  );
}
