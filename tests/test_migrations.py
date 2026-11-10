"""Tests that the migrations describe the same schema the mappings do.

The tests build their databases with `create_all`, which is fast but only ever adds
whole tables; the app builds its own with `upgrade_to_head`. Nothing keeps those two in
step on its own — a column added to `tables.py` without a matching revision passes every
other test in this suite and then fails at runtime with "no such column". That is the
drift these tests exist to catch.
"""

from __future__ import annotations

import json
import threading
from typing import TYPE_CHECKING

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, inspect, text

from vuurtoren.db import _MIGRATIONS, Base, create_all, make_engine, upgrade_to_head
from vuurtoren.tables import AccountRow  # noqa: F401  # registers the mappings

if TYPE_CHECKING:
    from pathlib import Path


def _columns(engine: Engine) -> dict[str, set[str]]:
    inspector = inspect(engine)
    return {
        name: {column["name"] for column in inspector.get_columns(name)}
        for name in inspector.get_table_names()
        if name != "alembic_version"  # alembic's own bookkeeping, not part of the model
    }


def test_migrations_produce_the_mapped_schema(tmp_path: Path) -> None:
    """Running every migration leaves exactly the tables and columns the mappings declare."""
    migrated = make_engine(tmp_path / "migrated.db")
    upgrade_to_head(migrated)

    created = make_engine(tmp_path / "created.db")
    create_all(created)

    assert _columns(migrated) == _columns(created)


def test_no_mapping_change_is_missing_a_migration(tmp_path: Path) -> None:
    """Autogenerate against the migrated schema finds nothing left to do.

    This is the stricter half: it compares types and constraints too, so it fails on a
    column whose *definition* changed as well as on one that was added outright.
    """
    engine = make_engine(tmp_path / "head.db")
    upgrade_to_head(engine)

    with engine.connect() as connection:
        context = MigrationContext.configure(connection)
        diff = compare_metadata(context, Base.metadata)

    assert diff == [], f"tables.py has changes with no migration: {diff}"


def test_the_migrations_have_one_head() -> None:
    """Two branches each adding a revision on the same parent leave two heads.

    `upgrade head` then refuses to run, and the app cannot open its database.
    """
    config = Config()
    config.set_main_option("script_location", str(_MIGRATIONS))
    assert len(ScriptDirectory.from_config(config).get_heads()) == 1


def test_concurrent_upgrades_do_not_collide(tmp_path: Path) -> None:
    """Several threads may upgrade at once — the app's cold start does exactly this.

    Alembic keeps its environment in process-global module state, so unserialised
    upgrades corrupt each other and fail with a KeyError while tearing the context down.
    """
    threads_n = 3
    barrier = threading.Barrier(threads_n)
    failures: list[BaseException] = []

    def upgrade(index: int) -> None:
        barrier.wait()
        try:
            upgrade_to_head(make_engine(tmp_path / f"concurrent{index}.db"))
        except BaseException as exc:  # noqa: BLE001 -- the assertion below is the report
            failures.append(exc)

    threads = [threading.Thread(target=upgrade, args=(i,)) for i in range(threads_n)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert failures == []


# --- data migrations ---

_BEFORE_DROP = "7723b1f65327"  # the head v0.1.0 shipped


def _migrate(engine: Engine, revision: str, *, down: bool = False) -> None:
    config = Config()
    config.set_main_option("script_location", str(_MIGRATIONS))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        (command.downgrade if down else command.upgrade)(config, revision)


def _overrides(engine: Engine) -> dict[int, dict[str, object]]:
    with engine.connect() as connection:
        rows = connection.execute(text("SELECT id, overrides FROM scenario ORDER BY id"))
        return {row.id: json.loads(row.overrides) for row in rows}


def _seed_0_1_0_scenarios(engine: Engine, *overrides: dict[str, object]) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO household"
                " (id, name, base_currency, tax_country, fiscal_partners, life_expectancy_age)"
                " VALUES (1, 'h', 'EUR', 'NL', 0, 95)"
            )
        )
        for i, o in enumerate(overrides, start=1):
            connection.execute(
                text(
                    "INSERT INTO scenario (id, household_id, name, is_baseline, overrides)"
                    " VALUES (:id, 1, 's', 0, :o)"
                ),
                {"id": i, "o": json.dumps(o)},
            )


