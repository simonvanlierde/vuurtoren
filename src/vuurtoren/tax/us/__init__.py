"""United States (US) federal tax configuration.

Registered as a *citizenship* set, not a residence one: there is no `regime_for("US")`,
because the US enters this app through `CitizenshipOverlay` (`tax/overlay.py`) rather
than through `TaxRegime`. Importing this package registers the figures into the
country-neutral TAX_CONFIG (tax/config.py) as an import-time side effect, so
`resolve_tax_config("US", ...)` works for anyone who reaches into tax/us/*.
"""

from vuurtoren.tax.us import config as _config  # noqa: F401
