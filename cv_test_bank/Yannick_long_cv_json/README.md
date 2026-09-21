# Yannick long CV JSON

Regression fixture for a long CV (2.7 MB PDF, ~21,643 chars extracted) that failed `structuring_invalid_json` twice: first attempt ~11m28s, manual retry ~2m20s (request d2652dea, 2026-09-03 10:18–10:56).

Guards the long-CV / multi-block structuring path and the JSON reliability + retry work. Expected after the fix: honest failure categories, bounded auto-retry, and ideally a first-pass success.
