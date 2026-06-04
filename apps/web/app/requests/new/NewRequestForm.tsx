"use client";

import { useState, type ChangeEvent, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { prepareUpload, createRequest } from "./actions";

const errorMessages: Record<string, string> = {
  file_required: "Ajoute un PDF source avant de créer la demande.",
  pdf_required: "Le fichier doit être un PDF.",
  file_too_large: "Le PDF doit faire 10 Mo maximum.",
  upload_failed: "Upload refusé. Réessaie ou envoie-moi le PDF.",
  profile_failed: "Création du profil interne impossible.",
  request_failed: "Création de la demande impossible.",
};

const MAX_UPLOAD_BYTES = 10 * 1024 * 1024;

export default function NewRequestForm({ initialError }: { initialError?: string | null }) {
  const router = useRouter();
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorCode, setErrorCode] = useState<string | null>(initialError ?? null);
  const [selectedFileName, setSelectedFileName] = useState<string | null>(null);

  async function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setIsSubmitting(true);
    setErrorCode(null);

    try {
      const form = new FormData(e.currentTarget);
      const file = form.get("file") as File | null;
      if (!file || file.size === 0) {
        setErrorCode("file_required");
        setIsSubmitting(false);
        return;
      }
      if (file.type !== "application/pdf") {
        setErrorCode("pdf_required");
        setIsSubmitting(false);
        return;
      }
      if (file.size > MAX_UPLOAD_BYTES) {
        setErrorCode("file_too_large");
        setIsSubmitting(false);
        return;
      }
      const firstBytes = new Uint8Array(await file.arrayBuffer()).slice(0, 5);
      const magic = new TextDecoder().decode(firstBytes);
      if (!magic.startsWith("%PDF-")) {
        setErrorCode("pdf_required");
        setIsSubmitting(false);
        return;
      }

      const { requestId, sourcePath, signedUrl } = await prepareUpload({
        file,
        fileName: file.name,
        fileType: file.type,
      });

      const uploadRes = await fetch(signedUrl, {
        method: "PUT",
        body: file,
        headers: {
          "Content-Type": file.type,
          "x-upsert": "false",
        },
      });
      if (!uploadRes.ok) {
        setErrorCode("upload_failed");
        setIsSubmitting(false);
        return;
      }

      const meta = new FormData();
      meta.set("request_id", requestId);
      meta.set("source_path", sourcePath);
      meta.set("source_file_name", file.name);
      meta.set("source_file_size", String(file.size));
      meta.set("source_file_mime", file.type);
      meta.set("instructions", String(form.get("instructions") || ""));

      const result = await createRequest(meta);
      if (!result.ok) {
        setErrorCode(result.error);
        setIsSubmitting(false);
        return;
      }

      router.push(`/requests/${result.requestId}`);
    } catch {
      setErrorCode("request_failed");
      setIsSubmitting(false);
    }
  }

  function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    setSelectedFileName(event.currentTarget.files?.[0]?.name ?? null);
  }

  const errorMessage = errorCode ? errorMessages[errorCode] || `Erreur : ${errorCode}` : null;

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      {errorMessage ? (
        <p className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm font-black leading-5 text-red-700">
          {errorMessage}
        </p>
      ) : null}

      <div className="rounded-[2rem] border border-white/80 bg-gradient-to-br from-ink to-ink/92 p-6 text-white shadow-[0_24px_80px_rgba(17,17,16,0.18)]">
        <p className="text-xs font-black uppercase tracking-[0.34em] text-white/48">Workflow unique</p>
        <h2 className="mt-3 text-2xl font-black tracking-[-0.04em] sm:text-3xl">CV source + message libre</h2>
        <p className="mt-3 max-w-2xl text-sm font-medium leading-6 text-white/72">
          Pas de formulaire candidat séparé. Tu envoies un PDF source, tu ajoutes ta consigne, puis on redirige vers le statut de génération.
        </p>
      </div>

      <label className="block rounded-[1.75rem] border border-dashed border-whub/28 bg-whub/[0.035] p-5">
        <span className="text-sm font-black text-ink">CV source PDF</span>
        <input
          name="file"
          type="file"
          accept="application/pdf"
          required
          onChange={handleFileChange}
          className="mt-3 w-full rounded-2xl border border-ink/10 bg-white px-4 py-3 text-sm font-semibold text-ink/65 file:mr-4 file:rounded-xl file:border-0 file:bg-ink file:px-4 file:py-2 file:text-sm file:font-black file:text-white"
        />
        <span className="mt-3 block text-xs font-semibold text-ink/45">
          PDF uniquement. Les coordonnées sont retirées du rendu client, le CV reste fidèle au source.
        </span>
        <div className="mt-4 rounded-2xl border border-white/80 bg-white px-4 py-3 text-sm font-semibold text-ink/65">
          {selectedFileName ? (
            <span>Fichier sélectionné : <span className="font-black text-ink">{selectedFileName}</span></span>
          ) : (
            <span>Dépose un PDF ou clique pour choisir ton CV source.</span>
          )}
        </div>
      </label>

      <label className="block">
        <span className="text-sm font-black text-ink">Message / consigne complémentaire</span>
        <textarea
          name="instructions"
          rows={7}
          className="mt-2 w-full resize-none rounded-3xl border border-ink/10 bg-porcelain/70 px-4 py-3.5 text-sm font-semibold leading-6 placeholder:text-ink/28"
          placeholder="Ex : garde le contenu source tel quel, retire les coordonnées, mets l’accent sur Java/AWS et redirige-moi vers une version client propre."
        />
        <p className="mt-2 text-xs font-semibold leading-5 text-ink/45">
          N’écris ici que les exceptions utiles. Par défaut, le workflow reste fidèle au CV source et masque les coordonnées.
        </p>
      </label>

      <div className="flex flex-col items-start justify-between gap-4 border-t border-ink/8 pt-6 sm:flex-row sm:items-center">
        <p className="max-w-md text-xs font-semibold leading-5 text-ink/42">
          {isSubmitting
            ? "Génération en cours… Ne ferme pas la page."
            : "Une fois envoyé, tu seras redirigé vers le statut de la demande."}
        </p>
        <button
          disabled={isSubmitting}
          className="w-full rounded-2xl bg-whub px-6 py-4 font-black text-white shadow-violet transition hover:-translate-y-0.5 disabled:opacity-60 disabled:hover:translate-y-0 sm:w-auto"
        >
          {isSubmitting ? "Envoi en cours…" : "Générer le CV"}
        </button>
      </div>
    </form>
  );
}
