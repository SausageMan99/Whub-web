"use client";

import { useEffect, useRef, useState, type DragEvent, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { createRequest, prepareUpload } from "@/app/requests/new/actions";
import { guessFirstName } from "@/lib/workspace";

const MAX_UPLOAD_BYTES = 10 * 1024 * 1024;

const ERRORS: Record<string, string> = {
  candidate_first_name_required: "Indique le prénom du candidat : c’est le seul élément d’identité gardé sur le CV.",
  file_required: "Ajoute le CV source en PDF.",
  pdf_required: "Ce fichier n’est pas un PDF lisible. Exporte le CV en PDF puis réessaie.",
  file_too_large: "Le PDF dépasse 10 Mo. Compresse-le ou demande une version plus légère au candidat.",
  upload_failed: "L’envoi du PDF a échoué. Vérifie ta connexion puis réessaie.",
  rate_limited: "Trop de CV envoyés en une minute. Attends un instant puis réessaie.",
  request_failed: "La demande n’a pas pu être créée. Réessaie ; si ça recommence, préviens l’administrateur de l’outil.",
  queue_unavailable: "La demande est créée mais la file de traitement ne répond pas. Elle partira dès son retour.",
};

export function NewCvDialog({
  open,
  initialFile,
  initialError,
  onClose,
}: {
  open: boolean;
  initialFile: File | null;
  initialError: string | null;
  onClose: () => void;
}) {
  const router = useRouter();
  const ref = useRef<HTMLDialogElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [prenom, setPrenom] = useState("");
  const [consigne, setConsigne] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [over, setOver] = useState(false);
  const [sending, setSending] = useState(false);

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) {
      setError(initialError);
      setSending(false);
      if (initialFile) take(initialFile);
      dialog.showModal();
    } else if (!open && dialog.open) {
      dialog.close();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, initialFile, initialError]);

  function reset() {
    setFile(null);
    setPrenom("");
    setConsigne("");
    setError(null);
  }

  function take(candidate: File | undefined | null) {
    if (!candidate) return;
    if (candidate.type !== "application/pdf" && !/\.pdf$/i.test(candidate.name)) {
      setError(`« ${candidate.name} » n’est pas un PDF. Exporte le CV en PDF puis réessaie.`);
      return;
    }
    if (candidate.size > MAX_UPLOAD_BYTES) {
      setError(ERRORS.file_too_large);
      return;
    }
    setError(null);
    setFile(candidate);
    setPrenom((current) => current || guessFirstName(candidate.name));
  }

  function onDrop(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault();
    event.stopPropagation();
    setOver(false);
    take(event.dataTransfer.files?.[0]);
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const firstName = prenom.trim();
    if (!file) return setError(ERRORS.file_required);
    if (!firstName) return setError(ERRORS.candidate_first_name_required);

    setSending(true);
    setError(null);
    try {
      // On ne lit que les 5 premiers octets pour vérifier l'en-tête PDF.
      const magic = new TextDecoder().decode(new Uint8Array(await file.slice(0, 5).arrayBuffer()));
      if (!magic.startsWith("%PDF-")) throw new Error("pdf_required");

      const { requestId, sourcePath, signedUrl } = await prepareUpload({ fileName: file.name, fileType: "application/pdf", fileSize: file.size });
      const upload = await fetch(signedUrl, { method: "PUT", body: file, headers: { "Content-Type": "application/pdf", "x-upsert": "false" } });
      if (!upload.ok) throw new Error("upload_failed");

      const meta = new FormData();
      meta.set("request_id", requestId);
      meta.set("source_path", sourcePath);
      meta.set("source_file_name", file.name);
      meta.set("source_file_size", String(file.size));
      meta.set("source_file_mime", "application/pdf");
      meta.set("candidate_first_name", firstName);
      meta.set("instructions", consigne.trim());
      const result = await createRequest(meta);
      if (!result.ok) throw new Error(result.error);

      reset();
      onClose();
      router.push(`/demandes/${result.requestId}`);
      router.refresh();
    } catch (e) {
      // Les redirections de Next (limite d'envoi, fichier refusé) se propagent normalement.
      const digest = (e as { digest?: unknown } | null)?.digest;
      if (typeof digest === "string" && digest.startsWith("NEXT_REDIRECT")) throw e;
      const code = e instanceof Error ? e.message : "request_failed";
      setError(ERRORS[code] ?? ERRORS.request_failed);
      setSending(false);
    }
  }

  return (
    <dialog ref={ref} className="dlg" aria-labelledby="newcv-title" onClose={onClose} onCancel={() => !sending && onClose()}>
      <form className="dlg-body" onSubmit={submit} noValidate>
        <h2 id="newcv-title">Nouveau CV</h2>
        <p>Le CV W hub reprend uniquement le contenu du PDF source. Les coordonnées et le nom de famille sont retirés.</p>
        <label
          className={`drop ${over ? "over" : ""} ${file ? "has" : ""}`}
          onDragEnter={(e) => { e.preventDefault(); e.stopPropagation(); setOver(true); }}
          onDragOver={(e) => { e.preventDefault(); e.stopPropagation(); }}
          onDragLeave={() => setOver(false)}
          onDrop={onDrop}
        >
          <span className="ic" aria-hidden="true">PDF</span>
          <span>
            <strong>{file ? file.name : "Choisis le CV source"}</strong>
            <small>{file ? `${(file.size / 1048576).toFixed(1).replace(".", ",")} Mo. Clique pour changer de fichier.` : "Ou glisse le fichier ici. PDF, 10 Mo maximum."}</small>
          </span>
          <input name="file" type="file" accept="application/pdf" className="sr-only" onChange={(e) => take(e.currentTarget.files?.[0])} />
        </label>
        <div className="field">
          <label htmlFor="candidate_first_name">Prénom du candidat</label>
          <input id="candidate_first_name" name="candidate_first_name" autoComplete="off" placeholder="Ex. Inès" value={prenom} onChange={(e) => setPrenom(e.target.value)} />
        </div>
        <div className="field">
          <label htmlFor="instructions">Consigne <span className="opt">facultative</span></label>
          <textarea id="instructions" name="instructions" rows={3} value={consigne} onChange={(e) => setConsigne(e.target.value)} placeholder="Ex. Mets en avant les missions banque et l’expérience Java. Garde les intitulés du CV source." />
        </div>
        {error && <p className="err" role="alert">{error}</p>}
        <div className="dlg-foot">
          <span className="hint">Prêt à relire en 2 à 4 minutes.</span>
          <div className="btns">
            <button type="button" className="btn btn-ghost" onClick={onClose} disabled={sending}>Annuler</button>
            <button type="submit" className="btn btn-primary" disabled={sending}>{sending ? "Envoi du PDF…" : "Lancer la mise au format"}</button>
          </div>
        </div>
      </form>
    </dialog>
  );
}
