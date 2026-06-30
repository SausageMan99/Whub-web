"use client";

import { useState, type ChangeEvent, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { prepareUpload, createRequest } from "./actions";

const errorMessages: Record<string, string> = {
  candidate_first_name_required: "Ajoute le prénom du candidat avant d’envoyer le CV.",
  file_required: "Ajoute un PDF source avant de créer la demande.",
  pdf_required: "Le fichier doit être un PDF valide.",
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
      const candidateFirstName = String(form.get("candidate_first_name") || "").trim();
      if (!candidateFirstName) {
        setErrorCode("candidate_first_name_required");
        setIsSubmitting(false);
        return;
      }

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
        fileName: file.name,
        fileType: file.type,
        fileSize: file.size,
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
      meta.set("candidate_first_name", candidateFirstName);
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
    <form onSubmit={handleSubmit} className="premium-card rounded-[2rem] p-5 sm:p-7">
      {errorMessage ? (
        <p className="mb-5 rounded-2xl border border-red-100 bg-red-50 px-4 py-3 text-sm font-semibold leading-5 text-red-800">
          {errorMessage}
        </p>
      ) : null}

      <label className="transfer-dropzone group block cursor-pointer rounded-[1.55rem] border border-dashed border-ink/14 bg-porcelain px-5 py-8 text-center hover:border-whub/35 hover:bg-white">
        <span className="mx-auto flex h-12 w-12 items-center justify-center rounded-2xl bg-white text-xl font-semibold text-whub ring-1 ring-ink/8 transition duration-200 group-hover:scale-105 group-hover:ring-whub/22">+</span>
        <span className="mt-4 block text-lg font-semibold tracking-[-0.02em] text-ink">CV source PDF</span>
        <span className="mt-2 block text-sm font-medium leading-6 text-ink/48">
          {selectedFileName ? (
            <>Fichier sélectionné : <span className="font-semibold text-ink">{selectedFileName}</span></>
          ) : (
            <>Dépose le PDF ici ou clique pour choisir un fichier.</>
          )}
        </span>
        <input
          name="file"
          type="file"
          accept="application/pdf"
          required
          onChange={handleFileChange}
          className="sr-only"
        />
      </label>

      <div className="mt-5 grid gap-4 sm:grid-cols-[0.62fr_1.38fr]">
        <label className="block">
          <span className="text-sm font-semibold text-ink">Prénom candidat</span>
          <input
            name="candidate_first_name"
            type="text"
            autoComplete="off"
            required
            className="mt-2 w-full rounded-2xl border border-ink/10 bg-white px-4 py-3.5 text-sm font-medium transition duration-200 placeholder:text-ink/28"
            placeholder="Ex : Mohammed"
          />
        </label>

        <label className="block">
          <span className="text-sm font-semibold text-ink">Consigne optionnelle</span>
          <textarea
            name="instructions"
            rows={4}
            className="mt-2 w-full resize-none rounded-2xl border border-ink/10 bg-white px-4 py-3.5 text-sm font-medium leading-6 transition duration-200 placeholder:text-ink/28"
            placeholder="Ex : mets en avant Java / API / banque, garde le contenu fidèle au CV source."
          />
        </label>
      </div>

      <div className="mt-6 flex flex-col items-start justify-between gap-4 border-t border-ink/8 pt-5 sm:flex-row sm:items-center">
        <p className="max-w-sm text-xs font-medium leading-5 text-ink/42">
          La demande sera ajoutée à la file de production. Le PDF final restera relançable en V2/V3.
        </p>
        <button
          disabled={isSubmitting}
          className="w-full rounded-2xl bg-whub px-6 py-4 text-sm font-black text-white shadow-violet transition duration-200 hover:-translate-y-0.5 hover:shadow-[0_18px_46px_rgba(112,1,245,0.28)] disabled:cursor-not-allowed disabled:opacity-60 disabled:hover:translate-y-0 sm:w-auto"
        >
          {isSubmitting ? "Création de la demande…" : "Générer la version client"}
        </button>
      </div>
    </form>
  );
}
