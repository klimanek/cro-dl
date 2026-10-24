# Changelog

## [2.0.3] - 2026-10-22

### Fixed
- cro-dl would not start on Python 3.12: 2.0.2 declared the library's naive
  timestamps as `NaiveDatetime`, and the older SQLModel that a 3.12 install
  resolves cannot map that to a column ("has no matching SQLAlchemy type"). The
  columns name their storage with `sa_type` now, which every version understands,
  so cro-dl still runs on the Pythons it always promised - not only on 3.13.
- The web's progress bar barely moved: it counted whole parts, so a single-work
  download had one step and showed no bar at all, and a part was one jump. It
  reads the segment counters the CLI's bar draws - 370 of them for one half-hour
  reading - and the page polls them twice a second instead of reloading itself.

## [2.0.2] - 2026-10-16

### Fixed
- The server refused to start on Windows after a fresh install: SQLModel 0.0.4x
  rejects a naive `datetime` for a plain `datetime` column, and the library's own
  stamps (when a folder was added, a check ran, a file was downloaded) are naive.
  They are declared as `NaiveDatetime` now, so the stored values are exactly what
  they were and an existing database needs no change. The repo's lock no longer
  pins the old SQLModel, which is what hid this until it met a pip install.

## [2.0.1] - 2026-10-13

### Fixed
- An installed cro-dl could not start the server at all: the wheel carried the
  Python code but neither the pages nor the player script, so uvicorn died in
  `StaticFiles` with "Directory ... does not exist". Both directories are
  declared as package data now, and a test holds them there.

## [2.0.0] - 2026-10-13

A web library over your downloads: cro-dl now serves what you have, and plays it.

### Added
- **A web library** (`cro-dl server`, http://127.0.0.1:8000): the library as a grid
  of works, and a page per work with its cover, description and parts. Every part
  carries a play button, and a player sits at the foot of every page
  (play/pause, previous/next, seek).
- **A queue**: play a work's parts together ("Přidat do fronty" on a work's page or
  in its menu in the grid), see it on `/fronta`, play one entry next, or empty it
  in one go. It lives in the browser, so moving around the library - or reloading
  it - does not lose it, and what is playing keeps playing while you browse.
- **Downloading from the page**: paste a mujrozhlas.cz link and watch it in
  `/downloads`; the same is available as JSON (`/api/downloads`).
- **More than one library folder**: "⚙️ Nastavení" lists them and imports another
  one (a collection on an external disk) by browsing to it. A folder that is not
  there right now (an unplugged disk) is named in a banner, and the setting stays
  for when it comes back.
- **Watching for new parts**: cro-dl asks the content API on its own, and on
  "Zkontrolovat nové díly". A work with something new is marked green ("Nové
  2 díly"); parts whose streams are gone show orange ("2 díly nedostupné") and
  parts the radio has not aired yet a neutral "Ještě 2 díly". The button downloads
  exactly the parts that can still be fetched.
- **Tags in the files**: title, author, the work as the album, the part as the
  track number and the genre the API lists (MP3/ID3 and M4A/AAC/MP4), written as a
  download is stored and again on demand ("Zapsat tagy do dílů").
- **Editing by hand**: a work's title, genre and description; each part's title,
  author and description; and the mujrozhlas.cz page a work came from - which is
  what makes a folder adopted from disk refreshable. The grid's menu can refresh,
  delete a work from the library (the files stay on disk) or fetch its new parts.
- **Genres**: a work's genre is a field of its own, the top bar lists the
  library's genres, and one of them filters the grid.
- **`--sync` adopts a library that was downloaded before cro-dl kept records**:
  each folder becomes a work, its files are linked to it, and an image lying next
  to the audio becomes the cover.

### Changed
- `cro-dl server` starts the web library; the rest of the CLI is unchanged
  (`cro-dl <url>`, `--sync`, `--title`, `--output`, `--no-accents`).
- A work's page is laid out around its cover: the description flows beside it, the
  parts sit in a column of their own, and on a narrow window everything stacks
  again.
- Timestamps read as Czech writes them ("Přidáno 8. října, 2026 v 15:36").
- The library is served one known file at a time (`/library/...`) rather than
  publishing the download directory, and only to the local machine.

### Security
- A request that writes must come from this server's own pages, every request must
  have been addressed to the loopback interface (so a page cannot reach the server
  through the browser by pointing its own name at 127.0.0.1), a redirect target
  stays on this server, and a download URL must be `http(s)` on mujrozhlas.cz.

### Fixed
- Artwork: the image is read from the API's `asset` object (downloads failed with
  an `InvalidURL` before), and a work whose parts report one image stores a single
  `cover.jpg` instead of one per part.
- Downloads and `--sync` link each part to its show or series, so the library no
  longer shows everything as "Místní soubory"; an episode that aired in a show on
  its own is a work of its own, named the way it was downloaded.
- A part number appeared three times in the queue ("1. 1. 1-Jack Black…"); the
  number has its own column now and is shown once.
- Parts whose streams expired are no longer announced as new, and checking for new
  parts no longer fails on a library whose database an earlier build made.
- The player: pausing resumes where it stopped, pause and play in the bar work, and
  playback no longer stops when you move to another page of the library.
- A series is recognised as fully downloaded, `--no-accents` applies to the file
  name as well as the folder, and "Aktualizovat data" works for a work whose API
  record is an episode rather than a series or a show - taking the cover from the
  folder when the API has none.
- The server logs request paths readably (`Seriály`, not `Seri%C3%A1ly`) and writes
  `crodl.log` as UTF-8.

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
