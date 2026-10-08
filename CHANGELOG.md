# Changelog

## [Unreleased]

### Added
- Local library persistence (`crodl/library`): a SQLModel/SQLite `Episode`
  table, an async engine with `init_db()` and a `LibraryRepository` protocol
  plus a SQLite implementation (with tests over an in-memory database).
- An `on_downloaded` hook: the core reports finished files, the facade hands
  them to the configured library, and the CLI records downloads into
  `~/Z Rozhlasu/library.db`.
- The web library shares that one persistence layer: `crodl/library/` gained
  the full domain (`Station`/`Show`/`Series` + episode foreign keys), a disk
  scan (`library/scan.py`), artwork fetching (`library/artwork.py`) and a
  `LibraryService` used by both the hook and the CLI's `--sync` flag.
- `crodl/server/` (FastAPI + Jinja2) serves the library from `crodl/library/`.
- A `Collection` value object (`crodl/program/content.py`): a downloaded part now
  carries the show/series it belongs to, so the library can link the episode and
  store one cover for a multi-part work instead of one image per part.
- The disk scan derives works from the download layout: each folder under
  `~/Z Rozhlasu` becomes a `Show`/`Series` (title = folder name, a series when
  it sits under `Seriály/`) and its files are linked to it, so `cro-dl --sync`
  adopts a library that predates the database (existing artwork next to the
  audio is picked up as well).
- The web library shows a grid of works - artwork, title, kind and part count -
  and a detail page with a work's parts, each playable, next to its cover and
  description. `LibraryService.overview()`/`detail()` own that aggregation and
  the Czech labels; the routes only render.
- `crodl/server/access_log.py`: a log filter that prints request paths as text
  instead of percent-escapes (`Seriály` instead of `Seri%C3%A1ly`).
- An end-to-end test (`tests/test_download_end_to_end.py`): a real
  `AudioWork.download()` for MP3, HLS and DASH with only the network and ffmpeg
  stubbed. It checks the file the library is handed (name, container, content),
  the order the segments were merged in and that the temporary segment folder is
  gone - the wiring a downloader without a declared container used to slip
  through.

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
- Optional clean-ups: `Attributes` and `Data` are frozen value objects, the
  three unused `type: ignore` comments are gone, and `pyright` plus `ty` now
  both pass on the whole package.
- The library `Episode` row now follows the content API vocabulary: it stores
  `short_title`, `part` and `duration`, with matching `AudioWork` properties.
  Section 7 of `WEB_LIBRARY_DESIGN.md` records which API the supplied docs
  describe (the broadcasting one) and what still needs modelling.
- The web library no longer mounts the download directory: media goes through
  `GET /library/{path}`, which serves only files the library stored. CORS allows
  just the local addresses the server runs on (`SERVER_HOST`/`SERVER_PORT` in
  `settings.py`, which `server/run.py` binds to as well), methods `GET` only.

### Removed
- `crodl/persistence/` and `crodl/tools/sync.py`, superseded by the single
  `crodl/library/` layer (the server, the disk scan and the curation script
  now use it too).
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
- Artwork downloads failed with an `InvalidURL` even though the image was on the
  server: the content API nests the image in an `asset` object, and
  `AudioWork.asset_url` returned `str()` of that dictionary. The URL is now
  taken from `asset["url"]`.
- The same image was downloaded once per episode. A work whose parts report one
  image now stores a single `cover.jpg` (fetched once, reused by every part and
  on re-runs); parts that bring their own image keep one each, and a single-part
  work keeps its image next to the audio file.
- The web library showed only "Místní soubory": episodes were stored without
  `show_id`/`series_id` and no `Show`/`Series` row was ever created, so every
  work counted as an orphan. Downloads now store and link their collection, and
  `--sync` derives collections for files that were already on disk.
- The server's access log printed percent-escaped paths
  (`/library/Seri%C3%A1ly/…`); the path is decoded for the terminal now.
- `crodl.log` is written as UTF-8 instead of the locale codec, which mangled
  Czech titles on Windows (cp1250).
- `library.db`, the log and the segment folders were one URL away: the old
  `StaticFiles(directory=DOWNLOAD_PATH)` mount published the whole download
  directory. They answer 404 now, and a path that tries to leave the directory
  (`..`, an absolute path) is refused.

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
