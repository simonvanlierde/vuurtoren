"""The citizenship-overlay seam. No country implements it yet — phase 3 does that."""

import numpy as np

from vuurtoren.tax.overlay import CitizenshipOverlay, PersonSlice, TreatmentMaps


def test_treatment_maps_default_to_empty() -> None:
    """An overlay reads the maps it cares about and must not trip over the absent ones."""
    maps = TreatmentMaps()

    assert maps.balances == {}
    assert maps.income == {}
    assert maps.fund_realized_gains == {}
    assert maps.value_growth == {}


def test_a_person_slice_keeps_owned_and_joint_apart() -> None:
    """The engine states ownership; the overlay decides the share of a joint account.

    Splitting a jointly held account is a US tax fact — it follows from filing status —
    and invariant #1 forbids `engine.py` knowing it. So the two arrive separately and the
    overlay combines them as `owned + share * joint` under its own rule.
    """
    owned = TreatmentMaps(balances={"nl.box3_investment": np.array([100.0])})
    joint = TreatmentMaps(balances={"nl.box3_investment": np.array([40.0])})

    slice_ = PersonSlice(person_id=1, owned=owned, joint=joint, earned_income=np.zeros(1))

    assert slice_.owned.balances["nl.box3_investment"] == np.array([100.0])
    assert slice_.joint.balances["nl.box3_investment"] == np.array([40.0])


def test_a_minimal_overlay_satisfies_the_protocol() -> None:
    """The protocol is narrow on purpose: no purchase_costs, no state_pension_date.

    Those are residence concepts. A protocol that forced an overlay to answer them would
    be lying about the asymmetry between taxing by residence and taxing by citizenship.
    """

    class _Stub:
        citizenship = "US"

        def annual_tax(self, s, cfg, *, residence_tax, carry):  # noqa: ANN001, ANN202
            return np.zeros_like(residence_tax), carry

        def withdrawal_tax(self, amount, *, treatment, realized_gain, cfg):  # noqa: ANN001, ANN202
            return np.zeros_like(amount)

        def valid_treatments(self):  # noqa: ANN202
            return frozenset({"us.non_pfic"})

        def validate_accounts(self, accounts, *, person):  # noqa: ANN001, ANN202
            return None

    assert isinstance(_Stub(), CitizenshipOverlay)
