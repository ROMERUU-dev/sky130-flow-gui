# SKY130 Flow GUI

A Linux desktop app for managing a practical SKY130 workflow from a single interface.

It does not replace `xschem`, `magic`, `ngspice`, `netgen`, or `klayout`. It coordinates them, keeps outputs organized, and gives you a cleaner workflow for schematic, post-layout, and validation tasks.

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

### Option 2: Use the Setup Assistant from the app

If the GUI already opens on your machine, go to `⬢ Entorno / Setup` and follow the wizard.

The Ubuntu bootstrap currently installs the base toolchain:

- `xschem`
- `ngspice`
- `magic`
- `netgen`
- `klayout`
- `python3`, `python3-pip`, `python3-venv`

It also prepares the project `.venv` and installs Python requirements from `requirements.txt`.

## Ubuntu Environment Notes

The app works best when these are available:

- Linux desktop session
- `xschem`
- `ngspice`
- `magic`
- `netgen`
- `klayout`
- `PDK_ROOT`
- `SKY130A`

The Setup Assistant can detect common installations and apply discovered paths automatically.

Important:

- the tool bootstrap is implemented for Ubuntu/Debian-style systems using `apt`
- the PDK may still need manual installation or manual path review depending on the machine
- final foundry signoff is still outside the scope of this GUI

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

## Project Structure

```text
app/
  core/
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
- This app improves workflow management; it is not a replacement for signoff flows or foundry-qualified verification.

## Recommended Next Steps

If you are using the project on a fresh Ubuntu machine:

1. Open `⬢ Entorno / Setup`
2. Run the wizard
3. Review `Preferences` only if something still needs manual tuning
4. Select a project
5. Start from `Extraction` or `Simulation`
