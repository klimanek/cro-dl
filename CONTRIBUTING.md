# Contributing and releasing

## Setting up

```
uv sync
```

Run the tests the way CI does:

```
uv run python -m pytest tests/ -q
```

If the suite fails on the logger, your `$HOME` is not writable for it: cro-dl
opens `~/Z Rozhlasu/logs/crodl.log` and keeps the database next to it. Point
`HOME` somewhere disposable (`HOME=/tmp/crodl-home`) or let it use the real one.

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
- **lint** — the gate above, minus pytest and the JS check.

## The minimum Python

`pyproject.toml` declares `>=3.10` and the README says the same in both
languages. `tests/test_ci.py` fails when the CI matrix does not *start* at that
floor, or when the README drifts from it — so changing the floor means three
edits together: `requires-python`, the README (both languages) and the matrix.

3.10 is measured, not assumed: the suite passes on 3.10.22. If a version goes red
in CI, either fix it or raise the floor everywhere at once.

## Dependencies

Dependabot opens a pull request every week for `pip` (which covers `uv.lock`) and
for the GitHub Actions. A new SQLModel broke a release once — it refused the
naive datetime columns the older one accepted — so let CI have the last word on a
bump rather than whichever machine happens to have it installed.

## Releasing

1. Bump `__version__` in `crodl/__init__.py`, e.g. to `2.1.0`.
2. Add a `## [2.1.0] - YYYY-MM-DD` section to `CHANGELOG.md`.
3. Commit and push to `main` (or merge a branch into it).
4. Tag it and push the tag — **a plain `git push` does not push tags**:

   ```
   git tag v2.1.0
   git push origin v2.1.0
   ```

5. GitHub does the rest (`.github/workflows/release.yml`):
   - **build** — the tag must equal `__version__` (`v2.1.0` → `2.1.0`: three
     parts, so not `v2.1`); then `uv build --wheel`, then a check that the wheel
     carries `crodl/server/static/player.js` and `crodl/server/templates/*.html`;
   - **publish** — uploads to PyPI through trusted publishing (OIDC, no token);
   - **notes** — creates a GitHub Release with generated notes.

A tag that does not match the version publishes **nothing**: the build job stops
on its first step. That is deliberate — 2.0.0 went out untagged and 2.0.2
shipped without its pages, and both would be caught here.

### One-time setup on PyPI

Before the first release, register the trusted publisher at
`https://pypi.org/manage/project/cro-dl/settings/publishing/`:

| field | value |
|---|---|
| Owner | `klimanek` |
| Repository | `cro-dl` |
| Workflow | `release.yml` |
| Environment | `pypi` |

Nothing secret is stored in the repository or in GitHub secrets.

### What a release does not do

- It does not read `CHANGELOG.md`; the GitHub Release notes are generated from
  the commits.
- It does not check whether the version is already on PyPI; a duplicate fails at
  the upload step (nothing breaks, the job just goes red).
