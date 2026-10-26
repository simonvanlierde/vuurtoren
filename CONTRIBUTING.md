# Contributing to Vuurtoren

How to work on the code: the gates every commit passes, the architectural invariants, and
the conventions that are easy to get wrong.

## The gates

Both must exit 0 before every commit. CI (`.github/workflows/ci.yml`) runs the same
commands in one job. The Playwright suites run after them on main, on a manual run, and on a
pull request labelled `e2e`; other pull requests run `tsc -b` in their place.

```bash
# Python
uv sync
uv run ruff format --check . && uv run ruff check . && uv run ty check && uv run pytest

# Frontend
pnpm -C frontend install
pnpm -C frontend run check && pnpm -C frontend test && pnpm -C frontend build
```

`uv run ruff format .` and `pnpm -C frontend fix` write the fixes; the gate uses
`ruff format --check` so it reports unformatted code instead of rewriting your tree.

The frontend's API types are generated, and `lib/api.ts` names them; only the routes that
return an untyped dict keep hand-written types. After changing a request or response model
in `api/schemas.py` or `domain.py`, run `pnpm -C frontend run gen:api` and commit the two
files it writes (`frontend/src/lib/openapi.json` and `api.gen.ts`); a test in each gate
fails while either is stale.

`ty` is [Astral's type checker](https://github.com/astral-sh/ty). Its suppression comment
is `# ty: ignore[rule]`, not mypy's `# type: ignore[rule]`, which `ty` ignores. Ruff runs
`select = ["ALL"]`: five rules are ignored globally in `pyproject.toml`, and every other
exception is an inline `# noqa: RULE  # reason`. Fix a finding rather than suppress it,
and if you do suppress one, say why on the same line.

Install the git hooks to run the gates on the files you touch:

```bash
uv tool install prek   # a drop-in pre-commit replacement, once per machine
prek install
```

Mutation testing is not a gate. `just mutation` runs mutmut over the Dutch tax code and
`solve.py` (about 8 minutes with six workers) and lists functions with more surviving mutants
than `tests/mutation-baseline.txt` records. A new survivor is a change the tests cannot
see: add the test that kills it, or, if the mutant changes nothing a caller can observe,
run `just mutation-baseline` to accept it.

## Layout

```text
src/vuurtoren/
  domain.py       frozen value objects — the projection engine's only input
  tables.py       SQLAlchemy 2.0 storage, mapped to domain objects
  seed.py         loads a household from TOML
  mortgage.py     annuity maths (country-neutral)
  engine.py       month-by-month projection, FIRE metrics
  scenarios.py    applies scenario overrides before a projection
  solve.py        solves for the input that hits a goal
  api/            the FastAPI app, one module per route group
  reporting/      read-only reports (US FBAR filing check)
  tax/
    regime.py     the TaxRegime protocol — the residence-country seam
    overlay.py    the citizenship seam, for a US person living elsewhere
    household.py  one residence regime plus any citizenship overlays
    config.py     tax-parameter schema and per-scenario resolution
    parameters.py loads each country's parameters.yaml
    nl/           Dutch rules and figures, behind the protocol
    at/           Austrian rules and figures, behind the protocol
    us/           US federal rules, applied as a citizenship overlay
```

## Architectural invariants

These keep the engine correct and portable. Breaking one is a correctness or portability
bug, not a matter of style, and tests in `tests/test_golden.py` enforce several of them.
Code comments cite them by number.

1. **The engine knows no country.** `engine.py` imports nothing from `tax/nl/`, and all tax
   goes through the `TaxRegime` protocol. An AST test walks every module outside `tax/nl/`
   (relative imports included) and fails the build otherwise; the regime registry in
   `tax/regime.py` is its one allowed exception. `tax/config.py` (schema and resolution)
   and `mortgage.py` (annuity maths) are country-neutral and fine to import; `tax/nl/`
   holds only Dutch figures and rules.
2. **Three classifications on an `Account`, one reader each.** `kind` is the account's
   economic nature, the same in every country (`CASH|EQUITY|BOND|REAL_ESTATE|PENSION|DEBT`),
   and is for the engine. `tax_treatment` is scoped to the country of residence
   (`"nl.box3_investment"`, `"at.investment"`) and is for the regime. `overlay_treatment`
   is scoped to a citizenship (`"us.non_pfic"`) and is for a `CitizenshipOverlay`. The
   engine never branches on a treatment string to decide what it means, the regime never
   branches on `kind`, and the two treatment namespaces never read each other: a US
   overlay reading an `nl.*` key is the coupling the split exists to prevent.
3. **No tax rate is ever written inline.** Every figure comes from a tax-config field that
   carries its `Provenance`: a `status`, a source URL, and the date it was verified. A
   field without provenance fails a test. Rates the government has not fixed yet are
   `provisional`, and the 2028 regime's are `proposed`. Any figure can be overridden per
   scenario, so "what if Box 3 goes to 40%?" is a scenario, not a code change.
4. **Money never round-trips through a float.** Use `Money` (integer eurocents, 2dp) for
   balances and amounts, and `ExactDecimal` (stored as text) for FX rates, unit prices and
   fractional unit counts. Never use `Numeric` or `Float`: SQLite turns those into a C
   double. Do not swap `ExactDecimal` for `Money` either: `Money` rounds to 2dp and would
   destroy an FX rate like `0.923456`. Use `Decimal` at every boundary; `float64` numpy
   lives inside the engine only.
5. **`domain.py` imports nothing from SQLAlchemy, `db.py`, or the rest of the project.** It
   is the engine's only input, and portability depends on it staying pure.
6. **The engine is `(n_runs,)` numpy arrays throughout**, and the deterministic projection
   is `n_runs=1`. There is no scalar code path. Monte Carlo is the same code with a
   different returns provider.
7. **`YearState.investment_gain` is `np.ndarray | None`, and the difference matters.**
   `None` means no actual return is available, so the forfaitair rule applies. A value is
   a *proven* actual return, so the tegenbewijs may be elected. Passing a zero array where
   you mean "unknown" elects a proven-zero return and zeroes the wealth tax.
8. **No personal data in tracked files.** Seeding reads a gitignored `data/household.toml`.
   The committed `household.example.toml` is fictional, and the tests and the golden
   baselines run against it.

## Two kinds of rate — do not unify them

- *Nominal* rates (the portfolio `return_assumption`, deliberately, and the mortgage rate)
  convert to monthly as `annual / 12`, so twelve months compound past the headline figure
  (6% becomes 6.17%). That is what "nominal" means, and a lender's annuity schedule does
  exactly this, so `mortgage.py` and `fixed_returns` agree because both inputs are nominal.
- *Price-level* rates (`inflation`, `house_appreciation`) convert as
  `(1 + annual) ** (1/12) - 1`, so a 2% assumption delivers exactly 2% over a year. These
  are year-on-year changes of the kind CBS and the ECB publish; converting them with `/12`
  would quietly inflate them.

Rent-vs-buy compares house appreciation against portfolio return, so if you change one
conversion, state which kind of rate you claim the input is.

## Schema changes

Any edit to `tables.py` needs an Alembic migration in the same commit. Autogenerate it,
read what it produced, and commit both together:

```bash
uv run alembic revision --autogenerate -m "what changed"
```

The app runs `upgrade_to_head` when it opens the database, so nobody has to remember an
upgrade step. The tests build their schemas with `create_all`, because replaying
migrations per test is slow. `tests/test_migrations.py` stops the two drifting apart: it
fails on a mapping the migrations do not account for, which otherwise shows up as
`no such column` in a running server.

A database from before Alembic needs `uv run alembic stamp head` once.

## The golden baselines

There are two, and they prove opposite things. `tests/golden/baseline.json` locks a
projection of `household.example.toml`, which has **no** US person.
`tests/golden/us_baseline.json` locks one of `household.us.example.toml`, which does. A
diff in either means the engine's numbers moved, but only the second can ever see a change
to `tax/us/`, which is why it exists.

Regenerate them with `uv run python scripts/regenerate_golden.py [example|us]`, only when a
numeric change is intended, in a deliberate commit of its own that is reviewed separately.
Never use it to make a failing test pass. If a tax test disagrees with the implementation,
the implementation is wrong: figures are checked against Belastingdienst and Rijksoverheid
and dated, not adjusted to fit.

## Adding a country

A new country is a new `tax/<cc>/` package plus one registry entry, and nothing in the
engine changes. Read the Dutch package (`tax/nl/`) first: it is the worked example.

1. **Parameters.** Put every figure in `tax/<cc>/parameters.yaml`, in the
   [PolicyEngine](https://policyengine.org/) parameter shape, each with its `status`,
   source URL, and verification date (invariant 3). These load into a `TaxConfig`.
2. **Rules.** Implement the `TaxRegime` protocol (`tax/regime.py`), keeping the arithmetic
   in `(n_runs,)` numpy (invariant 6).
3. **Register it.** Add one entry to `regime_for` that pairs the country code with its
   regime and config.
4. **Test it.** Add a golden case so the country's numbers are locked like the Dutch ones.

## Copy

Localised UI strings cover the chrome only: nav labels, buttons, headings. Domain tax terms
stay in their own language in every locale, because they are names ("Box 3", "lijfrente").
A new country brings its own untranslated terms the same way.
