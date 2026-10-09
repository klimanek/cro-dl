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
- The library can hold more than one folder: "⚙️ Nastavení" (in the top bar) lists
  the folders it keeps, and "Importovat" takes the path of another one (a
  collection on an external disk). The files stay where they are, the works show
  up next to the rest, and they are served and played like anything else. A
  folder that is not there right now (an unplugged disk) is named in a banner on
  every page, and the setting stays for when it comes back - the library is not
  written to or crashed on in the meantime. A file that is not there gets no
  address at all, so a missing cover or part shows a placeholder instead of a
  broken player.
- A work's description is only shown when it has one (it used to print "None").
- Editing metadata by hand: a work's title and description, and each part's  title, author and description, are editable on the detail page (a work adopted
  from disk is named after its folder until then). Curation writes in place and
  only the columns a person may touch.
- Downloading from the web library: a field on the home page takes a
  mujrozhlas.cz link, the download runs in the background (up to 20 jobs kept),
  `/downloads` lists them with progress and `/downloads/{id}` refreshes itself
  while one runs. The same is available as JSON through `POST /api/downloads`,
  `GET /api/downloads` and `GET /api/downloads/{id}`.
- Actions on a work in the grid, behind a ⋯ button that appears on hover:
  "Aktualizovat data" asks the content API for what the library is missing
  (metadata, and the artwork whose download failed earlier) and "Smazat
  z knihovny" removes the records - it asks first and leaves the files on disk,
  so `--sync` can adopt them again.
- "Režim úprav": the edit forms are hidden until the switch in the top bar turns
  them on; a cookie remembers the choice across pages.
- Watching for new parts: the server asks the content API what each work has now
  (a moment after start, then every `UPDATE_CHECK_HOURS`, and on demand from the
  library page via "Zkontrolovat nové díly"). Works with something new carry a
  badge ("3 nové díly") and a button that downloads exactly those parts - by
  their uuid, so no page URL is needed - with progress in the downloads list.
- "Zkontrolovat nové díly" lives in the top bar and shows what it is doing: a
  spinner while it runs, then a tick or a cross. The check runs in the background
  (the page refreshes itself), so no request waits for the API.
- In edit mode a work can be given the mujrozhlas.cz page it came from. The link
  is stored (its own small table, so the work keeps its key), and "Aktualizovat
  data" reads the uuid off that page and fetches what the API has - which is what
  makes a folder adopted from disk refreshable.
- Downloads are tagged as they are stored: `mutagen` writes the title, the
  author, the work as the album, the part as the track number and the genre the
  API lists for the work ("Horor", "Komedie") into MP3 (ID3) and M4A/AAC (MP4)
  files, so a player shows the reading as a reading and not as a loose file.
- Edit mode gained a tag editor: "Zapsat tagy do dílů" writes what the library
  knows into every part's file (for downloads from before there were tags), and
  each part has its own form showing what its file says - an empty field leaves
  that tag alone. Raw AAC (ADTS, the Czech Radio HLS format) takes an ID3 chunk,
  which is what players read there; only a file that cannot be tagged is skipped.
- The library plays: every part carries a small play button and a player sits at
  the foot of every page (play/pause, previous/next, a seek bar, the queue). The
  queue lives in the browser, so browsing the library - or reloading it - leaves
  the part you were in where you left it, and one click carries on. A work's menu
  has "Přidat do fronty" (its parts in playing order, no duplicates). Playback
  itself pauses when a page changes: a new document means a new `<audio>`, and a
  browser only starts audio after a click - hence the bar staying and the place
  being kept. Without JavaScript the per-part player is still there (`<noscript>`).
- A work's genre is a field of its own ("Upravit název, žánr a popis" in edit
  mode): saving it rewrites the genre tag of every part, and a download or a
  refresh fills it from the API's genres when nobody has set one.
- The top bar lists the library's genres; one genre filters the grid, and when
  there are more than a few the rest fold into a dropdown.

### Changed
- Two layout inconsistencies in the same area: on a work's page "Aktualizovat
  data" and "Zapsat tagy do dílů" were different heights (the emoji in the second
  label made its line box taller), and the bars did not match between pages (the
  library's items were inline text with " · " between them, a work's were a
  spread-out flex, and the mode links were 0.9em inside an already 0.9em bar).
  Buttons share one line height and padding now, both bars use the same 16px gaps
  and the same 0.9em text (measured in the browser: every item 14.4px, both
  buttons 31.6px), and the library header's title, bar, genres and warning are
  rows of their own instead of flex items on one line. The button also says "do
  dílů" like the rest of the UI, not "do částí".
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
- The pages share one stylesheet (`server/templates/_style.html`) instead of
  each carrying its own copy.
- Timestamps in the UI are written as Czech writes them ("Přidáno 8. října, 2026
  v 15:36") rather than as ISO strings.

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
- A part the library lacks was always announced as news. Works are time-limited,
  so the API still lists parts whose streams expired long ago: those now show an
  orange "2 díly nedostupné" (nothing to fetch), parts the radio has not aired
  yet a neutral "Ještě 2 díly", and only a part that can really be fetched is
  green ("Nové 2 díly"). `till` turned out to be the broadcast end, not the
  stream window - the missing audio links are what tells the two apart.
- "Aktualizovat data" answered "Tenhle záznam nemá v API protějšek" for a work
  whose page is a JavaScript shell. The uuid *was* found on the page; the refresh
  then asked the API about the row's kind (a `Show`) while the record was an
  episode, and the API answered `entity_not_found`. The API is now asked until
  one of its kinds answers (series, show, episode), which is also what a folder
  adopted from disk looks like.
- The "Zkontrolováno" link in the top bar rendered at a smaller size (0.85em)
  than "Stahování" and "Režim úprav" beside it; all of them are 14.4px now.
- An episode that the API knows as part of a show (a play aired in "Hra na
  neděli") was stored with no work of its own and turned up in "Místní soubory",
  where nothing could be refreshed for it. It is now a work of its own: keyed by
  the part's uuid, named the way it was downloaded (not after the show it aired
  in), with the genre and artwork from its own record - and the page it came from
  is stored with it, on the part and as the work's link, so the work's page shows
  it and "Aktualizovat data" has something to read the uuid from. "↻ Aktualizovat
  data" on the "Místní soubory" page gives the loose files that same work, which
  is also the way to repair a library that stored them earlier: a download that is
  already on disk is skipped, so re-downloading such a file does nothing.
- Checking for new parts failed on any library whose database was created while
  `updatecheck` kept one NOT NULL count without a default: every write was refused
  ("NOT NULL constraint failed: updatecheck.missing"), so the check could never
  record what it found. The table is rebuilt on startup without the column it no
  longer uses (its rows are a cache that the next check recomputes), and a work
  the database refuses is skipped with a log line instead of failing the whole
  check.

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
