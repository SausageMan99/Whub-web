# Noël invalid JSON

Regression fixture for a long CV (222 KB PDF, 25,388 chars extracted, 441 lines, 23,923 sanitized) whose structuring call returned unparseable/truncated JSON after ~2m40s (request 5c44e3d8, 2026-09-03, `structuring_invalid_json`).

Used to verify the error taxonomy split (pre-model vs model timeout vs invalid JSON) and the bounded automatic retry policy: a same-prompt retry should either succeed or fail honestly after the retry budget.
