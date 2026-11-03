"use client";

// Sans compte, le prénom de la personne qui relit est gardé dans son navigateur.
// Il signe les validations et les corrections.
import { useSyncExternalStore } from "react";

const KEY = "whub.prenom";
const EVENT = "whub:prenom";
const ASK = "whub:ask-prenom";

export function readPrenom(): string {
  try {
    return localStorage.getItem(KEY) ?? "";
  } catch {
    return "";
  }
}

export function savePrenom(value: string) {
  const clean = value.replace(/\s+/g, " ").trim().slice(0, 40);
  try {
    if (clean) localStorage.setItem(KEY, clean);
    else localStorage.removeItem(KEY);
  } catch {
    // stockage indisponible (navigation privée) : le prénom vaut pour cette page seulement
  }
  memory = clean;
  window.dispatchEvent(new Event(EVENT));
}

let memory = "";

function subscribe(callback: () => void) {
  window.addEventListener(EVENT, callback);
  window.addEventListener("storage", callback);
  return () => {
    window.removeEventListener(EVENT, callback);
    window.removeEventListener("storage", callback);
  };
}

export function usePrenom() {
  return useSyncExternalStore(subscribe, () => readPrenom() || memory, () => "");
}

/** Demande le prénom s'il n'est pas encore connu. Résout avec le prénom, ou null si la personne annule. */
export function ensurePrenom(): Promise<string | null> {
  const known = readPrenom() || memory;
  if (known) return Promise.resolve(known);
  return new Promise((resolve) => {
    window.dispatchEvent(new CustomEvent(ASK, { detail: resolve }));
  });
}

export const ASK_PRENOM_EVENT = ASK;
