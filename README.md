# SKY130 Flow GUI

A Linux desktop app for managing a practical SKY130 workflow from a single interface.

It does not replace `xschem`, `magic`, `ngspice`, `netgen`, or `klayout`. It coordinates them, keeps outputs organized, and gives you a cleaner workflow for schematic, post-layout, and validation tasks.

The environment diagnostics are intentionally strict:

- base EDA tools are validated separately from the SKY130 PDK
- `netgen-lvs` is accepted as a valid Ubuntu-provided Netgen binary
- tool versions are checked against a declared minimum, so Ubuntu's Magic 8.3.105 and Netgen 1.5.133 are reported as too old rather than passing silently
- a Python environment that is not owned and writable by the desktop user is reported explicitly
- missing Qt/X11 runtime libraries for PySide6 are flagged before the GUI starts, and skipped on Wayland where they are not used

## What It Does

- Simulation with waveform and spectrum viewing
- Post-layout extraction flow with Magic
- LVS flow with Netgen
- Antenna check flow with KLayout
- EM sizing support from waveform data
- Project-aware output management under `runs/`
- Persistent preferences and recent projects
- Setup Assistant for validating and bootstrapping the environment on Ubuntu

## Current UI

The app currently includes:

- Left-side navigation
- Light, dark and follow-the-system themes
- Collapsible simulation panels
- Post-layout wrapper controls for:
  - initial conditions
  - no load / capacitive load / series RC load
- Waveform and frequency-spectrum viewers
- Setup wizard for:
  - reviewing the system
  - installing core tools on Ubuntu
  - applying detected paths
  - final validation

## Main Tabs

- `Simulación / Simulation`
- `LVS`
- `Extracción / Extraction`
- `Antena / Antenna`
- `EM`
- `Entorno / Setup`
- `Proyecto / Project`
- `Preferencias / Preferences`

## Installation

### Option 1: Debian package (Ubuntu 26.04 LTS)

```bash
sudo apt install ./sky130-flow-gui_0.3.0_amd64.deb
sky130-flow-gui
```

The package bundles its own Python runtime, but prefers a user-owned environment at
`~/.local/share/sky130-flow-gui/venv` when one exists. That environment is created and
repaired from the app, without root, so a system Python upgrade cannot strand it.

### Option 2: Manual Python setup

```bash
python3 -m venv ~/.local/share/sky130-flow-gui/venv
~/.local/share/sky130-flow-gui/venv/bin/python -m pip install -r requirements.txt
~/.local/share/sky130-flow-gui/venv/bin/python -m app.main
```

Create it as your normal user. Never build or repair it with `sudo` or `pkexec`; the app
refuses to do so itself.

You can also manage it from the command line:

```bash
python3 -m app.core.python_env diagnose
python3 -m app.core.python_env repair
```

### Option 3: Use the Setup Assistant from the app

If the GUI already opens, go to `⚙ Preferencias → Entorno` and follow the wizard.

The Ubuntu bootstrap installs system packages plus a current upstream Magic build:

- `xschem`, `ngspice`, `netgen-lvs`, `klayout` from apt
- `magic` built from the official repository at tag `8.3.684` into `/usr/local/bin`
- `python3`, `python3-pip`, `python3-venv`
- Qt runtime libraries for PySide6

On GCC 15 (the Ubuntu 26.04 default) the Magic build is configured with `-std=gnu17`,
because the compiler's C23 default rejects constructs the sources still use.

It does not touch the Python environment. Prepare that afterwards as the normal user.

Ubuntu ships Magic 8.3.105, which current SKY130 techfiles reject outright. To repair an
existing machine manually:

```bash
bash scripts/install_magic_ubuntu.sh
/usr/local/bin/magic --version
```

Then set the Magic executable in Preferences to `/usr/local/bin/magic` if `which magic`
still resolves to `/usr/bin/magic`.

### Installing the SKY130 PDK

The PDK is not bundled with this app. The recommended route uses the upstream prebuilt
builds published by the FOSSi Foundation:

```bash
bash scripts/install_sky130_pdk_ciel.sh
```

This installs the `ciel` PDK manager for the current user and enables the open_pdks build
pinned in `app/data/dependency_manifest.json`. Available builds are listed at
<https://github.com/fossi-foundation/ciel-releases/releases>.

