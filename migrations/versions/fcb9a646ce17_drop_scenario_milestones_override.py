"""drop scenario milestones override

Revision ID: fcb9a646ce17
Revises: 7723b1f65327
Create Date: 2026-10-21 01:19:33.441794

v0.1.0 stored an empty `milestones` group in every scenario's overrides: a
per-milestone patch it never applied. `ScenarioOverrides` now refuses unknown keys,
so the upgrade strips the empty group. A non-empty one could be saved through the
API but never projected; the upgrade stops on it rather than drop what a user typed.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "fcb9a646ce17"
down_revision: Union[str, Sequence[str], None] = "7723b1f65327"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_scenario = sa.table("scenario", sa.column("id", sa.Integer), sa.column("overrides", sa.JSON))


def _rewrite(change) -> None:
    """Apply `change` to each scenario's overrides dict and store the ones it alters."""
    connection = op.get_bind()
    for row in connection.execute(sa.select(_scenario.c.id, _scenario.c.overrides)).all():
        overrides = dict(row.overrides or {})
        if change(row.id, overrides):
            connection.execute(
                sa.update(_scenario).where(_scenario.c.id == row.id).values(overrides=overrides)
            )


def upgrade() -> None:
    """Strip the empty `milestones` group; refuse a scenario whose group is not empty."""
    non_empty: list[int] = []

    def strip(scenario_id: int, overrides: dict) -> bool:
        if "milestones" not in overrides:
            return False
        if overrides["milestones"]:
            non_empty.append(scenario_id)
        del overrides["milestones"]
        return True

    _rewrite(strip)
    if non_empty:
        # Raising rolls the whole upgrade back, so the file stays a working v0.1.0 database.
        names = ", ".join(f"scenario {i}" for i in non_empty)
        msg = (
            f"{names}: a per-milestone override, which no version of vuurtoren applied "
            "and this one no longer stores. Open the database with v0.1.0, remove the "
            "scenario's `milestones` override (or delete the scenario), then upgrade again."
        )
        raise RuntimeError(msg)


def downgrade() -> None:
    """Put the empty `milestones` group back, as v0.1.0 wrote it."""

    def restore(_scenario_id: int, overrides: dict) -> bool:
        overrides.setdefault("milestones", {})
        return True

    _rewrite(restore)
