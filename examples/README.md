# circuit examples

One JSON file per circuit. All examples render and support **DC steady-state simulation**.
Falstad export supports **all examples**. Component values use base SI units.

| example | circuit |
| --- | --- |
| 01 | LED with current-limiting resistor |
| 02 | voltage divider |
| 03 | parallel resistors |
| 04 | switch-controlled LED |
| 05 | normally open button and LED (held down initially) |
| 06 | forward-biased diode |
| 07 | RC charging |
| 08 | RL step response |
| 09 | potentiometer divider |
| 10 | photodiode sensor |
| 12 | LED circuit with explicit wire |

## incomplete circuits

`incomplete/03_parallel_resistors_incomplete.json` disconnects R2’s return terminal;
R1 still has a complete path. `incomplete/04_switch_led_incomplete.json` disconnects
the LED’s return terminal even though the switch is closed. Both are valid topology
JSON with an unconnected terminal represented by a singleton net.

Load these separately, for example:

```sh
python main.py examples/incomplete/04_switch_led_incomplete.json
```

Both also appear in **Circuit Library** after the complete examples. They are
rendering/diagnostic samples; Falstad export does not support these incomplete
layouts. Existing library records are preserved when these samples are added.

## use

```sh
python main.py examples/01_led_series.json
python database.py --import-examples examples
```

Or click **Circuit Library** in the app. Switch/button states come from JSON,
reflecting the physical circuit. Undetermined results show `—`.

Capacitors are open circuits and inductors are ideal shorts at DC equilibrium;
initial conditions do not affect that result. Charging waveforms are not computed
locally; Falstad runs its own transient simulation.
Potentiometer results use track voltage (1–2) and current entering terminal 1;
hover over its results for all three terminal currents.

Terminals are `"1"` and `"2"`; potentiometers add `"3"` for the wiper. LEDs use
`LED1`, inductors use `L1`. Full parameter definitions are in
[circuits.md](../circuits.md).

Potentiometers export as two track resistors joined at the wiper; photodiodes
export as a diode in parallel with a photocurrent source. Diode/LED results may
differ because Falstad uses nonlinear models instead of our fixed-drop model.
Export currently requires a single-source series/parallel layout and unloaded
potentiometer wipers. Example text exports are in [artifacts](../artifacts/).

See the [Falstad/CircuitJS credits](../README.md#references) for references.

## updates

- 2026-10-31 — add simple circuits desktop prototype
- 2026-10-31 — add more component types
- 2026-10-31 — add falstad export support for more component types
- 2026-10-31 — update read me
- 2026-10-31 — update ui
- 2026-11-01 — ui updates
