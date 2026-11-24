# Roadmap

What is worth doing next, roughly in the order I would take it. Items under
“Fixes” are not new features: something that already shipped does not behave as
it should.

_As of 2026-11-25: 2.2.0 is released (PyPI and the `v2.2.0` tag), `main` and
`dev` are in sync, the suite has 432 passing tests, and there are no open
TODO/FIXME markers._

## Fixes

### 1. A partial download must not look finished

`crodl/streams/mp3.py` writes straight to the final file, and
`AudioParts._merge_chunks` lets ffmpeg write straight to it too. When a download
or merge is interrupted, a truncated file with the final name stays on disk.
`AudioWork.already_exists()` only checks the stem, so the next run skips it, and
`Series.downloaded_parts` counts it as downloaded. The library then holds a
“finished” part that cannot be played.

- Download and merge into a temporary file (`<name>.part`, or
  `merged.<ext>` inside the segment folder) and `os.replace` it on success.
- Remove the temporary file on failure.
- Validate the MP3 `Content-Length` (or at least that the file is non-empty).
- Cover it with a test: an interrupted download must not pass `already_exists`.

### 2. `cro-dl --sync` should cover every library folder

`sync_library()` calls `LibraryScan()` with the default `DOWNLOAD_PATH`, so
additional roots (an external disk added in Settings) are imported only once,
when the folder is added. Files that appear there later never reach the library.

- Scan every folder from `SqliteLibraryRepository.get_roots()` /
  `roots.known()` in `--sync`.
- Add “Prohledat znovu” to Settings, per folder and for all folders.
- Consider a “clean missing files” action: rows whose `local_path` no longer
  exists are shown as placeholders today and are never cleaned up.

### 3. The version check needs an opt-out

CLI and web both ask PyPI once a day. Offline it only costs the timeout, but
somebody may not want any outbound request.

- A setting such as `VERSION_CHECK_DAYS = 0` (or `CRODL_NO_UPDATE_CHECK=1`)
  respected by `version_check.watch()` and by `announce_update()`.
- Keep the cache behaviour: no request at all when disabled.

### Note (no action)

The annotated `v2.2.0` tag points to `ac078e0`, while `main` and `dev` are at
`1cd1d9d`. Both trees are identical and the release comes from the tag, so this
is history shape, not a problem.

## Improvements

### A. Continue listening (high)

`player.js` stores one global position (`{index, position}`); switching to
another part throws the previous position away. Store progress per part (by
`src`) and surface it:

- a “Pokračovat” button on the library grid and on a work's page;
- a small progress mark next to each part;
- “Play all” starting at the first unplayed part.

### B. Search and sorting (high)

The library only filters by genre and sorts by title. Add:

- a search over work title, description, author and part titles (`?q=`);
- sorting by title, recently added, recently checked or genre (`?sort=`).

### C. Auto-download new parts (high)

The new-part check finds available parts but always waits for a click. Add a
per-work “download new parts automatically” switch (a new column on `Show` and
`Series`, migrated through `ADDED_COLUMNS`) and call
`DownloadManager.start_missing` when a check finds something available.

### D. A player for spoken word (medium)

- playback speed (0.75–2×);
- a sleep timer;
- keyboard shortcuts (space, arrows);
- the Media Session API, so a phone's lock screen shows the title and controls.

### E. Queue management (medium)

The queue can only be appended to and emptied. Add remove, reorder and “play
next”.

### F. Download management (medium)

`DownloadJob` already holds its `asyncio.Task`. Add:

- a cancel and a retry button on the download pages;
- a format choice (mp3 / hls / dash) to the web download form, which currently
  always uses the default MP3.

### G. Cover art inside the files (medium)

`library/tags.py` writes ID3/MP4 tags but keeps the cover only as a separate
image. Embed it as `APIC` (MP3/AAC) and `covr` (M4A/MP4) too, so players outside
cro-dl show it offline.

### H. Grid performance (low)

- `loading="lazy"` on the card images;
- optionally thumbnails for the grid (would add Pillow) instead of full covers;
- cache headers for `/library/...` covers and audio.

### I. Access from a phone or tablet (larger, security decision)

The server binds `127.0.0.1` only. An opt-in `--host 0.0.0.0` plus a simple
access token would allow listening from another device on the LAN. This changes
the security model, so it should stay off by default and be decided explicitly.

### J. Smaller conveniences

- `cro-dl --check` to run the content check from the terminal;
- open the browser after `cro-dl server` (an opt-in flag);
- browser notifications for newly found parts;
- bulk actions: select several works and check, tag or delete them in one go.

## Suggested order

1. Fix 1 — partial files (small, prevents silent corruption).
2. Fix 2 — `--sync` across all roots and a rescan button (small/medium).
3. A + B — continue listening and search (largest user benefit).
4. C — automatic download of new parts.
5. D–G by preference.
6. I only after an explicit decision about LAN access.
