# Changelog

## 0.3.0 — 2026-09-19

Target platform: Ubuntu 26.04 LTS (Python 3.14, Qt 6.11, GCC 15).

### Removed: maintainer-built PDK distribution

Releases up to `v0.2.0` shipped a `tt-pdk-sky130a` tarball produced by archiving one
workstation's `~/pdk/sky130A`, and the Setup Assistant pointed every user at it. That
archive was not reproducible and carried whatever local modifications happened to be
present.

- the bundle route is disabled in the shipped manifest, and the assistant states why
- a new route installs the upstream prebuilt sky130A published by the FOSSi Foundation
  (`fossi-foundation/ciel-releases`), pinned to a specific `open_pdks` build and
  installed as the desktop user
- `scripts/build_sky130_pdk_bundle.sh` replaces the old bundler: it builds from a clean
  `open_pdks` checkout, refuses to package an in-use PDK root, and writes a provenance
  file recording the ref, the Magic version and the build date

### Tool versions

- `open_pdks` 1.0.321 → 1.0.608
- Magic 8.3.634 → 8.3.684, fetched from the official repository rather than an archived
  tarball
- Magic is configured with `-std=gnu17` on GCC ≥ 14, which otherwise fails to build under
  the C23 default in Ubuntu 26.04
- the manifest declares minimum versions, so Ubuntu's Magic 8.3.105 and Netgen 1.5.133 are
  reported as too old instead of passing as OK

### Fixed

- Magic 8.3.6xx answers `-version` with usage text and exit code 0. The probe stored that
  text as the detected version, which also meant the Magic/PDK compatibility check never
  fired. `--version` is now tried first and usage output is rejected.
- ngspice reported `******` as its version, the first line of its banner.
- The app refused to start on Wayland when the `xcb` helper libraries were absent, even
  though the wayland platform plugin never loads them.
- A process that failed to start leaked its `QProcess` and left the runner wedged.
- Four Qt tests never ran: other test modules installed a fake `PySide6` into
  `sys.modules` at import time, so the real ones were silently skipped.

### Performance

| | before | after |
|---|---|---|
| startup to visible window | 10.3 s | 1.4 s |
| preferences page construction | 3.90 s | 0.04 s |
| main window construction | 4.04 s | 0.20 s |
| spectrum, matched resolution | 315 ms | 2.9 ms |
| `.deb` download | 213 MB | 74 MB |

- the ten-second minimum splash, slept on the UI thread, is gone
- environment diagnosis is memoized with explicit invalidation; building the preferences
  page ran seven full scans
- the scan runs on a worker thread instead of blocking the window
- the Python environment probe asks the interpreter everything in one subprocess
  instead of five
- the spectrum used a quadratic DFT in Python, capped at 512 samples; an FFT keeps
  16384 samples and halves the dominant-frequency error
- phase estimation was two complex exponentials per sample with no cap on trace length
- raw files are read as one array rather than unpacked row by row
- `PySide6-Essentials` replaces full `PySide6`, dropping a 195 MB Qt WebEngine the app
  never imports

### Interface

- light, dark and follow-the-system themes; colors live in one token set per mode
- the per-tab stylesheets that hard-coded light colors are gone, so pages follow the
  selected theme instead of staying white
- the navigation column no longer forces a horizontal scrollbar at the default size
- window geometry is remembered between sessions
- `Ctrl+1`..`Ctrl+7` jump between sections
- the startup project dialog can be turned off

### Added

- job queue: a command issued while another runs is queued instead of dropped
- CSV export for the selected trace and its overlays, at full double precision, with no
  silent resampling of traces that do not share an X axis
- log views discard their oldest lines past 5000 blocks
- the packaged launcher prefers a user-owned Python environment at
  `~/.local/share/sky130-flow-gui/venv`, and creates one if nothing usable is found

### Tests

68 → 119, with no silent skips.

## 0.2.0

Setup assistant, EM sizing workflow, Debian packaging, bundled PDK download.
