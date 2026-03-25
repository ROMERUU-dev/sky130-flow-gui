# SKY130 Flow GUI (Linux Desktop MVP)

A Python/PySide6 desktop workflow manager for SKY130 analog/custom IC tasks.  
It **does not replace** xschem, magic, klayout, ngspice, or netgen; it orchestrates them from a clean GUI.

## MVP Features

- Native Linux desktop app (PySide6)
- Non-blocking command execution using `QProcess`
- Tabs for:
  - Simulation (`ngspice`)
  - LVS (`netgen`)
  - Extraction/Post-layout (`magic`)
  - Antenna Check (`klayout`)
  - EM Sizing (`ngspice` current waveform analysis for routing estimates)
  - Project/Files
  - Preferences
- Persistent preferences and recent projects (`QSettings`)
- Environment/path validation with status table
- Exact command shown in logs for reproducibility
- Standardized run outputs under project `runs/` directories
- Stop running jobs
- Send extracted netlist to simulation tab
- Technical, dark-mode friendly default Qt styling

## Project Structure

```text
app/
  main.py
  core/
    command_runner.py
    env_validator.py
    log_parser.py
    output_manager.py
    project_manager.py
    settings_manager.py
    update_manager.py
    integration_manager.py
  runners/
    base_runner.py
    ngspice_runner.py
    lvs_runner.py
    magic_runner.py
    antenna_runner.py
  resources/
    sky130-flow-gui.svg
  data/
    sky130_em_profiles.json
  models/
    em_models.py
  services/
    em_service.py
  ui/
    main_window.py
    simulation_tab.py
    lvs_tab.py
    extraction_tab.py
    antenna_tab.py
    em_sizing_tab.py
    project_tab.py
    preferences_tab.py
    waveform_viewer.py
    splash.py
    widgets.py
requirements.txt
README.md
```

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run

```bash
python -m app.main
```

## Simulation Guide

- Detailed Spanish guide for the simulation/visualization workflow:
  - `docs/SIMULATION_GUIDE_ES.md`

## EM Sizing Tab

The **EM Sizing** tab is an engineering support tool for reviewing branch currents exported from `ngspice` and estimating interconnect sizing decisions for manual SKY130 / Tiny Tapeout routing.

It can:

- Load current waveform files from `ngspice` outputs
- Support CSV and whitespace-separated `wrdata`-style text files
- Compute `I_avg`, `I_rms`, and `I_peak`
- Classify branches as `power`, `output`, or `signal`
- Apply `average`, `rms`, `peak`, or conservative `auto` design-metric selection
- Recommend metal width from estimated current-density rules plus DRC minimum and routing-grid rounding
- Recommend via count and a compact via array
- Export results to CSV, JSON, and plain text

Important limits:

- This is an **engineering estimation tool**, not official foundry EM signoff.
- EM/current-density values in `app/data/sky130_em_profiles.json` are configurable, conservative, user-defined estimates.
- DRC minimum width and EM sizing are handled separately in the calculations and UI.
- Final signoff must still use foundry-qualified rules and the proper signoff flow.

Supported waveform file shape:

- First column must be time
- Remaining columns are current branches
- Header row is optional
- Scientific notation, blank lines, extra spaces, and simple comment lines are accepted

Profile units:

- thickness: `um`
- minimum width: `um`
- routing grid: `um`
- current density: `mA/um^2`
- via current: `mA`

Example usage:

1. Export branch current waveforms from `ngspice` to CSV or whitespace-separated text.
2. Open **EM Sizing** and load the file or use **Load Latest Result**.
3. Choose the profile, design metric, target metal, via type, and margin factor.
4. Review per-branch recommendations, warnings, and the detail panel before routing in Magic.

## SKY130 Environment Assumptions

1. You are on Linux with desktop access.
2. Tools are installed and runnable from PATH or explicitly configured:
   - `xschem`, `ngspice`, `magic`, `netgen`, `klayout`
3. PDK is installed and SKY130A content is available.
4. You can provide paths for:
   - `PDK_ROOT`
   - `SKY130A`
   - magic rcfile
   - netgen setup tcl
   - klayout antenna deck/script

## Notes for Real Installations

- In **Preferences**, configure absolute tool paths and PDK paths.
- Use **Validate** to identify missing executables/files.
- The app injects `PDK_ROOT` and `SKY130A` into subprocess environments.
- For extraction in Magic:
  - Provide top cell name
  - Either select an existing extraction script or let app generate one
- For LVS:
  - Provide extracted and schematic netlists
  - Provide `sky130A_setup.tcl` from your PDK
- For antenna checks:
  - Provide a KLayout-compatible rule deck/script

## MVP Limitations

- Waveform plotting is ready to receive real parsed simulation traces (no dummy/example traces are shown by default).
- Log parsing is heuristic/simple and intended as a starting point.
- EM sizing rules are conservative estimates and are not signoff-qualified.

## Phase 2 Suggestions

- DRC tab
- Better ngspice raw parsing and selectable traces from real output
- Pre-layout vs post-layout overlay comparisons
- Project session file import/export
- Simulation templates
- Rich report export (PDF/HTML)
- AppImage/PyInstaller packaging

## Output Location Policy

All generated files are stored either:

- In the active project folder (preferred):
  - `runs/logs`
  - `runs/results`
  - `runs/lvs`
  - `runs/extraction`
  - `runs/antenna`
- Or, if no project is selected, in repository-local fallback workspace:
  - `workspace/logs`
  - `workspace/results`
  - `workspace/lvs`
  - `workspace/extraction`
  - `workspace/antenna`

No output is written to Desktop by default.

## Update an Existing Installation

If you already installed it from this repo, you have two options:

1. From the GUI (`Preferences`):
   - `Check for updates`
   - `Update now`
2. From the terminal:

```bash
git pull --ff-only
```

After updating, restart the application.

## Install as an Application Icon (Linux)

In the `Preferences` tab, use **Install application icon**.
This creates:

- `~/.local/bin/sky130-flow-gui` (launcher)
- `~/.local/share/applications/sky130-flow-gui.desktop`
- `~/.local/share/icons/hicolor/scalable/apps/sky130-flow-gui.svg`

You will then be able to open it from your desktop applications menu.

## How to Open the Application

You can open it in 3 ways:

1. From a terminal in the repo:

```bash
python -m app.main
```

2. From the launcher (if you installed the icon):

```bash
~/.local/bin/sky130-flow-gui
```

3. From your desktop applications menu (entry: **SKY130 Flow GUI**).

## Uninstall

If you installed the icon/launcher, remove these files:

```bash
rm -f ~/.local/bin/sky130-flow-gui
rm -f ~/.local/share/applications/sky130-flow-gui.desktop
rm -f ~/.local/share/icons/hicolor/scalable/apps/sky130-flow-gui.svg
update-desktop-database ~/.local/share/applications
```

To remove the app source code as well, delete the repository directory where you cloned it.

## Push Changes Properly from Codex Web (Quick)

1. Verify that you are on your working branch (for example `work`) and that your changes are committed.
2. Publish the branch to the remote (`origin`): `git push -u origin work`.
3. On GitHub, create the Pull Request: `work` -> `main`.
4. If there are conflicts on GitHub:
   - **Accept incoming**: keep what comes from the PR branch.
   - **Accept current**: keep what the base branch already had.
   - Recommended: review the final diff before confirming the merge.
5. Click **Merge pull request** on GitHub and then on your local machine:
   - `git checkout main`
   - `git pull --ff-only origin main`
