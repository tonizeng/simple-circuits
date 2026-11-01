# simple circuits

A Python/PySide6 desktop digital twin for classroom circuits on macOS, Windows,
and Linux. Circuit data drives the schematic and electrical results.

## run

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python main.py
```

On Windows, create the environment with `python` and activate it with
`.venv\Scripts\Activate.ps1`.

## current features

- Eleven circuit examples, vector symbols, component legends, and hover highlights.
- DC steady-state MNA for all 11 examples; Falstad export for examples 1–5.
- SQLite example browser; an empty database is seeded automatically.
- Current magnitude and direction arrows; unknown results display `—`.

Switches/buttons reflect topology data and cannot be changed in the UI. LEDs use
fixed forward voltage by default; an optional exponential solver is available
with `solve_dc(circuit, led_model="falstad")`.

Capacitors are open and inductors are zero-voltage connections at DC equilibrium.
Charging and other transient waveforms are not simulated.
Hardware communication, UI saving/settings, and transient simulation remain pending.

## useful commands

```sh
python main.py examples/01_led_series.json
python database.py --import-examples examples
python falstad.py examples/01_led_series.json --output led-falstad.txt
python -m unittest discover -s tests
```

See [examples](examples/README.md) for the circuit list and
[circuits.md](circuits.md) for schema, solver, and export details.

## commits

Run `git config core.hooksPath .githooks` after cloning to enable automatic
README update entries and lowercase commit messages. This checkout is configured.

## updates

- 2026-10-31 — add simple circuits desktop prototype
## Updates
- 2026-10-31 — add more component types
