# W hub CV Factory

MVP interne pour transformer des CV candidats en CV client-facing W hub.

## Stack

- Web: Next.js App Router + Tailwind
- Auth/DB/Storage: Supabase
- Worker: Python + Hermes + renderer W hub
- Déploiement: Vercel + VPS

## MVP

1. Connexion interne par magic link Supabase.
2. Upload CV PDF + consignes.
3. Dashboard de suivi.
4. Worker asynchrone de génération.
5. PDF final W hub avec QA bloquante.
6. Commentaires de modification et versions V1/V2/V3.

## Vérification locale avant release

Lancer la gate complète depuis la racine du repo :

```bash
scripts/verify_all.sh
```

La commande exécute le lint/typecheck web compatible Next 16, les tests web, le build Next, les tests worker, la compilation Python de `workers/cv-worker/src`, `workers/cv-worker/renderer` et `workers/cv-worker/scripts`, le preflight assets/fonts W hub repo-local validé par SHA-256 (`workers/cv-worker/scripts/verify_whub_assets.py`) et `git diff --check`.

## Sécurité non négociable

- Accès limité aux emails whitelistés dans `allowed_users`.
- Buckets Supabase privés uniquement.
- PDF final bloqué si coordonnées candidat détectées.
- Logo et watermark W hub exacts, extraits d’un CV validé.
