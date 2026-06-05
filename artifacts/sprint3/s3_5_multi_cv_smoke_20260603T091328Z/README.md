# S3-5 Evidence ledger — multi-CV local smoke

Run: `20260603T091328Z`
Artifacts: `/root/whub-cv-factory/artifacts/sprint3/s3_5_multi_cv_smoke_20260603T091328Z`
Montage: `/root/whub-cv-factory/artifacts/sprint3/s3_5_multi_cv_smoke_20260603T091328Z/s3_5_current_pdfs_first_last_montage.png`

| Case | Type | QA | Pages before→after | Taste before→after | Coverage | Layout issues after |
|---|---|---:|---:|---:|---:|---|
| zahia_like_location_and_role_facts | real_anonymized_s2_fixture | GO | 1→1 | 100→100 | 8 checked / 0 missing | [] |
| oussama_like_rpa_copy_preservation | real_anonymized_s2_fixture | GO | 2→1 | 66→100 | 17 checked / 0 missing | [] |
| thorez_like_realizations_and_tools_coverage | real_anonymized_s2_fixture | GO | 1→1 | 100→100 | 17 checked / 0 missing | [] |
| s3_4_zahia_oussama_like_heavy_layout | sprint3_heavy_layout_fixture | GO | 5→5 | 100→100 | 98 checked / 0 missing | [] |

No prod action performed: no push, no whub-cv-worker.service restart, no Vercel deploy.