To build from source instead:

```bash
bash scripts/build_sky130_pdk_from_sources.sh
```

## Ubuntu Environment Notes

The app works best when these are available:

- Linux desktop session
- `xschem`
- `ngspice`
- `magic`
- `netgen` or `netgen-lvs`
- `klayout`
- `PDK_ROOT`
- `SKY130A`

The Setup Assistant can detect common installations and apply discovered paths automatically.

Important:

- the tool bootstrap is implemented for Ubuntu/Debian-style systems using `apt` plus the official Magic source release
- installing apt packages does not install the SKY130 PDK automatically
- Ubuntu ships Magic 8.3.105, too old for current SKY130 techfiles; use `scripts/install_magic_ubuntu.sh` when the validator reports a Magic/PDK incompatibility
- the validator looks for `sky130A` in `PDK_ROOT`, `/usr/local/share/pdk`, `/usr/share/pdk`, `~/pdk`, `~/.volare`, and `~/eda/pdk`
- the app checks `sky130A/libs.tech/magic`, `netgen`, `klayout`, `ngspice`, and `xschem` separately, so an incomplete PDK is reported as incomplete rather than OK
- the Python environment lives under `~/.local/share/sky130-flow-gui/venv`, so a read-only `/opt` install is not a problem
- if that environment belongs to another user, the validator reports it explicitly instead of treating it as healthy
- final foundry signoff is still outside the scope of this GUI

## Ubuntu Qt Runtime Notes

On a **Wayland** session (the Ubuntu default) Qt loads the `wayland` platform plugin and
the `xcb` helper libraries below are not needed. The startup check knows this and skips
them; earlier versions refused to start on a perfectly working Wayland desktop.

On an **X11** session, installing `PySide6` with `pip` is not sufficient on a clean Ubuntu
desktop if Qt/X11 runtime libraries are missing. A common failure mode is:

- Qt finds the `xcb` platform plugin
- the plugin still fails to load
- the process exits because libraries such as `libxcb-cursor0` are missing

The bootstrap installs the common runtime packages needed to avoid that first-run failure on Ubuntu. If you are setting up the environment manually, install at least:

- `libxcb-cursor0`
- `libxkbcommon-x11-0`
- `libxcb-xkb1`
- `libxcb-xfixes0`
- `libgl1`

The bootstrap also installs extra compatibility packages that are often helpful on clean or minimal systems:

- `libxcb-xinerama0`
- `libxcb-icccm4`
- `libxcb-image0`
- `libxcb-keysyms1`
- `libxcb-render-util0`
- `libxcb-randr0`
- `libxcb-shape0`

## Running the App

From the repository root:

```bash
python -m app.main
```

If you are using a virtual environment:

```bash
source ~/.local/share/sky130-flow-gui/venv/bin/activate
python -m app.main
```

## Post-Layout Flow

The app now supports a more practical post-layout workflow:

- normalizes project roots correctly
- keeps extracted and simulation outputs under the main project `runs/`
- detects top cells from `mag/`
- can send extracted netlists directly to Simulation
- can build a post-layout simulation wrapper automatically for Tiny Tapeout-style blocks

Wrapper options include:

- use initial conditions
- no load
- capacitive load
- series RC load

## Output Policy

Generated files are stored in the active project when a project is selected:

- `runs/logs`
- `runs/results`
- `runs/lvs`
- `runs/extraction`
- `runs/antenna`

If no project is selected, the app falls back to repository-local `workspace/` directories.

## Setup Assistant

The `⬢ Entorno / Setup` tab is the recommended starting point on a new machine.

It provides:

1. System review
2. Ubuntu tool installation
3. Automatic path application
4. Final validation

It also summarizes readiness for:

- Tools
- PDK
- Python
- Overall environment

The validator distinguishes between:

- tool not installed
- tool installed under an alternate binary name such as `netgen-lvs`
- SKY130 PDK absent
- SKY130 PDK incomplete
- the user Python environment missing, owned by another user, or not writable

## Preferences

The `Preferencias / Preferences` tab is still the place for:

- fine-tuning tool paths
- adjusting PDK paths
- validating the environment manually
- updating the local installation
- installing the desktop launcher/icon

## EM Sizing

The EM sizing flow is a support tool for estimating routing decisions from current waveforms.