def test_dropping_scenario_milestones_strips_the_empty_key_and_restores_it(
    tmp_path: Path,
) -> None:
    """v0.1.0 stored `"milestones": {}` in every scenario; the upgrade removes it.

    The downgrade puts it back, so a v0.1.0 build reads the file as it wrote it.
    """
    engine = make_engine(tmp_path / "v010.db")
    _migrate(engine, _BEFORE_DROP)
    _seed_0_1_0_scenarios(
        engine,
        {"accounts": {}, "milestones": {}, "added_milestones": [], "tax": {}},
        {"cash_flows": {"3": {"amount_monthly": "100"}}, "milestones": {}},
    )

    _migrate(engine, "head")
    assert _overrides(engine) == {
        1: {"accounts": {}, "added_milestones": [], "tax": {}},
        2: {"cash_flows": {"3": {"amount_monthly": "100"}}},
    }

    _migrate(engine, _BEFORE_DROP, down=True)
    assert _overrides(engine) == {
        1: {"accounts": {}, "added_milestones": [], "tax": {}, "milestones": {}},
        2: {"cash_flows": {"3": {"amount_monthly": "100"}}, "milestones": {}},
    }


def test_dropping_scenario_milestones_refuses_a_non_empty_patch(tmp_path: Path) -> None:
    """v0.1.0 saved a per-milestone patch it could never apply; the upgrade will not drop it.

    The whole upgrade rolls back, so the file stays a working v0.1.0 database.
    """
    engine = make_engine(tmp_path / "v010.db")
    _migrate(engine, _BEFORE_DROP)
    stored: dict[str, object] = {"milestones": {"1": {"on_date": "2030-01-01"}}}
    _seed_0_1_0_scenarios(engine, {"milestones": {}}, stored)

    with pytest.raises(RuntimeError, match=r"scenario 2\b"):
        _migrate(engine, "head")
    assert _overrides(engine) == {1: {"milestones": {}}, 2: stored}
    with engine.connect() as connection:
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar() == (
            _BEFORE_DROP
        )


_BEFORE_COLUMN_DROP = "2e195eacbd54"


def test_the_old_state_pension_assumption_name_is_renamed_on_upgrade(tmp_path: Path) -> None:
    """A scenario stored under `aow_growth_months_per_decade` still projects after the upgrade.

    The app no longer accepts the old name, so the upgrade moves it; where both are stored
    the new one is kept. The downgrade restores the dropped columns on existing rows.
    """
    engine = make_engine(tmp_path / "renamed.db")
    _migrate(engine, _BEFORE_COLUMN_DROP)
    _seed_0_1_0_scenarios(
        engine,
        {"assumptions": {"aow_growth_months_per_decade": 6, "inflation": 0.03}},
        {
            "assumptions": {
                "aow_growth_months_per_decade": 6,
                "state_pension_growth_months_per_decade": 4,
            }
        },
        {"tax": {}},
    )

    _migrate(engine, "head")
    assert _overrides(engine) == {
        1: {"assumptions": {"state_pension_growth_months_per_decade": 6, "inflation": 0.03}},
        2: {"assumptions": {"state_pension_growth_months_per_decade": 4}},
        3: {"tax": {}},
    }

    _migrate(engine, _BEFORE_COLUMN_DROP, down=True)
    with engine.connect() as connection:
        assert connection.execute(text("SELECT base_currency FROM household")).scalar() == "EUR"
        assert connection.execute(text("SELECT is_baseline FROM scenario")).scalar() == 0


_BEFORE_FLAT_RATE_DROP = "46b4436a7eb9"


def _seed_scenarios(engine: Engine, *overrides: dict[str, object]) -> None:
    """One household and a scenario per override, in the schema after v0.1.1's drops."""
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO household (id, name, tax_country, fiscal_partners,"
                " life_expectancy_age) VALUES (1, 'h', 'NL', 0, 95)"
            )
        )
        for i, o in enumerate(overrides, start=1):
            connection.execute(
                text(
                    "INSERT INTO scenario (id, household_id, name, overrides)"
                    " VALUES (:id, 1, 's', :o)"
                ),
                {"id": i, "o": json.dumps(o)},
            )


