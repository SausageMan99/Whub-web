"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { markReadyToSend, retryRequest } from "@/app/requests/[id]/actions";
import { ensurePrenom } from "@/lib/prenom";
import { IconCheck } from "./icons";

export function ValidateButton({ requestId, versionId, cancel = false }: { requestId: string; versionId: string; cancel?: boolean }) {
  const [pending, start] = useTransition();
  const [error, setError] = useState<string | null>(null);
  const router = useRouter();

  async function run() {
    const author = cancel ? null : await ensurePrenom();
    if (!cancel && !author) return;
    const fd = new FormData();
    fd.set("request_id", requestId);
    fd.set("version_id", versionId);
    if (author) fd.set("author", author);
    if (cancel) fd.set("cancel", "1");
    setError(null);
    start(async () => {
      try {
        await markReadyToSend(fd);
        router.refresh();
      } catch {
        setError("Action impossible pour le moment. Recharge la page puis réessaie.");
      }
    });
  }

  return (
    <>
      <button type="button" className={cancel ? "btn btn-ghost" : "btn btn-primary"} onClick={run} disabled={pending}>
        {!cancel && <IconCheck />}
        {cancel ? (pending ? "Annulation…" : "Remettre à relire") : pending ? "Validation…" : "Marquer prêt à envoyer"}
      </button>
      {error && <p className="err" role="alert" style={{ flexBasis: "100%" }}>{error}</p>}
    </>
  );
}

export function RetryButton({ requestId, label }: { requestId: string; label: string }) {
  const [pending, start] = useTransition();
  const [error, setError] = useState<string | null>(null);
  const router = useRouter();
  return (
    <>
      <button
        type="button"
        className="btn btn-primary"
        disabled={pending}
        onClick={() => {
          const fd = new FormData();
          fd.set("request_id", requestId);
          setError(null);
          start(async () => {
            try {
              await retryRequest(fd);
              router.refresh();
            } catch {
              setError("La relance a échoué. Réessaie dans un instant.");
            }
          });
        }}
      >
        {pending ? "Relance…" : label}
      </button>
      {error && <p className="err" role="alert">{error}</p>}
    </>
  );
}
