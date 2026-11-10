"""give an ownerless pension in a one-person household that person

Revision ID: d41f7a3c9e60
Revises: 9c41e7d2a5b8
Create Date: 2026-11-10 17:00:00.000000

A PENSION account now needs an owner: its payout is taxed on the owner's Box 1 income
and AOW date. One saved before that rule may have none. In a household with one person
it can only be theirs; elsewhere the owner is unknown, and the projection refuses the
account until the user picks one. Data only: no schema change.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d41f7a3c9e60"
down_revision: Union[str, Sequence[str], None] = "9c41e7d2a5b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_account = sa.table(
    "account",
    sa.column("id", sa.Integer),
    sa.column("household_id", sa.Integer),
    sa.column("owner_person_id", sa.Integer),
    sa.column("kind", sa.String),
)
_person = sa.table("person", sa.column("id", sa.Integer), sa.column("household_id", sa.Integer))


def upgrade() -> None:
    """Set the owner of each ownerless PENSION account whose household has one person."""
    connection = op.get_bind()
    only_person = dict(
        connection.execute(
            sa.select(_person.c.household_id, sa.func.min(_person.c.id))
            .group_by(_person.c.household_id)
            .having(sa.func.count() == 1)
        )
        .tuples()
        .all()
    )
    for hh_id, person_id in only_person.items():
        connection.execute(
            sa.update(_account)
            .where(
                _account.c.household_id == hh_id,
                _account.c.kind == "PENSION",
                _account.c.owner_person_id.is_(None),
            )
            .values(owner_person_id=person_id)
        )


def downgrade() -> None:
    """Nothing to restore: the previous version runs with the owner set."""
