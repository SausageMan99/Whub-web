"use client";

import { useEffect, useRef } from "react";

// Présentation de la nouvelle version, affichée une fois par navigateur.
// Le contrôle qualité « relit » la phrase d'accueil et y signale un point à vérifier.
export const SPLASH_KEY = "whub.nouveautes.2026-11";

const ECRAN = [
  ["Un seul écran de travail", "la file des demandes à gauche, le CV au centre."],
  ["Le CV s’affiche directement", "plus besoin de le télécharger pour le relire."],
  ["Les points à vérifier sont signalés sur la page", "avec une correction prête en un clic."],
  ["Nouveau statut « Prêt à envoyer »", "signé de ton prénom, pour savoir ce qui est parti."],
  ["Glisse un PDF n’importe où", "pour lancer un nouveau CV."],
  ["Recherche par prénom ou par poste", "et une file regroupée par action à faire."],
  ["Les versions repartent à 1 pour chaque candidat", "fini la « version 246 »."],
];

const MOTEUR = [
  ["Remis en service après la panne d’octobre", "9 demandes bloquées récupérées."],
  ["Nouveau moteur de lecture des CV", "Gemini 2.5 Flash, Claude Haiku en secours, réponses vérifiées par un schéma strict, sans réutilisation des données."],
  ["Les PDF scannés sont lus", "par reconnaissance de caractères ; une vérification humaine est demandée si même ça échoue."],
  ["Plus aucun mot effacé au nettoyage", "ASP.NET, « LinkedIn Ads », ponctuation, ligatures et puces Word."],
  ["CV longs mieux tenus", "langues, certifications et missions conservées d’un bout à l’autre."],
  ["Compétences des CV Canva à deux colonnes", "lues d’après leur mise en forme."],
  ["Pagination revue", "plus de dernière page presque vide ni de titre seul en bas de page."],
  ["Beaucoup moins de fausses alertes", "et une alerte de santé automatique avec un test complet chaque matin."],
];

export function Splash({ onClose }: { onClose: () => void }) {
  const button = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    const t = window.setTimeout(() => button.current?.focus({ preventScroll: true }), 2400);
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => {
      window.clearTimeout(t);
      window.removeEventListener("keydown", onKey);
    };
  }, [onClose]);

  return (
    <div className="splash" role="dialog" aria-modal="true" aria-labelledby="splash-title">
      <div className="splash-sheet">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img className="splash-logo" src="/brand/whub-logo.png" alt="W hub smart connect" />
        <h1 id="splash-title">
          Votre tout nouveau logiciel par votre ancien stagiaire{" "}
          <span className="fav">
            préféré
            <span className="mark" aria-hidden="true" />
          </span>
          , Clément.
        </h1>
        <p className="aside">
          <span className="n" aria-hidden="true">1</span>
          <span><b>Point à vérifier.</b> Information absente du CV source. Fidélité à confirmer par la relectrice ou le relecteur.</span>
        </p>

        <div className="cols">
          <section aria-labelledby="splash-ecran">
            <h2 id="splash-ecran">Ce qui change à l’écran</h2>
            <ul>{ECRAN.map(([b, rest]) => <li key={b}><b>{b}</b>, {rest}</li>)}</ul>
          </section>
          <section aria-labelledby="splash-moteur">
            <h2 id="splash-moteur">Ce qui change dans le moteur</h2>
            <ul>{MOTEUR.map(([b, rest]) => <li key={b}><b>{b}</b> : {rest}</li>)}</ul>
          </section>
        </div>

        <div className="go">
          <button ref={button} type="button" className="btn btn-primary" onClick={onClose}>Ouvrir les demandes</button>
          <span className="hint">Cette présentation reste accessible depuis « Nouveautés », en haut de l’écran.</span>
        </div>
      </div>
    </div>
  );
}
