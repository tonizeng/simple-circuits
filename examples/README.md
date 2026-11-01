# circuit examples

One JSON file per circuit. All examples render; **1–5 also support DC simulation
and Falstad export**. Component values use base SI units.

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
| 11 | motor with flyback diode |
| 12 | LED circuit with explicit wire |

## use

```sh
python main.py examples/01_led_series.json
python database.py --import-examples examples
```

Or click **View Examples** in the app. Switch/button states come from JSON,
reflecting the physical circuit. Unsupported or undetermined results show `—`.

Terminals are `"1"` and `"2"`; potentiometers add `"3"` for the wiper. LEDs use
`LED1`, inductors use `L1`. Full parameter definitions are in
[circuits.md](../circuits.md).

## Updates

- 2026-10-31 — add simple circuits desktop prototype
- 2026-10-31 — --amend-no-edit
