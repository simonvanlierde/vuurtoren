"""Austrian (AT) tax configuration."""

# Importing this package must register the Austrian figures into the country-neutral
# TAX_CONFIG (tax/config.py) before anyone calls defaults_for("AT", ...) or
# resolve_tax_config("AT", ...). config.py does the registration as an import-time
# side effect; this import guarantees it has run for every caller that reaches into
# tax/at/* (e.g. via regime_for("AT"), or directly in tests).
from vuurtoren.tax.at import config as _config  # noqa: F401
