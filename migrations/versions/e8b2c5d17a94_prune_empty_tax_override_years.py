"""prune tax override years and countries left empty

Revision ID: e8b2c5d17a94
Revises: d41f7a3c9e60
Create Date: 2026-11-10 18:00:00.000000

Dropping `pension_withdrawal_rate` (9c41e7d2a5b8) left an empty year object where that
was the year's only override, and that revision may already have run. This removes each
empty year, then each country left with no year. Data only: no schema change.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e8b2c5d17a94"
down_revision: Union[str, Sequence[str], None] = "d41f7a3c9e60"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_scenario = sa.table("scenario", sa.column("id", sa.Integer), sa.column("overrides", sa.JSON))


def upgrade() -> None:
    """Rewrite every scenario whose tax overrides hold an empty year or country."""
    connection = op.get_bind()
    for row in connection.execute(sa.select(_scenario.c.id, _scenario.c.overrides)).all():
        overrides = dict(row.overrides or {})
        tax = overrides.get("tax") or {}
        pruned = {
            country: kept
            for country, years in tax.items()
            if (kept := {year: o for year, o in years.items() if o})
        }
        if pruned == tax:
            continue
        overrides["tax"] = pruned
        connection.execute(
            sa.update(_scenario).where(_scenario.c.id == row.id).values(overrides=overrides)
        )


def downgrade() -> None:
    """Nothing to restore: an empty year overrides nothing."""
