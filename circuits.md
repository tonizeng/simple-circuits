# Circuit source of truth

This is the living reference for agreed circuit data and modeling conventions.
Update it when a decision changes. Examples and proposals below are not yet an
implemented controller protocol.

## Agreed conventions

- The desktop application uses Python and PySide6. Circuit drawing and the
  electrical model are separate: changing a symbol's position or rotation must
  not change its electrical connections.
- The controller is expected to send circuit topology as JSON over serial.
- The input describes components and electrical nets. `components` lists every
  component, its unique ID, type, and electrical parameters. `nets` lists each
  node and the component terminals connected to it.
- All terminals on a net share the same electrical potential. Nets reference
  specific terminals, rather than just component IDs.
- Terminal IDs are strings: `"1"`, `"2"`, and, when needed, `"3"`, `"4"`, etc.
  Do not use `a`/`b`, `head`/`tail`, or polarity names as terminal IDs in JSON.
- Terminal identities remain fixed when a schematic symbol rotates.
- LED IDs use `L1`, `L2`, etc.; ordinary diodes use `D1`, `D2`, etc.
  IDs must be unique; component behavior is determined by `type`, not ID prefix.
- Assume the hardware can distinguish LEDs from ordinary diodes and supplies
  their component types and terminal polarity correctly.
- Hardware does not send an LED model type. Software selects the
  fixed-drop classroom model by default; no extra hardware fields
  are required. `forward_voltage_v` is the default conducting drop.
- Up to four physical connectors per controller are anticipated. This hardware
  limit does not imply a limit of four attached terminals per electrical net.

### Terminal meanings

| Component type | Terminal `"1"` | Terminal `"2"` |
| --- | --- | --- |
| Resistor | First end | Second end |
| LED / diode | Anode | Cathode |
| Voltage source | Positive | Negative |

Resistors have no electrical polarity. LED and voltage-source terminal mappings
must be followed by both the controller and the desktop app.

## Raw hardware schema and internal JSON

The agreed raw schema is components `(c_id, type, value)` and nodes
`(n_id, terminals)`, with terminal references `(c_id, "1" or "2")`.
Units are omitted: resistance is in ohms, source voltage and LED/diode forward
voltage are in volts. For example, a 4.7 kΩ resistor sends `4700`.

A future adapter will convert raw hardware records to the internal JSON below:
`c_id` → component `id`, `n_id` → net `id`, and `value` → the type-specific
parameter. The current parser accepts the internal format, not raw records.
LEDs and ordinary diodes are separate types; ordinary diode rendering is supported; its simulation is outside the initial scope.

## Internal JSON example

Series circuit: 5 V source → 330 Ω resistor → LED → source negative.
This is the format accepted by the current parser. Hardware framing and the
adapter remain pending controller integration.

```json
{
  "schema_version": 1,
  "circuit_id": "circuit-001",
  "name": "Resistor LED Circuit",
  "ground_node": "n0",
  "components": [
    {
      "id": "V1",
      "type": "voltage_source",
      "parameters": { "voltage_v": 5.0 }
    },
    {
      "id": "R1",
      "type": "resistor",
      "parameters": { "resistance_ohm": 330.0 }
    },
    {
      "id": "L1",
      "type": "led",
      "parameters": {
        "forward_voltage_v": 2.0
      }
    }
  ],
  "nets": [
    {
      "id": "n1",
      "terminals": [
        { "component_id": "V1", "terminal": "1" },
        { "component_id": "R1", "terminal": "1" }
      ]
    },
    {
      "id": "n2",
      "terminals": [
        { "component_id": "R1", "terminal": "2" },
        { "component_id": "L1", "terminal": "1" }
      ]
    },
    {
      "id": "n0",
      "terminals": [
        { "component_id": "L1", "terminal": "2" },
        { "component_id": "V1", "terminal": "2" }
      ]
    }
  ]
}
```

