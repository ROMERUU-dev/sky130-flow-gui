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
  ui/
    main_window.py
    simulation_tab.py
    lvs_tab.py
    extraction_tab.py
    antenna_tab.py
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

## Actualizar una instalación existente

Si ya lo tenías instalado desde este repo, tienes dos opciones:

1. Desde la GUI (Preferences):
   - `Buscar actualizaciones`
   - `Actualizar ahora`
2. Desde terminal:

```bash
git pull --ff-only
```

Después de actualizar, reinicia la aplicación.

## Instalar como icono de aplicación (Linux)

En la pestaña Preferences usa **Instalar icono de aplicación**.
Esto crea:

- `~/.local/bin/sky130-flow-gui` (launcher)
- `~/.local/share/applications/sky130-flow-gui.desktop`
- `~/.local/share/icons/hicolor/scalable/apps/sky130-flow-gui.svg`

Luego podrás abrirla desde el menú de aplicaciones del escritorio.

## Cómo abrir la aplicación

Puedes abrirla de 3 formas:

1. Desde terminal en el repo:

```bash
python -m app.main
```

2. Desde el launcher (si instalaste icono):

```bash
~/.local/bin/sky130-flow-gui
```

3. Desde el menú de aplicaciones de tu escritorio (entrada: **SKY130 Flow GUI**).

## Desinstalar

Si instalaste icono/launcher, elimina estos archivos:

```bash
rm -f ~/.local/bin/sky130-flow-gui
rm -f ~/.local/share/applications/sky130-flow-gui.desktop
rm -f ~/.local/share/icons/hicolor/scalable/apps/sky130-flow-gui.svg
update-desktop-database ~/.local/share/applications
```

Y para quitar el código de la app, elimina el directorio del repositorio donde la clonaste.

## Subir cambios bien desde Codex Web (rápido)

1. Verifica que estás en tu rama de trabajo (por ejemplo `work`) y que los cambios estén confirmados (commit).
2. Publica la rama al remoto (`origin`): `git push -u origin work`.
3. En GitHub, crea el Pull Request: `work` -> `main`.
4. Si hay conflictos en GitHub:
   - **Accept incoming**: te quedas con lo que viene de la rama del PR.
   - **Accept current**: te quedas con lo que ya tenía la rama base.
   - Recomendado: revisar el diff final antes de confirmar el merge.
5. Haz **Merge pull request** en GitHub y luego en tu máquina local:
   - `git checkout main`
   - `git pull --ff-only origin main`
