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

- Eleven circuit examples, vector symbols, component legends, hover highlights,
  and Guide/Formulas tabs for reading results and equation references.
- DC steady-state MNA for all 11 examples; Falstad export for all bundled examples.
- SQLite circuit library; an empty database is seeded automatically.
- Current magnitude and direction arrows; unknown results display `—`.

Switches/buttons reflect topology data and cannot be changed in the UI. LEDs use
fixed forward voltage by default; an optional exponential solver is available
with `solve_dc(circuit, led_model="falstad")`.

Capacitors are open and inductors are zero-voltage connections at DC equilibrium.
Charging and other transient waveforms are not simulated locally.
Falstad export requires a single-source series/parallel layout with unloaded
potentiometer wipers. Falstad runs its own simulation; results may differ.
Settings let users choose and save component, node, and current-arrow colours.
Hardware communication, UI saving, and transient simulation remain pending.

## useful commands

```sh
python main.py examples/01_led_series.json
python database.py --import-examples examples
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

[Falstad Circuit Simulator](https://www.falstad.com/circuit/) by Paul Falstad,
and [CircuitJS1](https://github.com/sharpie7/circuitjs1), adapted for the browser
by Iain Sharp, are references for export formats and the optional exponential
LED model. This app exports circuit data to CircuitJS; its local solver runs
independently.

## updates

- 2026-10-31 — add simple circuits desktop prototype
- 2026-10-31 — add more component types
- 2026-10-31 — add falstad export support for more component types
- 2026-10-31 — update read me
- 2026-10-31 — update ui
- 2026-11-01 — ui updates
