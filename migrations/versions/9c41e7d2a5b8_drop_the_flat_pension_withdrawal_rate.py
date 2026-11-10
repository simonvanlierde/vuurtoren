"""drop the flat pension withdrawal rate from stored tax overrides

Revision ID: 9c41e7d2a5b8
Revises: 46b4436a7eb9
Create Date: 2026-11-10 15:20:00.000000

A pension withdrawal is now taxed through the Box 1 brackets, so the config field
`pension_withdrawal_rate` is gone. v0.1.1's tax panel could override it, and a scenario
still carrying that override would refuse to project. Data only: no schema change.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "9c41e7d2a5b8"
down_revision: Union[str, Sequence[str], None] = "46b4436a7eb9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_FIELD = "pension_withdrawal_rate"
_scenario = sa.table("scenario", sa.column("id", sa.Integer), sa.column("overrides", sa.JSON))


def upgrade() -> None:
    """Pop the field from every country and year of every scenario's tax overrides."""
    connection = op.get_bind()
    for row in connection.execute(sa.select(_scenario.c.id, _scenario.c.overrides)).all():
        overrides = dict(row.overrides or {})
        tax = overrides.get("tax") or {}
        years = [year for country in tax.values() for year in country.values()]
        if not any(_FIELD in year for year in years):
            continue
        for year in years:
            year.pop(_FIELD, None)
        connection.execute(
            sa.update(_scenario).where(_scenario.c.id == row.id).values(overrides=overrides)
        )


def downgrade() -> None:
    """Nothing to restore: the previous version runs without the override."""
