# simple circuits

A Python/PySide6 desktop digital twin for classroom circuits on macOS, Windows,
and Linux. Circuit data drives the schematic and electrical results.

## run

Requires Python 3.10 or newer.

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python main.py
```

On Windows, create the environment with `python` and activate it with
`.venv\Scripts\Activate.ps1`.

## current features

- Eleven 3.3 V circuit examples, vector symbols, component legends, hover highlights,
  and Guide/Formulas tabs for reading results and equation references.
- DC steady-state MNA for all 11 examples; Falstad export for all bundled examples.
- Read-only bundled Circuit Library; saved user circuits are stored in SQLite under My Circuits.
- Current magnitude and direction arrows; unknown results display `—`.
- Pre-power checks against 3.3 V / 1.5 A, with short detection and automatic
  Error/Warning cards in a draggable panel inside the schematic. The board requests approval; firmware owns power and cutoff.

Switches/buttons reflect topology data and cannot be changed in the UI. LEDs use
a fixed forward-voltage model.

Capacitors are open and inductors are zero-voltage connections at DC equilibrium.
Charging and other transient waveforms are not simulated locally.
Falstad export requires a single-source series/parallel layout with unloaded
potentiometer wipers. Falstad runs its own simulation; results may differ.
Settings let users choose and save component, node, and current-arrow colours.
Battery voltage/current telemetry can feed the protection API and update calculations.
Physical current limiting/cutoff still requires firmware and hardware support; serial
integration remains pending. Save supports new circuits, personal copies, updates, and uploaded builds in reference mode; all saves go to My Circuits.

## useful commands

```sh
python main.py examples/01_led_series.json
python falstad.py examples/01_led_series.json --output led-falstad.txt
python -m unittest discover -s tests
```

See [examples](examples/README.md) for the circuit list and
[circuits.md](circuits.md) for schema, solver, and export details.

## equation assets

Formulas use pre-generated SVGs; Matplotlib is not needed to run the app.
To regenerate them:

```sh
python -m pip install -r requirements-dev.txt
python tools/generate_formulas.py
```

## commits

Run `git config core.hooksPath .githooks` after cloning to enable automatic
README update entries and lowercase commit messages. The hook appends entries when enabled.

## references

[Falstad Circuit Simulator](https://www.falstad.com/circuit/) is the external
simulator opened by the export feature. Circuit calculations run locally in
Python.

## updates

- 2026-10-31 — add simple circuits desktop prototype
- 2026-10-31 — add more component types
- 2026-10-31 — add falstad export support for more component types
- 2026-10-31 — update read me
- 2026-10-31 — update ui
- 2026-11-01 — ui updates
- 2026-11-12 — add circuit validation logic
- 2026-11-16 — changed ui
- 2026-11-23 — modernize ui
- 2026-11-23 — add building from scrach + reference
