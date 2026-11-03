"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { ASK_PRENOM_EVENT, savePrenom, usePrenom } from "@/lib/prenom";
import { NewCvDialog } from "./NewCvDialog";
import { Splash, SPLASH_KEY } from "./Splash";
import { IconPlus } from "./icons";

export function WorkspaceShell({ queue, children }: { queue: React.ReactNode; children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const params = useSearchParams();
  const prenom = usePrenom();
  const detail = /^\/demandes\/[^/]+/.test(pathname);

  // ---- Nouveau CV : bouton, ?nouveau=1, ou PDF lâché n'importe où ----
  const [newOpen, setNewOpen] = useState(false);
  const [droppedFile, setDroppedFile] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false);
  const urlError = params.get("error");

  useEffect(() => {
    if (params.get("nouveau") === "1") setNewOpen(true);
  }, [params]);

  const closeNew = useCallback(() => {
    setNewOpen(false);
    setDroppedFile(null);
    if (params.get("nouveau")) router.replace(pathname, { scroll: false });
  }, [params, pathname, router]);

  useEffect(() => {
    let depth = 0;
    const hasFiles = (e: DragEvent) => Array.from(e.dataTransfer?.types ?? []).includes("Files");
    const enter = (e: DragEvent) => {
      if (!hasFiles(e) || newOpen) return;
      depth += 1;
      setDragging(true);
    };
    const leave = () => {
      depth = Math.max(0, depth - 1);
      if (!depth) setDragging(false);
    };
    const over = (e: DragEvent) => hasFiles(e) && e.preventDefault();
    const drop = (e: DragEvent) => {
      if (!hasFiles(e)) return;
      e.preventDefault();
      depth = 0;
      setDragging(false);
      if (newOpen) return;
      const file = e.dataTransfer?.files?.[0];
      if (file) {
        setDroppedFile(file);
        setNewOpen(true);
      }
    };
    window.addEventListener("dragenter", enter);
    window.addEventListener("dragleave", leave);
    window.addEventListener("dragover", over);
    window.addEventListener("drop", drop);
    return () => {
      window.removeEventListener("dragenter", enter);
      window.removeEventListener("dragleave", leave);
      window.removeEventListener("dragover", over);
      window.removeEventListener("drop", drop);
    };
  }, [newOpen]);

  // ---- Présentation des nouveautés, une fois par navigateur ----
  const [splash, setSplash] = useState(false);
  useEffect(() => {
    try {
      if (!localStorage.getItem(SPLASH_KEY)) setSplash(true);
    } catch {
      // stockage bloqué : on ne l'impose pas à chaque visite
    }
  }, []);
  const closeSplash = useCallback(() => {
    setSplash(false);
    try {
      localStorage.setItem(SPLASH_KEY, "vu");
    } catch {}
  }, []);

  // ---- Prénom de la personne qui relit ----
  const nameDialog = useRef<HTMLDialogElement>(null);
  const pending = useRef<((value: string | null) => void) | null>(null);
  const [nameDraft, setNameDraft] = useState("");
  useEffect(() => {
    const ask = (e: Event) => {
      pending.current = (e as CustomEvent).detail;
      setNameDraft("");
      nameDialog.current?.showModal();
    };
    window.addEventListener(ASK_PRENOM_EVENT, ask);
    return () => window.removeEventListener(ASK_PRENOM_EVENT, ask);
  }, []);
  function openNameDialog() {
    pending.current = null;
    setNameDraft(prenom);
    nameDialog.current?.showModal();
  }
  function submitName(e: FormEvent) {
    e.preventDefault();
    const value = nameDraft.trim();
    if (!value) return;
    savePrenom(value);
    nameDialog.current?.close();
    pending.current?.(value);
    pending.current = null;
  }
  function cancelName() {
    pending.current?.(null);
    pending.current = null;
  }

  return (
    <>
      <header className="top">
        <Link className="brand" href="/demandes">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/brand/whub-logo.png" alt="W hub" width={1051} height={398} />
          <span>CV Factory</span>
        </Link>
        <span className="spacer" />
        <button type="button" className="btn btn-ghost news" onClick={() => setSplash(true)}>
          <span className="lbl">Nouveautés</span>
        </button>
        <button type="button" className="btn btn-primary" onClick={() => setNewOpen(true)} aria-label="Nouveau CV">
          <IconPlus />
          <span className="lbl">Nouveau CV</span>
        </button>
        <button type="button" className="me" onClick={openNameDialog} title="Ton prénom signe tes validations et tes corrections">
          {prenom || "Ton prénom"}
        </button>
      </header>

      <div className={`work ${detail ? "detail" : ""}`}>
        <nav className="queue" aria-label="Demandes">{queue}</nav>
        <main className="stage" id="stage">{children}</main>
      </div>

      {dragging && <div className="dropall" aria-hidden="true">Lâche le PDF pour créer une demande</div>}

      <NewCvDialog open={newOpen} initialFile={droppedFile} initialError={newOpen ? urlError : null} onClose={closeNew} />

      <dialog ref={nameDialog} className="dlg" aria-labelledby="name-title" onCancel={cancelName}>
        <form className="dlg-body" onSubmit={submitName}>
          <h2 id="name-title">Ton prénom</h2>
          <p>Il signe tes validations et tes corrections. Il est gardé dans ce navigateur, sans compte.</p>
          <div className="field">
            <label htmlFor="reviewer">Prénom</label>
            <input id="reviewer" value={nameDraft} onChange={(e) => setNameDraft(e.target.value)} autoComplete="given-name" placeholder="Ex. Sarah" />
          </div>
          <div className="dlg-foot">
            <div className="btns">
              <button type="button" className="btn btn-ghost" onClick={() => { nameDialog.current?.close(); cancelName(); }}>Annuler</button>
              <button type="submit" className="btn btn-primary">Enregistrer</button>
            </div>
          </div>
        </form>
      </dialog>

      {splash && <Splash onClose={closeSplash} />}
    </>
  );
}