`ground_node` identifies the solver's 0 V reference, not necessarily earth ground.
The DC solver honors an explicit reference first. The parser itself leaves
an omitted reference unset. If omitted (or null), select
the net connected to terminal `"2"` of the single voltage source. With multiple
voltage sources, an explicit reference is required. With no voltage source, the
reference can remain unset for drawing, but the solver requires an explicit choice.
The selected net retains its original ID and remains in `nets`; only its voltage
unknown is omitted from the MNA system. MNA handles floating voltage sources
using extra current unknowns and voltage constraints without explicit supernodes.
With the optional Falstad-compatible exponential model, example 1 gives about
9.8157 mA and LED voltage 1.7608 V. The default fixed-drop model gives
`(5 - 2) / 330 ≈ 9.1 mA`. These are model predictions, not measured results.

## Planned processing

1. Parse JSON and validate IDs, types, parameter values, and terminal references.
   A component terminal must not appear in more than one net.
2. Resolve connectivity, merging nodes joined by ideal wires if the input has
   not already combined them into nets.
3. Build an electrical circuit model independent of drawing geometry.
4. Allocate solver indices from the resolved nodes; controller IDs are not
   matrix indices.
5. Build and solve a Modified Nodal Analysis (MNA) system. Resistors contribute
   conductance; ideal voltage sources require additional current unknowns and
   voltage constraints. LEDs need nonlinear or conducting/off-state handling.
6. Return electrical results for display alongside the schematic.

Drawing definitions should expose terminal coordinates using the same numbered
IDs as the electrical model. Layout, wire routing, Falstad export, and SQLite
storage are planned application responsibilities.

## Open decisions

- Mapping between physical controller connectors and component terminal IDs.
- Exact JSON envelope and serial message framing. One JSON object per line,
  terminated with a newline, has been suggested.
- Whether the controller sends resolved nets or raw connector/wire links.
- Treatment of floating circuits and solver reference selection for source-free
  circuits or disconnected electrical islands.
- Future transient support (the initial solver is DC only).
- Symbol geometry, dimensions, grid spacing, and resistor symbol convention.

## Current implementation

`topology.py` implements JSON/dict parsing and validation into electrical
component, terminal, net, and circuit objects. All 11 types listed below are
supported for drawing, using the example parameter fields. `components.py`
shares names, numeric/boolean validation rules, terminal definitions, and labels.
The current
LED input only requires `forward_voltage_v`; no model field is required or used.
The default DC LED model is fixed-drop on/off; the Falstad-compatible exponential
model is optional through solve_dc(circuit, led_model="falstad").
Every terminal must appear exactly once. Represent an open terminal with a
singleton net. Currently, an explicit `ground_node` must identify an existing
net; omission leaves the topology reference unset. The solver selects a reference
as described above without mutating the input circuit.
Only schema version 1 is supported; omission currently defaults to version 1.

`schematic.py` draws vector symbols with terminal 1 on the left and terminal 2
on the right, plus component IDs, nominal parameters, terminal numbers, and net
labels. Three-component series loops with one voltage source are laid out as a
rectangle: source on the left, the next component on top, and the final component
on the right, with a bottom return wire. Placement follows connectivity, retaining
terminal polarity. `layout.py` adds connectivity-based rectangular series/parallel
layouts for longer chains, parallel loads, and unloaded
potentiometers. Every bundled example now has a rectangular layout. General
non-series/parallel graphs or loaded potentiometer wipers still use net lanes.
The UI scales oversized drawings to fit on load. No electrical solving or node
merging is performed by this drawing logic.
Crossings without junction dots are not connections.

The physical circuit will use a fixed base board. Its node/position mapping will
be supplied later; current drawing coordinates are temporary and independent of
the electrical model.

`CircuitWindow.load_topology(data)` loads valid input into the canvas and circuit
name. Invalid input shows an error and preserves the previous circuit. Startup
remains blank until data is loaded.

Controller communication, raw-wire merging, and saving from the UI
have not yet been implemented. DC steady-state MNA is integrated for all 11 examples; transient charging is not yet simulated.

Basic storage now exists in `database.py`: SQLite stores only the circuit name
and JSON document. Names are unique; saving an existing name replaces its JSON.
The module offers save/load/list and JSON-folder import. The UI's View Examples
button lists database circuits and loads the selected JSON onto the canvas.
An empty database is seeded from bundled examples; existing records are not
overwritten by browsing. Save/Settings remain unconnected; Export to Falstad
opens the generated link for supported circuits.
Storage is independent of component rendering support.

