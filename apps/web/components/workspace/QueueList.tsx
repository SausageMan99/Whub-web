"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import type { QueueItem } from "@/lib/workspace-data";
import { GROUPS, shortAgo, stepLine } from "@/lib/workspace";
import { IconSearch } from "./icons";

const VISIBLE_PER_GROUP = 8;

function subline(item: QueueItem) {
  if (item.group === "fab") return stepLine(item.step);
  if (item.group === "bloque") {
    return item.status === "needs_human_review" ? "CV source illisible" : item.status === "qa_failed" ? "PDF bloqué par le contrôle" : "Mise au format en échec";
  }
  const version = `Version ${item.versionCount || 1}`;
  if (item.group === "pret") return item.validatedBy ? `${version}, validée par ${item.validatedBy}` : `${version}, validée`;
  return item.notesCount ? `${version}, ${item.notesCount} point${item.notesCount > 1 ? "s" : ""} à vérifier` : `${version}, aucun point signalé`;
}

export function QueueList({ items }: { items: QueueItem[] }) {
  const pathname = usePathname();
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [now, setNow] = useState(() => Date.now());

  // La file se met à jour seule : souvent pendant une mise au format, rarement sinon.
  const busy = items.some((i) => i.group === "fab");
  useEffect(() => {
    const timer = window.setInterval(() => {
      if (document.visibilityState === "visible") {
        router.refresh();
        setNow(Date.now());
      }
    }, busy ? 6000 : 30000);
    return () => window.clearInterval(timer);
  }, [busy, router]);

  const filtered = useMemo(() => {
    const q = query.trim().toLocaleLowerCase("fr");
    if (!q) return items;
    return items.filter((i) => `${i.prenom} ${i.poste ?? ""}`.toLocaleLowerCase("fr").includes(q));
  }, [items, query]);

  return (
    <>
      <div className="search" role="search">
        <IconSearch />
        <label className="sr-only" htmlFor="q">Rechercher un candidat</label>
        <input id="q" type="search" placeholder="Rechercher un prénom, un poste" value={query} onChange={(e) => setQuery(e.target.value)} autoComplete="off" />
      </div>
      {!items.length && <p className="empty-q">Aucune demande pour l’instant. Glisse un CV en PDF dans la fenêtre pour lancer la première.</p>}
      {items.length > 0 && !filtered.length && <p className="empty-q">Aucune demande pour « {query} ». Vérifie l’orthographe du prénom.</p>}
      {GROUPS.map((group) => {
        const list = filtered.filter((i) => i.group === group.key).sort((a, b) => b.updatedAt.localeCompare(a.updatedAt));
        if (!list.length) return null;
        const open = expanded[group.key] || query.trim() !== "";
        const shown = open ? list : list.slice(0, VISIBLE_PER_GROUP);
        return (
          <section className="group" key={group.key} aria-labelledby={`g-${group.key}`}>
            <h2 id={`g-${group.key}`}>{group.label} <b>{list.length}</b></h2>
            <ul>
              {shown.map((item) => {
                const href = `/demandes/${item.id}`;
                const current = pathname === href;
                return (
                  <li key={item.id}>
                    <Link className="item" href={href} aria-current={current ? "page" : undefined} scroll={false}>
                      <span className={`dot d-${item.group}`} aria-hidden="true" />
                      <span>
                        <span className="who">{item.prenom}</span>
                        {item.poste && <span className="what">{item.poste}</span>}
                        <span className={`sub ${item.group === "bloque" ? "s-bloque" : ""}`}>{subline(item)}</span>
                      </span>
                      <span className="when" suppressHydrationWarning>{shortAgo(item.updatedAt, now)}</span>
                    </Link>
                  </li>
                );
              })}
            </ul>
            {list.length > shown.length && (
              <button className="more" type="button" onClick={() => setExpanded((e) => ({ ...e, [group.key]: true }))}>
                Afficher les {list.length - shown.length} plus anciennes
              </button>
            )}
          </section>
        );
      })}
    </>
  );
}
