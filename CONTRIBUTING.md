# Contributing

## Setting up

```
uv sync
```

Run the tests the way CI does:

```
uv run python -m pytest tests/ -q
```

If the suite fails on the logger, check that the message is not the read-only
`$HOME` one: the log file is opened on the first record, so cro-dl says so on
stderr and carries on. The library itself lives in `~/Z Rozhlasu`; tests use
in-memory databases and temporary folders.

## The gate

Everything below has to pass before a commit goes in, and CI runs the same:

```
uv run ruff format --check crodl/ tests/
uv run ruff check crodl/ tests/
uv run ty check crodl/
uv run pyright crodl/
uv run python -m pytest tests/ -q
node --check crodl/server/static/player.js   # the player loads on every page
```

## What CI runs (`.github/workflows/ci.yml`)

- **tests** — Python 3.10, 3.11, 3.12, 3.13, 3.14 on Ubuntu, installing cro-dl
  the way a user does (`pip install ".[test]"`), so the resolver's choices are
  tested and not just the code.
- **platforms** — Python 3.13 on Windows and macOS. Two of the bugs this project
  has shipped were platform-only: a naive datetime column that only the newer
  SQLModel refused, and a wheel that went out without the pages. No Linux runner
  can see either of them.
- **lint** — the gate above, minus pytest (the JS check is included).

## The minimum Python

`pyproject.toml` declares `>=3.10` and the README says the same in both
languages. `tests/test_ci.py` fails when the CI matrix does not *start* at that
floor, or when the README drifts from it — so changing the floor means three
edits together: `requires-python`, the README (both languages) and the matrix.

3.10 is measured, not assumed: the suite passes on 3.10.22. If a version goes red
in CI, either fix it or raise the floor everywhere at once.

## Dependencies

There is no update bot: `uv lock --upgrade` (or `uv add`) is a deliberate act,
and the checks above are what says whether a bump is safe. A new SQLModel broke a
release once — it refused the naive datetime columns the older one accepted — so
let CI have the last word on a bump rather than whichever machine happens to have
it installed. Pin what a release depends on (`lxml<7.0.0`, `pytest<9`, …) and
change the pin on purpose.
