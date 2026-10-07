# Changelog

## [Unreleased]

### Added
- Local library persistence (`crodl/library`): a SQLModel/SQLite `Episode`
  table, an async engine with `init_db()` and a `LibraryRepository` protocol
  plus a SQLite implementation (with tests over an in-memory database).
- An `on_downloaded` hook: the core reports finished files, the facade hands
  them to the configured library, and the CLI records downloads into
  `~/Z Rozhlasu/library.db`.

### Changed
- Removed the legacy `crodl/tools/scrap.py` module (module-level global
  `cro_session`, duplicate `get_audio_link_of_preferred_format`, unused
  wrappers); `Series` now builds its episode list via the shared
  `extract_episode_info()`.
- Added direct test coverage for `CroAPIClient` in `tests/test_api_client.py`.
- The core no longer prints: `AudioWork.info()` returns the audio variants as
  data and the CLI renders them. A work without any audio link now reports the
  reason and exits with status 1 instead of failing silently.
- Constructors no longer perform network calls: `AudioWork`, `Series` and
  `Show` expose an explicit, idempotent `load()` (awaited by the facade and by
  `download()`), and a series fetches its episode list once instead of on
  every property access.
- `Series` and `Show` now share a single episode collection (`Episodes`), so
  the episode mapping and the `"<part>-<title>"` download name live in one
  place and a series exposes the same `episodes` attribute as a show.
- The downloaders own the output file name: `AudioParts.extension` and
  `AudioParts.output_path` replaced the `_merge_chunks(format)` argument.

### Removed
- Dead modules `crodl/tools/timer.py` and `crodl/data/streamlinks.py`, plus the
  unused `AudioWork.links` property and a commented-out pandas block in
  `crodl/data/attributes.py`.
- Unused dependencies `icecream` and `yaspin`, together with their transitive
  orphans (`asttokens`, `executing`, `termcolor`) in `uv.lock`.

### Fixed
- `Series.already_exists()` always returned `False`: `downloaded_parts` looked
  for the `"3-"` prefix, but files are written as `"3 - Title.mp3"` (the
  filename sanitizer expands dashes). The episode number is now parsed from
  the file name, so a fully downloaded series is recognised.
- `AudioWork.already_exists()` no longer matches a different episode via
  substring (e.g. `"13 - Title.mp3"` satisfying a lookup for `"3 - Title"`).
- `--no-accents` now also applies to the downloaded file name, not just the
  folder: the flag is propagated from `AudioWork` into the MP3/HLS/DASH
  downloaders, so accent-free files are named and found consistently.

## [1.5.2] - 2026-10-06

### Fixed
- FFmpeg merge failing with "Too many open files" (exit code 232) for long
  episodes: the `concatf:` protocol keeps all segments open at once, so the
  open-file limit is now raised before merging. FFmpeg errors are also
  reported with the actual error message instead of a bare exit code.

## [1.5.1] - 2026-05-05

### Added
- `--title` / `-t`: Option to set a custom title for the downloaded file or folder.
- `--output` / `-o`: Option to specify a custom output directory.
- `--no-accents`: Flag to automatically remove diacritics from filenames.
- Comprehensive test suite for new v1.5.0 features.

### Changed
- Improved `sanitize_filename` to collapse multiple dashes and handle Windows-specific edge cases.
- Refactored core logic into a Facade pattern for better maintainability.
- Updated documentation with examples for new CLI options.
- Parallel downloading for Series and Shows to improve performance.

### Fixed
- Multiple dashes appearing in filenames after sanitization.
- `SyntaxWarning` in `utils.py` regarding invalid escape sequences.
- Absolute path issues when merging audio segments with FFmpeg.

---

## [1.1.x] - Previous Versions
- Initial support for MP3, HLS, and DASH streams.
- Basic downloading functionality for AudioWorks, Series, and Shows.
