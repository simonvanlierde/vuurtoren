"""drop unused household and scenario columns

Revision ID: 46b4436a7eb9
Revises: 2e195eacbd54
Create Date: 2026-11-10 13:15:03.918555

Nothing read `household.base_currency` (reporting is always EUR) or
`scenario.is_baseline`. The same upgrade renames the stored assumption override
`aow_growth_months_per_decade` to `state_pension_growth_months_per_decade`: the app no
longer accepts the old name, and a scenario still carrying it would refuse to project.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "46b4436a7eb9"
down_revision: Union[str, Sequence[str], None] = "2e195eacbd54"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_OLD, _NEW = "aow_growth_months_per_decade", "state_pension_growth_months_per_decade"
_scenario = sa.table("scenario", sa.column("id", sa.Integer), sa.column("overrides", sa.JSON))


def upgrade() -> None:
    """Drop the two columns and move the old assumption name to the new one."""
    connection = op.get_bind()
    for row in connection.execute(sa.select(_scenario.c.id, _scenario.c.overrides)).all():
        overrides = dict(row.overrides or {})
        assumptions = dict(overrides.get("assumptions") or {})
        if _OLD not in assumptions:
            continue
        # Where both names are stored, the new one is kept.
        old = assumptions.pop(_OLD)
        assumptions.setdefault(_NEW, old)
        overrides["assumptions"] = assumptions
        connection.execute(
            sa.update(_scenario).where(_scenario.c.id == row.id).values(overrides=overrides)
        )

    # Plain ALTER TABLE ... DROP COLUMN (SQLite 3.35+), not batch mode: batch recreates
    # the table, and dropping `household` fails the foreign key every other table holds.
    op.drop_column("household", "base_currency")
    op.drop_column("scenario", "is_baseline")


def downgrade() -> None:
    """Put the columns back with the values the app always wrote.

    The renamed assumption stays renamed: the previous version accepts both names.
    """
    op.add_column(
        "scenario",
        sa.Column("is_baseline", sa.BOOLEAN(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "household",
        sa.Column("base_currency", sa.VARCHAR(), nullable=False, server_default="EUR"),
    )
