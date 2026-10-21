"""Dutch (NL) tax configuration."""

# Importing this package must register the Dutch figures into the country-neutral
# TAX_CONFIG (tax/config.py) before anyone calls defaults_for("NL", ...) or
# resolve_tax_config("NL", ...). config.py does the registration as an import-time
# side effect; this import guarantees it has run for every caller that reaches into
# tax/nl/* (e.g. via regime_for("NL"), or directly in tests).
from vuurtoren.tax.nl import config as _config  # noqa: F401
