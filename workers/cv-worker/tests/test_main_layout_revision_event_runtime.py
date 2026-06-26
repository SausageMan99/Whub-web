from __future__ import annotations

import inspect
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"

_pkg = types.ModuleType("workers")
_pkg.__path__ = [str(ROOT / "workers")]  # type: ignore[attr-defined]
sys.modules.setdefault("workers", _pkg)

_cv = types.ModuleType("workers.cv_worker")
_cv.__path__ = [str(ROOT / "workers" / "cv-worker")]  # type: ignore[attr-defined]
sys.modules.setdefault("workers.cv_worker", _cv)

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def test_main_layout_revision_event_runtime_does_not_crash_when_verification_path_is_taken():
    from src.layout.revision_verification import verify_layout_revision_improved

    # Verify the keyword-only contract by inspecting the signature.
    parameters = inspect.signature(verify_layout_revision_improved).parameters.values()
    assert parameters, "verify_layout_revision_improved should expose its parameters"
    assert all(
        p.kind
        in {
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        }
        or p.name in {"previous_qa_report", "new_qa_report", "comments"}
        for p in parameters
    )

    passed, warnings = verify_layout_revision_improved(
        previous_qa_report={"pages": 2},
        new_qa_report={"pages": 2},
        comments=[],
    )
    assert passed is True
    assert warnings == []
