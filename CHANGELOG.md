# Changelog

## 0.3.1 — 2026-09-20

### Added

- **Optional digital flow through a container.** The Setup Assistant can now
  install a container runtime and download LibreLane — the maintained successor
  to OpenLane 2 — whose image carries OpenROAD, Yosys, Magic, KLayout and
  netgen. Nothing extra lands on the host. Docker comes from Ubuntu's own
  `docker.io` package rather than a third-party repository, so it keeps getting
  security updates through apt. The assistant distinguishes a missing runtime, a
  stopped daemon, and the case where the `docker` group was granted but the
  current session predates it — which is the one that confuses everybody.
- **Runs are recorded and survive a restart.** What used to be called history
  was a glob of `*.raw` files: it showed that output existed, but not which
  netlist produced it, how long it took, or whether it actually succeeded, and
  nothing at all about extraction, LVS or antenna runs. A JSON log beside the
  project's outputs now records each run's status, exit code, duration, inputs,
  command and artifacts. It is written atomically, survives a corrupt file, and
  is capped at 200 entries.
- **Each run keeps its own outputs.** Every simulation wrote the same
  `raw.raw` and `log.txt`, so each run overwrote the last and "load previous"
  could only ever reopen the newest result. Runs are now addressable by id.

### Fixed

- **A packaged install reported its own Python environment as broken.** The
  validator only accepted a user virtualenv under the XDG data directory, so on
  a `.deb` install — which ships its own interpreter — the environment check
  failed and the overall status went to `error` while the app was visibly
  running from a perfectly good environment. The running interpreter is now
  accepted when it satisfies the requirements, and the row is labelled
  `Entorno Python` rather than `Entorno Python XDG`.
- **The KLayout antenna deck could never be detected for sky130A.** Detection
  looked for one hardcoded filename, `sky130A_ant.rb`. sky130A ships no KLayout
  antenna deck at all: its DRC deck contains zero antenna rules, and the rules
  live in the Magic techfile instead. Deck discovery now accepts any
  antenna-named deck a PDK provides, and the Antenna page gained a Magic
  `antennacheck` engine, which it selects automatically when no deck exists and
  explains either way.

- **The official PDK install never ran.** The installer called
  `pip install --user ciel`, which Ubuntu 26.04 refuses outright because its
  system Python is marked externally managed (PEP 668). The manager now gets
  its own virtualenv under `~/.local/share/sky130-flow-gui/tools/ciel`. This
  path was verified by running it, not just by reading it.
- **The update check could never succeed on a packaged install.** It ran
  `git fetch` against the application directory, and a `.deb` install is not a
  git checkout, so it always answered "not a git repository". Packaged installs
  now query the GitHub releases API and compare against the shipped VERSION;
  source checkouts keep the git path.
- **The waveform viewer still forced a horizontal scrollbar.** Thirteen
  controls in a non-wrapping row demanded 1174 px, more than a 1536 px desktop
  has after the navigation column — and 0.3.0 made it worse by adding an
  "Export CSV" button to that row. The three export buttons are now one
  `Exportar` menu and the row wraps, taking the viewer's minimum width from
  1174 px to 215 px. Verified at 1534×890 with traces loaded, not empty.

### Interface

- **The empty antenna-deck field explains itself.** sky130A ships no KLayout
  antenna deck, so that Preferences field is legitimately blank — but a blank
  field with only a label still reads as something missing. It now carries a
  placeholder saying the PDK has no deck and that the Antenna page uses Magic.
- **Tables no longer cut off their own headers or rows.** Columns kept their
  default width, so headers were sliced mid-word (`Mover al lado driver` became
  `er al lado dr`), and a fixed pixel height left the first row halved. Columns
  are now sized to their contents including the header, one column absorbs the
  slack, and the height is measured after layout so it is a whole number of
  rows. Applied to all five tables in the app.
- **A warmer dark theme.** The dark palette was blue-tinted, which fought the
  accent colours the pages use for status. It is now warm neutral grey with a
  terracotta accent.
- **Collapsible sections open smoothly.** Expanding called `setVisible(True)`
  on content that had never been laid out, so Qt painted one frame at the
  widget's default geometry before the parent layout moved it. That frame is
  the flicker. The content now stays in the layout and its height animates
  from zero.
- **xschem opens at a usable size.** The SKY130 `xschemrc` pins
  `initial_geometry` to 1280x695, and xschem runs unscaled under XWayland, so
  on a HiDPI screen it came up at roughly a quarter of the area it should. The
  launcher now overrides that with a geometry derived from the physical screen
  size, applied through `--tcl` so it lands after `xschemrc` is sourced.
- **Collapsible navigation.** A toggle above the menu, or `Ctrl+B`, shrinks it
  from 208 px to 68 px icon-only. The state is remembered. Collapsed items are
  sized so the selection rounded rectangle is wider than it is tall, rather
  than looking squashed.
- **Drawn icons.** The navigation used bare Unicode glyphs whose coverage
  varies by font, so some rendered as a dash or a box. They are painted now and
  follow the theme colour.
- **Disabled buttons say why.** On a machine that already has a PDK, three of
  the six actions in that step are disabled with no explanation, which reads as
  the assistant being broken rather than as nothing needing to be done. Each
  now carries the actual reason.
- **One accented action per page.** `Correr` on Simulation, LVS, Extraction and
  Antenna, and the recommended PDK route, are visually primary.

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