It can:

- load current waveform files
- compute current metrics
- suggest routing widths and via counts

It is not foundry-qualified EM signoff.

## Install as a Desktop App

From `Preferences`, use `Install application icon`.

That creates:

- `~/.local/bin/sky130-flow-gui`
- `~/.local/share/applications/sky130-flow-gui.desktop`
- `~/.local/share/icons/hicolor/scalable/apps/sky130-flow-gui.svg`

## Debian Package

The repository now includes a base `.deb` packaging flow for Ubuntu/Debian systems.

Build it from the repo root:

```bash
./scripts/build_deb.sh
```

By default, the package version is read from the repo `VERSION` file.

Or specify version and architecture explicitly:

```bash
./scripts/build_deb.sh 0.3.0 all
```

The generated package is written to:

```text
dist/sky130-flow-gui_<version>_<arch>.deb
```

Install it with:

```bash
sudo dpkg -i dist/sky130-flow-gui_<version>_<arch>.deb
```

What this package does:

- installs the app under `/opt/sky130-flow-gui`
- installs a launcher under `/usr/bin/sky130-flow-gui`
- installs a desktop entry and icon

What it does not do by itself:

- install the full SKY130 PDK in every environment
- guarantee that `/opt/sky130-flow-gui` is writable by the current desktop user
- repair a Python environment owned by another user
- replace the Setup Assistant
- replace the Ubuntu bootstrap for the VLSI toolchain

Recommended flow after installing the `.deb`:

1. Launch the app
2. Open `⬢ Entorno / Setup`
3. Complete the setup wizard
4. Validate the environment before running extraction or simulation

## PDK Bundle Archive

Releases up to `v0.2.0` published a `tt-pdk-sky130a` tarball produced by archiving the
maintainer's own `~/pdk/sky130A`. That is no longer done: the archive was not
reproducible, it captured whatever local modifications happened to be present, and it
pinned everyone to one workstation's state.

The download route in the Setup Assistant is disabled in the shipped manifest, and the
assistant explains why. Use the prebuilt upstream PDK or a source build instead.

If you do want to publish a bundle, `scripts/build_sky130_pdk_bundle.sh` builds one from a
clean `open_pdks` checkout, refuses to package an in-use PDK root, and writes a
`BUNDLE_PROVENANCE.txt` recording the `open_pdks` ref, the Magic version used, and the
build date:

```bash
./scripts/build_sky130_pdk_bundle.sh stable
```

Record the printed SHA-256 in `app/data/dependency_manifest.json` and re-enable the bundle
route only once the asset is actually uploaded.

## Project Structure

```text
app/
  core/          environment probing, settings, manifest, runners, waveform parsing
  data/          dependency_manifest.json: tool pins, PDK routes, version floors
  resources/     branding assets
  runners/       command construction per tool
  services/      EM sizing
  ui/            tabs, theme tokens, waveform viewer
packaging/       Debian desktop entry
scripts/         Ubuntu bootstrap, Magic build, PDK installers, .deb build
tests/
requirements.txt
CHANGELOG.md
README.md
```

## Tests

```bash
python3 -m unittest discover -s tests -t .
```

Qt-dependent tests run headless through `QT_QPA_PLATFORM=offscreen`.

## Limitations

- The Ubuntu bootstrap does not guarantee a fully automatic SKY130 PDK installation on every machine.
- Some flows still depend on the user having a valid external installation of the VLSI toolchain.
- If you add a dedicated squirrel PNG for splash/branding, place it under `app/resources/` so startup code can resolve it independently of the current working directory. The current fallback asset is `app/resources/sky130-flow-gui.svg`.
- This app improves workflow management; it is not a replacement for signoff flows or foundry-qualified verification.
- The `.deb` packaging flow is designed for Ubuntu/Debian and assumes `dpkg-deb` is available on the build machine.
- The published `.deb` bundles a Python 3.14 runtime and is built on Ubuntu 26.04 LTS. On an older Ubuntu, install from source instead.

## Recommended Next Steps

If you are using the project on a fresh Ubuntu machine:

1. Open `⬢ Entorno / Setup`
2. Run the wizard
3. Review `Preferences` only if something still needs manual tuning
4. Select a project
5. Start from `Extraction` or `Simulation`
