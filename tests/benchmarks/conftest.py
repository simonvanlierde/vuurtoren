"""Shared plans for the CodSpeed benchmarks.

The plans are the golden fixtures (the example TOMLs seeded through the DB), built once
per session so seeding and SQLite I/O stay out of the measured code.
"""

from typing import TYPE_CHECKING

import pytest

from golden_plan import US_HOUSEHOLD, build_seeded_plan

if TYPE_CHECKING:
    from vuurtoren.engine import PlanInput


@pytest.fixture(scope="session")
def nl_plan(tmp_path_factory: pytest.TempPathFactory) -> PlanInput:
    """The Dutch example household, with the house purchase milestone."""
    return build_seeded_plan(tmp_path_factory.mktemp("bench-nl"))


@pytest.fixture(scope="session")
def us_plan(tmp_path_factory: pytest.TempPathFactory) -> PlanInput:
    """The example household with a US person, so the US overlay runs every year."""
    return build_seeded_plan(tmp_path_factory.mktemp("bench-us"), US_HOUSEHOLD, buy_house=False)
