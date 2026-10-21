"""Per-residence-country treaty rules, and the registry the overlay looks them up in.

Adding US-in-Austria is one module beside `nl.py` and one entry below. A residence with no
entry is not an error: the overlay simply applies no relief, which is what the statute says
in the absence of a treaty.
"""

from vuurtoren.tax.us.residence.nl import NLTreatyRules
from vuurtoren.tax.us.residence.protocol import ResidenceTreatyRules, TreatyRelief

REGISTRY: dict[str, ResidenceTreatyRules] = {"NL": NLTreatyRules()}
"""Residence country code -> the treaty rules that reach a US person living there."""

__all__ = ["REGISTRY", "NLTreatyRules", "ResidenceTreatyRules", "TreatyRelief"]
