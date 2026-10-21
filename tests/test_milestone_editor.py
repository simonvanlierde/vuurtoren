"""The milestone editor's lists match the engine's milestone union.

`MILESTONE_TYPES` and `PARAM_FIELDS` in `frontend/src/components/editor/milestoneDraft.ts`
are hand-written copies of `domain.MilestoneParams`. TypeScript cannot see the Python
union, so this reads the TypeScript source and compares: a milestone type or param field
added on one side only fails here instead of shipping invisible in the editor.
"""

import re
from pathlib import Path
from typing import get_args

from vuurtoren import domain

_SOURCE = (
    Path(__file__).resolve().parent.parent
    / "frontend"
    / "src"
    / "components"
    / "editor"
    / "milestoneDraft.ts"
).read_text(encoding="utf-8")


def _engine_params() -> dict[str, set[str]]:
    union, _field = get_args(domain.MilestoneParams)
    return {
        model.model_fields["type"].default: set(model.model_fields) - {"type"}
        for model in get_args(union)
    }


def _editor_types() -> set[str]:
    begin = _SOURCE.index("export const MILESTONE_TYPES = [")
    body = _SOURCE[begin : _SOURCE.index("] as const;", begin)]
    return set(re.findall(r'"(\w+)"', body))


def _editor_params() -> dict[str, set[str]]:
    begin = _SOURCE.index("const PARAM_FIELDS")
    body = _SOURCE[_SOURCE.index("> = {", begin) : _SOURCE.index("\n};", begin)]
    params: dict[str, set[str]] = {}
    current = None
    for line in body.splitlines():
        if line.lstrip().startswith("//"):
            continue
        if start := re.match(r"^  (\w+): \[", line):
            current = params.setdefault(start.group(1), set())
        if current is not None:
            current.update(re.findall(r'\["(\w+)",', line))
    return params


def test_the_type_picker_lists_every_engine_milestone_type() -> None:
    """A type the engine runs but the picker lacks cannot be created in the editor."""
    assert _editor_types() == set(_engine_params())


def test_each_type_edits_exactly_the_engine_s_params() -> None:
    """A missing field leaves the draft unsendable; an extra one fails validation."""
    assert _editor_params() == _engine_params()
