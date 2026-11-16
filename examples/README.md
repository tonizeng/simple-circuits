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
| 10 | photoresistor divider |
| 12 | LED circuit with explicit wire |
| 13 | series RLC circuit |

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

All example sources use **3.3 V**, matching the configured supply maximum.
Checks assume settled DC; capacitor/inductor startup and turn-off are not assessed.
Live protection belongs to firmware/hardware. Existing unmodified library examples upgrade automatically.

## error circuit

**Error — Shorted Supply** (`errors/01_supply_short.json`) connects an ideal wire
across the 3.3 V source, bypassing a parallel resistor. Open it in **Circuit Library**
to see the Error card and denied power validation. This is a software-only fault
example; no malformed JSON is needed.

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

Potentiometers export as two track resistors joined at the wiper; photoresistors
export as resistors using their supplied resistance. Diode/LED results may
differ because Falstad uses nonlinear models instead of our fixed-drop model.
Export currently requires a single-source series/parallel layout and unloaded
potentiometer wipers. Example text exports are in [artifacts](../artifacts/).

See the [Falstad/CircuitJS credits](../README.md#references) for references.

**Error and Warning — Shorted Supply and Disconnected LED**
(`errors/02_short_disconnected_led.json`) shows both severity cards: W1 shorts
the supply and LED1 terminal 2 is disconnected. Diagnostic sample only.

## updates

- 2026-10-31 — add simple circuits desktop prototype
- 2026-10-31 — add more component types
- 2026-10-31 — add falstad export support for more component types
- 2026-10-31 — update read me
- 2026-10-31 — update ui
- 2026-11-01 — ui updates
- 2026-11-12 — add circuit validation logic

The series RLC example uses a 3.3 V source, 10 Ω resistor, 10 mH inductor, and
100 µF capacitor. Rendering, DC equilibrium, and Falstad export are supported.
A local analytical series-RLC preview supports underdamped, critically damped,
and overdamped responses through the schematic time slider. Inductor turn-off protection checks are deferred pending the
hardware design; software checks do not verify transient protection.

Example 08 supports a local first-order RL time preview: τ = 100 µs for
10 mH / 100 Ω. Use the schematic slider for predicted voltage/current changes;
select L1 for timing and plots. Example 13 also supports an analytical series-RLC time preview.
- 2026-11-16 — changed ui
