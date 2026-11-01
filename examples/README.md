# circuit examples

One JSON file per circuit. All examples render and support **DC steady-state simulation**.
Falstad export currently supports **1–5**. Component values use base SI units.

| example | circuit |
| --- | --- |
| 01 | LED with current-limiting resistor |
| 02 | voltage divider |
| 03 | parallel resistors |
| 04 | switch-controlled LED |
| 05 | normally open button and LED |
| 06 | forward-biased diode |
| 07 | RC charging |
| 08 | RL step response |
| 09 | potentiometer divider |
| 10 | photodiode sensor |
| 12 | LED circuit with explicit wire |

## use

```sh
python main.py examples/01_led_series.json
python database.py --import-examples examples
```

Or click **View Examples** in the app. Switch/button states come from JSON,
reflecting the physical circuit. Undetermined results show `—`.

Capacitors are open circuits and inductors are ideal shorts at DC equilibrium;
initial conditions do not affect that result. Charging waveforms are not computed.
Potentiometer results use track voltage (1–2) and current entering terminal 1;
hover over its results for all three terminal currents.

Terminals are `"1"` and `"2"`; potentiometers add `"3"` for the wiper. LEDs use
`LED1`, inductors use `L1`. Full parameter definitions are in
[circuits.md](../circuits.md).

## Updates

- 2026-10-31 — add simple circuits desktop prototype
- 2026-10-31 — --amend-no-edit
- 2026-10-31 — add more component types
