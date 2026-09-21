# Benjamin control chars

Regression fixture for a source PDF whose embedded fonts leak NUL (`0x00`) and C0 control bytes into PyMuPDF extraction (638 NUL bytes on the 2026-09-08 source).

Historical failure (requests 29eb8f45 / a9df0b89 / e4d73d00 / 6e223c4a / dacf6a48 / 06f294fe, 2026-09-08/09): the structuring runner passes the whole prompt as `subprocess` argv, so `subprocess.run` raised `ValueError: embedded null byte` in under a second, before any model call. `classify_structuring_error` had no pattern for it and fell through to `transient_model_failure`, so the portal showed a bogus "temporary" failure and every manual retry re-crashed identically.

Expected after the fix: control characters stripped/escaped before the runner (plus a distinct non-transient error category as safety net); the case must reach `draft_ready`/`ready` like a normal CV.
