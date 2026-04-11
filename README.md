# SKY130 Flow GUI

A Linux desktop app for managing a practical SKY130 workflow from a single interface.

It does not replace `xschem`, `magic`, `ngspice`, `netgen`, or `klayout`. It coordinates them, keeps outputs organized, and gives you a cleaner workflow for schematic, post-layout, and validation tasks.

The environment diagnostics are intentionally strict:

- base EDA tools are validated separately from the SKY130 PDK
- `netgen-lvs` is accepted as a valid Ubuntu-provided Netgen binary
- a root-owned or non-writable `.venv` is reported explicitly
- missing Qt/X11 runtime libraries for PySide6 on Ubuntu are flagged before the GUI starts

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
- Refined light theme
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

### Option 1: Manual Python setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m app.main
```

Create `.venv` as your normal user. Do not create or repair the repository virtualenv with `sudo` or `pkexec`.

### Option 2: Use the Setup Assistant from the app

If the GUI already opens on your machine, go to `⬢ Entorno / Setup` and follow the wizard.

The Ubuntu bootstrap installs Ubuntu system packages plus the official Magic `8.3.634` source release:

- `xschem`
- `ngspice`
- `magic` from apt as a baseline, then `/usr/local/bin/magic` built from the official `magic-8.3.634.tgz` release
- `netgen-lvs` (accepted by the app as Netgen)
- `klayout`
- `python3`, `python3-pip`, `python3-venv`
- Qt/X11 runtime libraries for PySide6:
  - required in practice on clean Ubuntu: `libxcb-cursor0`, `libxkbcommon-x11-0`, `libxcb-xkb1`, `libxcb-xfixes0`, `libgl1`
  - preventive compatibility packages installed by the bootstrap: `libxcb-xinerama0`, `libxcb-icccm4`, `libxcb-image0`, `libxcb-keysyms1`, `libxcb-render-util0`, `libxcb-randr0`, `libxcb-shape0`

It does not create or modify `.venv`. Prepare the Python environment afterwards as the normal user:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
```

Some current SKY130 PDK techfiles require a newer Magic revision than the one shipped by older Ubuntu apt repositories. The Setup Assistant handles this during a clean tool install. If you are repairing an existing machine manually, install the official Magic `8.3.634` source release:

```bash
bash scripts/install_magic_8_3_634_ubuntu.sh
/usr/local/bin/magic -dnull -noconsole -version
```

Then set the Magic executable in Preferences to `/usr/local/bin/magic` if `which magic` still resolves to `/usr/bin/magic`.

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
- older Ubuntu apt repositories may ship Magic revisions too old for current SKY130 techfiles; use `scripts/install_magic_8_3_634_ubuntu.sh` when the validator reports a Magic/PDK incompatibility
- the validator looks for `sky130A` in `PDK_ROOT`, `/usr/local/share/pdk`, `/usr/share/pdk`, `~/pdk`, `~/.volare`, and `~/eda/pdk`
- the app checks `sky130A/libs.tech/magic`, `netgen`, `klayout`, `ngspice`, and `xschem` separately, so an incomplete PDK is reported as incomplete rather than OK
- a repository under `/opt` may be readable but not writable for the current user; in that case `.venv` creation is intentionally reported as a permissions problem
- if `.venv` belongs to `root`, the validator reports it explicitly instead of treating the Python environment as healthy
- final foundry signoff is still outside the scope of this GUI

## Ubuntu Qt/X11 Runtime Notes

Installing `PySide6` with `pip` is not sufficient on a clean Ubuntu desktop if Qt/X11 runtime libraries are missing. A common failure mode is:

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
source .venv/bin/activate
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
- `.venv` missing, root-owned, or not writable

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

Or specify version and architecture explicitly:

```bash
./scripts/build_deb.sh 0.1.0 all
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
- guarantee that `/opt/sky130-flow-gui` is writable by the current desktop user for `.venv` creation
- repair a root-owned `.venv`
- replace the Setup Assistant
- replace the Ubuntu bootstrap for the VLSI toolchain

Recommended flow after installing the `.deb`:

1. Launch the app
2. Open `⬢ Entorno / Setup`
3. Complete the setup wizard
4. Validate the environment before running extraction or simulation

## Project Structure

```text
app/
  core/
  resources/
  runners/
  services/
  ui/
scripts/
tests/
requirements.txt
README.md
```

## Limitations

- The Ubuntu bootstrap does not guarantee a fully automatic SKY130 PDK installation on every machine.
- Some flows still depend on the user having a valid external installation of the VLSI toolchain.
- If you add a dedicated squirrel PNG for splash/branding, place it under `app/resources/` so startup code can resolve it independently of the current working directory. The current fallback asset is `app/resources/sky130-flow-gui.svg`.
- This app improves workflow management; it is not a replacement for signoff flows or foundry-qualified verification.
- The `.deb` packaging flow is designed for Ubuntu/Debian and assumes `dpkg-deb` is available on the build machine.

## Recommended Next Steps

If you are using the project on a fresh Ubuntu machine:

1. Open `⬢ Entorno / Setup`
2. Run the wizard
3. Review `Preferences` only if something still needs manual tuning
4. Select a project
5. Start from `Extraction` or `Simulation`
