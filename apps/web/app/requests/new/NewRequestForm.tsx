"use client";

import { useState, FormEvent } from "react";
import { useRouter } from "next/navigation";
import { prepareUpload, createRequest } from "./actions";
import { buildGuidedInstructions, guidedCvIntentions } from "./intentions";

const errorMessages: Record<string, string> = {
  file_required: "Ajoute un PDF source avant de créer la demande.",
  pdf_required: "Le fichier doit être un PDF.",
  upload_failed: "Upload refusé. Réessaie ou envoie-moi le PDF.",
  profile_failed: "Création du profil interne impossible.",
  request_failed: "Création de la demande impossible.",
};

export default function NewRequestForm({ initialError }: { initialError?: string | null }) {
  const router = useRouter();
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorCode, setErrorCode] = useState<string | null>(initialError ?? null);

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

      const guidedIntentions = form.getAll("cv_intentions").map(String);
      const instructions = buildGuidedInstructions(guidedIntentions, String(form.get("instructions") || ""));

      const meta = new FormData();
      meta.set("request_id", requestId);
      meta.set("source_path", sourcePath);
      meta.set("source_file_name", file.name);
      meta.set("source_file_size", String(file.size));
      meta.set("source_file_mime", file.type);
      meta.set("title", String(form.get("title") || ""));
      meta.set("candidate_first_name", String(form.get("candidate_first_name") || ""));
      meta.set("instructions", instructions);
      meta.set("priority", String(form.get("priority") || "normal"));

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

  const errorMessage = errorCode ? errorMessages[errorCode] || `Erreur : ${errorCode}` : null;

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      {errorMessage ? (
        <p className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm font-black leading-5 text-red-700">
          {errorMessage}
        </p>
      ) : null}

      <div className="grid gap-5 sm:grid-cols-2">
        <label className="block sm:col-span-2">
          <span className="text-sm font-black text-ink">Titre interne</span>
          <input name="title" className="mt-2 w-full rounded-2xl border border-ink/10 bg-porcelain/70 px-4 py-3.5 text-sm font-semibold placeholder:text-ink/28" placeholder="CV Architecte Cloud Azure" />
        </label>
        <label className="block">
          <span className="text-sm font-black text-ink">Prénom affiché</span>
          <input name="candidate_first_name" className="mt-2 w-full rounded-2xl border border-ink/10 bg-porcelain/70 px-4 py-3.5 text-sm font-semibold placeholder:text-ink/28" placeholder="Habib" />
        </label>
        <label className="block">
          <span className="text-sm font-black text-ink">Priorité</span>
          <select name="priority" className="mt-2 w-full rounded-2xl border border-ink/10 bg-porcelain/70 px-4 py-3.5 text-sm font-black text-ink">
            <option value="normal">Normal</option>
            <option value="high">Prioritaire</option>
            <option value="urgent">Urgent</option>
          </select>
        </label>
      </div>

      <label className="block rounded-[1.75rem] border border-dashed border-whub/28 bg-whub/[0.035] p-5">
        <span className="text-sm font-black text-ink">CV source PDF</span>
        <input name="file" type="file" accept="application/pdf" required className="mt-3 w-full rounded-2xl border border-ink/10 bg-white px-4 py-3 text-sm font-semibold text-ink/65 file:mr-4 file:rounded-xl file:border-0 file:bg-ink file:px-4 file:py-2 file:text-sm file:font-black file:text-white" />
        <span className="mt-3 block text-xs font-semibold text-ink/45">PDF uniquement. Les coordonnées seront retirées du rendu client.</span>
      </label>

      <fieldset className="rounded-[1.75rem] border border-ink/8 bg-white/70 p-5">
        <legend className="px-1 text-sm font-black text-ink">Intention du CV</legend>
        <p className="mt-1 text-xs font-semibold leading-5 text-ink/45">
          Par défaut : CV W hub fidèle, mise en page uniquement. Le worker retire les contacts/nom/adresse/liens, mais ne reformule pas, ne synthétise pas et n’omet pas le contenu métier sauf consigne explicite de CV court.
        </p>
        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          {guidedCvIntentions.map((intention) => (
            <label key={intention.key} className="flex cursor-pointer items-start gap-3 rounded-2xl border border-ink/8 bg-porcelain/60 px-4 py-3 transition hover:border-whub/35 hover:bg-whub/[0.04]">
              <input
                type="checkbox"
                name="cv_intentions"
                value={intention.key}
                className="mt-1 h-4 w-4 rounded border-ink/20 accent-whub"
              />
              <span className="text-sm font-black leading-5 text-ink/72">{intention.label}</span>
            </label>
          ))}
        </div>
      </fieldset>

      <label className="block">
        <span className="text-sm font-black text-ink">Consignes de génération</span>
        <textarea name="instructions" rows={6} className="mt-2 w-full resize-none rounded-2xl border border-ink/10 bg-porcelain/70 px-4 py-3.5 text-sm font-semibold leading-6 placeholder:text-ink/28" placeholder="Par défaut : mise en page W hub fidèle sans reformulation. Précise ici seulement les exceptions explicites : mission cible, stack à mettre en avant, ou autorisation de raccourcir." />
      </label>

      <div className="flex flex-col items-start justify-between gap-4 border-t border-ink/8 pt-6 sm:flex-row sm:items-center">
        <p className="max-w-md text-xs font-semibold leading-5 text-ink/42">
          {isSubmitting
            ? "Upload en cours… Ne ferme pas la page."
            : "La demande sera visible dans le dashboard une fois créée."}
        </p>
        <button
          disabled={isSubmitting}
          className="w-full rounded-2xl bg-whub px-6 py-4 font-black text-white shadow-violet transition hover:-translate-y-0.5 disabled:opacity-60 disabled:hover:translate-y-0 sm:w-auto"
        >
          {isSubmitting ? "Création en cours…" : "Créer la demande"}
        </button>
      </div>
    </form>
  );
}
