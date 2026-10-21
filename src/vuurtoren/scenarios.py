"""Caller-side scenario application.

A `Scenario` is a sparse typed diff against the baseline. Only its `tax` group is read
by `engine.project`, as `tax_overrides`; every other group is applied *here*, when
building the `PlanInput` the engine runs. `apply_scenario` does that and hands back the
applied plan plus the `tax` group, so the engine's interface cannot be handed a group it
would ignore.

Nothing is mutated in place: the baseline plan, its rows and the shared defaults are
untouched, so two scenarios projected back-to-back cannot leak into each other.
"""

import dataclasses
from decimal import Decimal

from pydantic import BaseModel

from vuurtoren.domain import Account, CashFlow, Milestone, Scenario, TaxOverrides
from vuurtoren.engine import Assumptions, PlanInput, check_treatments
from vuurtoren.tax.regime import regime_for

# Override groups the engine cannot model yet, refused rather than silently ignored.
# `milestones` is per-milestone patch/remove; `added_milestones` is applied.
_DEFERRED_GROUPS = ("milestones",)


def _patch_model[M: BaseModel](model: M, patch: dict[str, object]) -> M:
    """A validated copy of a frozen model with `patch` applied over its fields.

    Revalidates from a dump so a bad value (or the wrong type) fails here, at the API
    boundary, rather than 30 years into a projection. Unknown fields are rejected rather
    than silently dropped — a typo must not become a no-op.
    """
    cls = type(model)
    unknown = set(patch) - set(cls.model_fields)
    if unknown:
        msg = f"unknown {cls.__name__} override field(s): {sorted(unknown)}"
        raise ValueError(msg)
    return cls.model_validate(model.model_dump() | patch)


def _check_ids(known: set[int], patches: dict[int, dict[str, object]], group: str) -> None:
    """Fail on an override aimed at a row that is not in the plan.

    Shared by `accounts` and `cash_flows` so the two cannot drift into disagreeing about
    what an unknown id does. The patching itself stays per-group: `_patch_model` is
    generic over the model, but `Account` and `CashFlow` have no common id-bearing base
    to write one loop against, and inventing one to restructure six entities would cost
    far more than four lines of repetition.
    """
    unknown = set(patches) - known
    if unknown:
        msg = f"{group} override references unknown id(s): {sorted(unknown)}"
        raise ValueError(msg)


def _apply_accounts(
    accounts: list[Account], patches: dict[int, dict[str, object]], tax_country: str
) -> list[Account]:
    _check_ids({a.id for a in accounts}, patches, "accounts")
    patched = [_patch_model(a, patches[a.id]) if a.id in patches else a for a in accounts]
    _check_treatments(patched, tax_country)
    return patched


def _check_treatments(accounts: list[Account], tax_country: str) -> None:
    """Reject any account whose tax_treatment the scenario's regime does not know.

    The same rule the account CRUD applies: a typo'd treatment taxes nothing at all, a
    silent zero rather than an error. Every account, not only the patched ones, because a
    scenario that changes `tax_country` leaves the untouched accounts on the old
    country's keys. An unregistered country is refused: no projection could run on it.
    """
    try:
        valid = regime_for(tax_country).valid_treatments()
    except KeyError:
        msg = f"no tax regime for {tax_country!r}"
        raise ValueError(msg) from None
    check_treatments(accounts, valid, tax_country)


def _apply_cash_flows(
    flows: list[CashFlow], patches: dict[int, dict[str, object]]
) -> list[CashFlow]:
    _check_ids({f.id for f in flows}, patches, "cash_flows")
    return [_patch_model(f, patches[f.id]) if f.id in patches else f for f in flows]


_RENAMED = {"aow_growth_months_per_decade": "state_pension_growth_months_per_decade"}
"""Assumption fields that changed name. Scenarios are stored JSON, so a rename that
dropped the old key would silently reject every scenario saved before it."""


def _apply_assumptions(assumptions: Assumptions, patch: dict[str, object]) -> Assumptions:
    patch = {_RENAMED.get(k, k): v for k, v in patch.items()}
    fields = {f.name for f in dataclasses.fields(assumptions)}
    unknown = set(patch) - fields
    if unknown:
        msg = f"unknown assumptions override field(s): {sorted(unknown)}"
        raise ValueError(msg)
    # Assumptions is a plain dataclass of float/int/bool/str/Decimal; the override group
    # arrives untyped from JSON. Coerce each value to the field's existing type so
    # the engine's float arithmetic never meets a Decimal.
    #
    # Via `str` for a Decimal target: `Decimal(0.86)` reads the float's binary expansion
    # and yields 0.8599999999999999866773237045... — the exact loss of precision
    # invariant #4 exists to prevent, on a field (`usd_to_eur`) that translates every US
    # figure in the projection.
    coerced = {k: _coerce(getattr(assumptions, k), v) for k, v in patch.items()}
    return dataclasses.replace(assumptions, **coerced)


def _coerce(current: object, value: object) -> object:
    """Cast an override to the type the assumption already holds. See `_apply_assumptions`."""
    target = type(current)
    return target(str(value)) if target is Decimal else target(value)


def apply_scenario(plan: PlanInput, scenario: Scenario) -> tuple[PlanInput, TaxOverrides]:
    """Apply a scenario's v1 override groups to `plan`.

    Returns `(applied_plan, tax_overrides)`. Hand both straight to `engine.project`
    (`tax_overrides=`): the engine reads the `tax` group itself.

    Raises `ValueError` (a 4xx at the API boundary) for a deferred group, an unknown
    override id, or an unknown/ill-typed field — never a silent no-op.
    """
    o = scenario.overrides
    deferred = [name for name in _DEFERRED_GROUPS if getattr(o, name)]
    if deferred:
        msg = (
            f"scenario override group(s) {deferred} are not supported yet: "
            "per-milestone patching is deferred"
        )
        raise ValueError(msg)

    household = _patch_model(plan.household, o.household) if o.household else plan.household
    applied = PlanInput(
        household=household,
        people=plan.people,
        accounts=_apply_accounts(plan.accounts, o.accounts, household.tax_country),
        cash_flows=_apply_cash_flows(plan.cash_flows, o.cash_flows),
        milestones=plan.milestones + [Milestone.model_validate(m) for m in o.added_milestones],
        start=plan.start,
        assumptions=(
            _apply_assumptions(plan.assumptions, o.assumptions)
            if o.assumptions
            else plan.assumptions
        ),
    )
    return applied, o.tax