def test_the_removed_flat_pension_rate_is_dropped_from_stored_tax_overrides(
    tmp_path: Path,
) -> None:
    """v0.1.1's tax panel could override `pension_withdrawal_rate`, which no longer exists.

    Left in place, every projection of that scenario would refuse the unknown field. The
    upgrade pops it from each country and year and leaves every other override alone.
    """
    engine = make_engine(tmp_path / "flat-rate.db")
    _migrate(engine, _BEFORE_FLAT_RATE_DROP)
    stored: list[dict[str, object]] = [
        {
            "tax": {
                "NL": {
                    "2026": {"pension_withdrawal_rate": "0.40", "box3_rate": "0.37"},
                    "2027": {"pension_withdrawal_rate": "0.41"},
                }
            }
        },
        {"assumptions": {"inflation": 0.03}},
        {"tax": {"NL": {"2026": {"pension_withdrawal_rate": "0.40"}}}},
    ]
    _seed_scenarios(engine, *stored)

    _migrate(engine, "head")
    assert _overrides(engine) == {
        1: {"tax": {"NL": {"2026": {"box3_rate": "0.37"}}}},
        2: {"assumptions": {"inflation": 0.03}},
        3: {"tax": {}},
    }


_BEFORE_EMPTY_TAX_PRUNE = "d41f7a3c9e60"


def test_tax_override_years_left_empty_are_pruned(tmp_path: Path) -> None:
    """A database that ran the flat-rate drop before it pruned holds empty year objects.

    The upgrade removes each empty year, then each country left with no year, and keeps
    every override that still says something.
    """
    engine = make_engine(tmp_path / "empty-years.db")
    _migrate(engine, _BEFORE_EMPTY_TAX_PRUNE)
    _seed_scenarios(
        engine,
        {"tax": {"NL": {"2026": {}, "2027": {"box3_rate": "0.37"}}, "AT": {"2026": {}}}},
        {"tax": {"NL": {}}, "assumptions": {"inflation": 0.03}},
    )

    _migrate(engine, "head")
    assert _overrides(engine) == {
        1: {"tax": {"NL": {"2027": {"box3_rate": "0.37"}}}},
        2: {"tax": {}, "assumptions": {"inflation": 0.03}},
    }


_BEFORE_PENSION_OWNERS = "9c41e7d2a5b8"


def test_an_ownerless_pension_in_a_one_person_household_gets_that_person(
    tmp_path: Path,
) -> None:
    """A PENSION account saved before every one needed an owner was taxed as nobody's.

    Where the household has one person, the pension can only be theirs. With two people
    or none the owner is unknown, so the account is left for the user to fix; the
    projection refuses it until then.
    """
    engine = make_engine(tmp_path / "owners.db")
    _migrate(engine, _BEFORE_PENSION_OWNERS)
    with engine.begin() as connection:
        for hh in (1, 2, 3):
            connection.execute(
                text(
                    "INSERT INTO household (id, name, tax_country, fiscal_partners,"
                    " life_expectancy_age) VALUES (:id, 'h', 'NL', 0, 95)"
                ),
                {"id": hh},
            )
        for person, hh in ((1, 1), (2, 2), (3, 2)):
            connection.execute(
                text(
                    "INSERT INTO person (id, household_id, name, birth_date, tax_residence)"
                    " VALUES (:id, :hh, 'p', '1960-01-01', 'NL')"
                ),
                {"id": person, "hh": hh},
            )
        accounts = [
            (1, 1, None, "PENSION"),  # alone in its household: gets person 1
            (2, 1, None, "CASH"),  # not a pension: untouched
            (3, 2, None, "PENSION"),  # two people: owner unknown
            (4, 2, 3, "PENSION"),  # already owned
            (5, 3, None, "PENSION"),  # nobody to own it
        ]
        for account, hh, owner, kind in accounts:
            connection.execute(
                text(
                    "INSERT INTO account (id, household_id, owner_person_id, name, kind,"
                    " tax_treatment, price_source, currency, return_assumption,"
                    " volatility_assumption)"
                    " VALUES (:id, :hh, :owner, 'a', :kind, 'nl.box1_pension', 'MANUAL',"
                    " 'EUR', 0, 0)"
                ),
                {"id": account, "hh": hh, "owner": owner, "kind": kind},
            )

    _migrate(engine, "head")
    with engine.connect() as connection:
        rows = connection.execute(text("SELECT id, owner_person_id FROM account ORDER BY id"))
        assert dict(rows.tuples().all()) == {1: 1, 2: None, 3: None, 4: 3, 5: None}

    _migrate(engine, _BEFORE_PENSION_OWNERS, down=True)
    with engine.connect() as connection:
        owner = connection.execute(text("SELECT owner_person_id FROM account WHERE id = 1"))
        assert owner.scalar() == 1