The intended component scope is DC sources, resistors, wires, LEDs, diodes,
switches, buttons, photodiodes, capacitors, inductors, and potentiometers.
`examples/README.md` documents 11 educational circuits and the component input
parameters. Every example can be parsed, rendered, and stored; DC
steady-state simulation is available for all 11 examples. Switch/button symbols start from JSON
states and are read-only in the UI, mirroring the physical circuit.
New examples use `LED1` for LEDs and `L1` for inductors to avoid prefix conflicts;
the original example retains its older LED ID. Potentiometers introduce terminal
`"3"` for the wiper, supported in validation, drawing, and wire routing.

The prototype displays boxed voltage (`V:`) and current (`I:`) readouts,
with slightly rounded corners and a 2px border, outside the rectangular circuit
loop without a visible sample
label. Component IDs and nominal values are separate, close to their symbols
inside the loop, formatted as `R1 = 330 Ω` (rather than a dot separator).
Readouts now show actual signed DC results for supported circuits. Undetermined
quantities and unsupported circuits show `—`. Nominal labels come from JSON.
Resistance appears only as the resistor's nominal value, not in result boxes.
LED nominal labels use `L1: Vf = 2 V`. Result boxes are fed by `solve_dc()`.

## Initial MNA implementation

The original implementation covered examples 1–5: resistors,
DC voltage sources, LEDs, maintained switches, and momentary buttons. DC models for the remaining components have since been added below; transient
charging and current-ramp behavior are still outside scope. Unsupported types must produce an explicit unsupported-result
status, not be silently omitted.

Keep topology objects and Qt symbols separate from solver device classes.
Solver device classes expose branch-current allocation, equation stamping,
LED-state constraints, and voltage/current expressions. Share contact
behavior between switches/buttons; a button derives contact state from
`normally_closed` and `pressed`. Rendering coordinates never enter MNA.

`simulation/mna.py` selects the reference, allocates non-ground node
voltage indices and required branch-current unknowns, assembles A and b, solves
A x = b with NumPy, and returns structured per-node and
per-component results. Use V = V1 - V2 and positive current from terminal 1 to 2;
a supplying voltage source normally has negative current under this convention.
Do not invert A explicitly. Ground selection follows the rule above.

- Resistor: stamp conductance 1/R and derive current from its terminal voltage.
- DC source: add a current unknown and V1 - V2 = voltage_v constraint.
- Contact: open means zero current; closed means a zero-voltage constraint,
  with a branch-current unknown if current is to be displayed. Detect redundant
  ideal constraints rather than disguising a singular system.
- Optional fixed LED model: On:
  V1 - V2 = Vf and current >= 0. Off: current = 0 and V1 - V2 <= Vf.
  Check state consistency and convergence; do not treat every LED as an always-on
  voltage source. The default nonlinear model is described below.

Open contacts/off LEDs can leave some voltages undetermined (including the
released-button example). A chosen reference alone does not fix every floating
subnetwork. Report unavailable voltages explicitly; do not silently add leakage
resistance or arbitrary voltages. Any numerical regularization must be a
separate, documented modeling choice.

Test analytical expectations before UI integration: LED current approximately
9.8157 mA with exponential LEDs (9.09 mA in fixed mode) in example 1; 2.5 V divider midpoint in example 2; separate parallel
branch currents in example 3; open/closed states in example 4; pressed/released
behavior in example 5. Also test reversed LEDs, shorts, floating nodes, and
inconsistent ideal sources. Replace `—` in result boxes only with actual valid
results; changes to contact state require rebuilding/re-solving the system.

Reference available locally: `/Users/tonizeng/circuit-simulator/src/`.
The older Falstad code has per-device `stamp()`/`calculateCurrent()` methods,
a diode-specific nonlinear implementation, and shared switch/button behavior.
Use it as an architectural reference; a full port is not needed.

