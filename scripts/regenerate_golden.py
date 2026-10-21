"""Regenerate the golden baselines under tests/golden/.

Run this ONLY when a change to the engine's numbers is intended, and commit the result
on its own so the diff is reviewable.

    uv run python scripts/regenerate_golden.py            # both baselines
    uv run python scripts/regenerate_golden.py us         # only the US-person one

Two baselines, because they prove opposite things. `baseline.json` covers a household
with no US person and must stay byte-identical through every change to `tax/us/`;
`us_baseline.json` covers one that has a US person, and is the only place a change to
the citizenship overlay's numbers shows up at all.
"""

import json
import sys
import tempfile
from pathlib import Path

from vuurtoren.engine import project

# tests/ isn't a package on sys.path by default outside pytest; add it for golden_plan.
sys.path.insert(0, str(Path(__file__).parent.parent / "tests"))
from golden_plan import (  # ty: ignore[unresolved-import]
    EXAMPLE_HOUSEHOLD,
    US_HOUSEHOLD,
    build_seeded_plan,
)

CHECKPOINTS = (12, 60, 360)
GOLDEN_DIR = Path(__file__).parent.parent / "tests" / "golden"

# name -> (household TOML, output file, whether the plan buys a house)
BASELINES = {
    "example": (EXAMPLE_HOUSEHOLD, GOLDEN_DIR / "baseline.json", True),
    "us": (US_HOUSEHOLD, GOLDEN_DIR / "us_baseline.json", False),
}


def regenerate(name: str) -> None:
    """Project one seeded household and write its checkpoints."""
    spec_path, out_file, buy_house = BASELINES[name]
    with tempfile.TemporaryDirectory() as tmp:
        plan = build_seeded_plan(Path(tmp), spec_path, buy_house=buy_house)
    p = project(plan)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(
        json.dumps(
            {
                "generated_from": (
                    f"seed_household({spec_path.name}) + Assumptions() at 2026-01-01"
                    + ("" if buy_house else " (no house purchase)")
                ),
                "net_worth": {str(m): round(float(p.net_worth[0, m]), 2) for m in CHECKPOINTS},
                "fire_number": round(p.fire.fire_number, 2),
                "fi_date": p.fire.fi_dates[0].isoformat() if p.fire.fi_dates[0] else None,
                "investment_tax_total": round(float(p.tax_paid["investment_tax"][0].sum()), 2),
                "housing_adjustment_total": round(
                    float(p.tax_paid["housing_adjustment"][0].sum()), 2
                ),
                "withdrawal_tax_total": round(float(p.tax_paid["withdrawal_tax"][0].sum()), 2),
                "transfer_tax": round(float(p.one_off_costs["transfer_tax"][0]), 2),
            },
            indent=2,
        )
        + "\n"
    )
    print(f"wrote {out_file}")


def main() -> None:
    """Regenerate every baseline, or the one named on the command line."""
    names = sys.argv[1:] or list(BASELINES)
    unknown = [n for n in names if n not in BASELINES]
    if unknown:
        msg = f"unknown baseline(s) {unknown}; known: {list(BASELINES)}"
        raise SystemExit(msg)
    for name in names:
        regenerate(name)


if __name__ == "__main__":
    main()
