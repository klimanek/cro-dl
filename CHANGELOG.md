# Changelog

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