The fixed-drop path enumerates LED states (maximum 8 LEDs, 128 MNA
unknowns); it also supplies a starting estimate for the optional nonlinear solve. Full-rank systems use a direct linear solve. Singular systems use SVD
to identify free variables, and SciPy HiGHS linear programming checks feasible
LED inequalities and bounds each requested quantity. Only values unique across
all feasible states are displayed; the minimum-norm solution is not treated as
physical ground truth. This avoids undocumented leakage/regularization.
Numerical comparisons use finite tolerances (absolute 1e-9, relative 1e-7).

`SimulationResult` carries status (`solved`, `partial`, `inconsistent`, `invalid`,
`unsupported`, `empty`, `nonconverged`, or `numerical_error`), reference, node voltages, per-device
V/I/state, and a message. The UI solves automatically on load, displays status,
and leaves out-of-scope circuits renderable. Switches and buttons are read-only
in the schematic. This app is a digital twin: only updated topology data should
change electrical contact states. Hardware communication is not yet connected;
JSON reloads currently stand in for controller updates. Hover highlighting is
visual only. Falstad export uses the latest received contact state.
NumPy/SciPy are declared in requirements.txt. No Falstad solver code is copied.

Current presentation: result boxes display `abs(current_a)` while the solver
retains signed currents. Blue arrows (#2878b5) near component leads indicate actual
conventional current direction (1→2 for positive, 2→1 for negative). They rotate
with symbols, darken to #1b5a88 on hover, and are hidden for unknown or
effectively zero current (absolute value <= 1e-12 A). Voltage remains V1 − V2.

## Optional exponential LED model

`simulation/led_model.py` implements I = Is × (exp(V / a) − 1), with
`a = 2 × 0.025865 V` and `Is = 1 / (exp(forward_voltage_v / a) − 1)`.
This matches CircuitJS's `DiodeModel.getModelWithParameters` for our flag-1 LED
exports. In this optional mode, Vf is a calibration voltage at 1 A.
The default fixed-drop UI labels remain `Vf = …`.
There is no series resistance, reverse breakdown, or temperature variation.
This is not the named `default-led` model, which has different parameters.

`simulation/nonlinear.py` uses SciPy nonlinear least squares with an analytic
Jacobian to solve KCL, ideal source/contact constraints, and LED equations.
Exponential trial steps are protected against overflow; final residuals must
satisfy the exact equation. Failure produces no fabricated result. Converged
junction V/I constraints feed ambiguity analysis for remaining linear freedoms.
Physical exponential leakage can determine downstream open-contact voltages;
the old fixed-model rule that these are necessarily floating no longer applies.
The fixed model remains accessible through `solve_dc(circuit, led_model="fixed")`.
No physical controls are introduced; topology remains authoritative.

[Reference LED calibration](https://github.com/sharpie7/circuitjs1/blob/master/src/com/lushprojects/circuitjs1/client/DiodeModel.java)

## DC models for examples 6–12

The default fixed-drop solver supports all component types in the bundled examples:

| type | DC model |
| --- | --- |
| diode | constant forward drop when conducting, zero reverse current |
| wire | ideal zero-voltage constraint with a current unknown |
| capacitor | open circuit (I = 0) after settling |
| inductor | ideal zero-voltage constraint after settling |
| potentiometer | R13 = total R × position; R32 = total R × (1 − position) |
| photodiode | photocurrent source from cathode to anode, parallel forward diode |

Potentiometer positions 0 and 1 use an ideal contact for the zero-length track
segment, without division by zero. `ComponentResult.terminal_currents_a` provides
signed currents entering all three terminals. The result box's I is terminal-1
current; its V is the full track voltage, not wiper voltage. Wiper voltage is
available in `node_voltages`. Wire/inductor loops may have ambiguous individual
currents; those remain unavailable instead of being assigned arbitrarily.

Photodiode `photocurrent_a` is positive from cathode to anode, hence a negative
terminal-1-to-2 current when reverse biased. Its forward junction uses an optional
positive `forward_voltage_v`, default 0.7 V (a simplified software assumption).
No capacitance, dark leakage, or reverse breakdown is modeled.

Capacitor/inductor initial conditions are retained in JSON but do not affect
DC equilibrium. Status messages identify that transient behavior is not simulated.

Optional exponential LED mode currently rejects circuits also containing ordinary
diodes or photodiodes; use the default fixed mode for those combinations. Falstad
export remains limited to examples 1–5; this addition does not change export scope.
No schematic interaction can change physical component states.

Model references:
- [Photodiode equivalent circuit](https://wiki.analog.com/university/courses/electronics/text/light-sensors-photodiodes)

## Falstad export

Implemented in `falstad.py` for the types in examples 1–5: resistor, DC source,
LED, switch, and button in a single-source series/parallel network. The UI's
Export to Falstad button opens the encoded current circuit in the default
browser. No local MNA results are needed. CLI supports URL generation and
`--output PATH` text export; generated examples are under `artifacts/`.

Coordinates snap to an 8-pixel grid. Same-net wires are split at all taps,
overlapping segments are deduplicated, and ambiguous cross-net junctions are
rejected. Voltage-source endpoint order is reversed from our numbered terminal
convention. LED input uses CircuitJS's compatible explicit-forward-drop syntax.
Button export preserves current contact position and momentary behavior, but
does not encode separate pressed/released metadata. Other components/layouts
produce a clear unsupported message. Export tests verify connectivity, polarity,
parameters, contact flags, URL encoding, and UI dispatch; live browser execution
has not been automated.

### Investigation and future scope

Target the browser-based CircuitJS/Falstad, rather than the older Java applet
in the separate `circuit-simulator` folder. CircuitJS supports circuit text in
the URL's `cct` parameter, or LZ-String URI-compressed text in `ctz`. A text-file
export can be offered alongside opening a browser link. Export does not require
a local electrical solver; Falstad performs its own simulation.

Planned pipeline: validated Circuit + drawing plan → component terminal
coordinates and wire routes → CircuitJS text → file or encoded browser URL.
Component records contain a type code, endpoint coordinates, flags, and
component-specific parameters. Net IDs are not directly exported as our JSON:
connections must be reconstructed with shared post coordinates and wires.

- Use integer grid coordinates and split wires at intended junctions/taps.
  Prevent unrelated nets from acquiring coincident endpoints while converting
  routes; a visible crossing alone must not become a connection.
- Map terminals per component, not by assuming all CircuitJS endpoint orders
  match ours. Verify source polarity, diode orientation, and capacitor/inductor
  initial-state conventions against the target implementation.
- Export an explicit ground symbol on the selected reference net.
- Resistors, DC sources, wires, capacitors, inductors, diodes, LEDs, contacts,
  and potentiometers have corresponding CircuitJS elements. Momentary buttons
  use switch behavior; the potentiometer wiper's computed post needs adapting.
- The optional exponential LED model matches the explicit-Vf exports. Named Falstad LED
  models can differ and are not automatically matched by a single Vf input.
- Native photodiode support has not been confirmed in the inspected source.
  A diode plus a parallel photocurrent source is a possible approximation;
  this must be explicit to the user, not a silent substitution.
- Start by importing/exporting the resistor/LED example, verify connections and
  polarity in the browser, then cover all examples and test junction handling.

Sources inspected:

- [CircuitJS URL options](https://github.com/sharpie7/circuitjs1/blob/master/README.md)
- [Base element text format](https://github.com/sharpie7/circuitjs1/blob/master/src/com/lushprojects/circuitjs1/client/CircuitElm.java)
- [Voltage source format](https://github.com/sharpie7/circuitjs1/blob/master/src/com/lushprojects/circuitjs1/client/VoltageElm.java)
- [Diode models](https://github.com/sharpie7/circuitjs1/blob/master/src/com/lushprojects/circuitjs1/client/DiodeElm.java)
- [Potentiometer geometry and format](https://github.com/sharpie7/circuitjs1/blob/master/src/com/lushprojects/circuitjs1/client/PotElm.java)

## Button example initial state

Example 5 starts with `normally_closed: false` and `pressed: true`: the normally
open button is held down, so its contact is closed. This changes sample input,
not UI controls or hardware-state interpretation. Received topology remains
authoritative. The matching bundled database record and Falstad text are updated.
