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

Series circuit: 3.3 V source → 330 Ω resistor → LED → source negative.
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
      "parameters": { "voltage_v": 3.3 }
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
The fixed-drop LED model gives `(3.3 - 2) / 330 ≈ 3.94 mA` in example 1.
These are model predictions, not measured results.

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
The DC LED model is fixed-drop on/off.
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
overwritten by browsing. Save remains unconnected; Export to Falstad
opens the generated link for supported circuits.
Storage is independent of component rendering support.

The intended component scope is DC sources, resistors, wires, LEDs, diodes,
switches, buttons, photoresistors, capacitors, inductors, and potentiometers.
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
- Fixed LED model: On:
  V1 - V2 = Vf and current >= 0. Off: current = 0 and V1 - V2 <= Vf.
  Check state consistency and convergence; do not treat every LED as an always-on
  voltage source.

Open contacts/off LEDs can leave some voltages undetermined (including the
released-button example). A chosen reference alone does not fix every floating
subnetwork. Report unavailable voltages explicitly; do not silently add leakage
resistance or arbitrary voltages. Any numerical regularization must be a
separate, documented modeling choice.

Test analytical expectations before UI integration: LED current approximately
3.94 mA with fixed-drop LEDs in example 1; 1.65 V divider midpoint in example 2; separate parallel
branch currents in example 3; open/closed states in example 4; pressed/released
behavior in example 5. Also test reversed LEDs, shorts, floating nodes, and
inconsistent ideal sources. Replace `—` in result boxes only with actual valid
results; changes to contact state require rebuilding/re-solving the system.

Reference available locally: `/Users/tonizeng/circuit-simulator/src/`.
The older Falstad code has per-device `stamp()`/`calculateCurrent()` methods,
a diode-specific nonlinear implementation, and shared switch/button behavior.
Use it as an architectural reference; a full port is not needed.

The fixed-drop path enumerates LED states (maximum 8 LEDs, 128 MNA
unknowns). Full-rank systems use a direct linear solve. Singular systems use SVD
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
retains signed currents. Arrows (#2878b5) near component leads indicate actual
conventional current direction (1→2 for positive, 2→1 for negative). They rotate
with symbols, darken to #1b5a88 on hover, and are hidden for unknown or
effectively zero current (absolute value <= 1e-12 A). Voltage remains V1 − V2.

## DC models for examples 6–12

The default fixed-drop solver supports all component types in the bundled examples:

| type | DC model |
| --- | --- |
| diode | constant forward drop when conducting, zero reverse current |
| wire | ideal zero-voltage constraint with a current unknown |
| capacitor | open circuit (I = 0) after settling |
| inductor | ideal zero-voltage constraint after settling |
| potentiometer | R13 = total R × position; R32 = total R × (1 − position) |
| photoresistor | supplied resistance, using the same electrical model as a resistor |

Potentiometer positions 0 and 1 use an ideal contact for the zero-length track
segment, without division by zero. `ComponentResult.terminal_currents_a` provides
signed currents entering all three terminals. The result box's I is terminal-1
current; its V is the full track voltage, not wiper voltage. Wiper voltage is
available in `node_voltages`. Wire/inductor loops may have ambiguous individual
currents; those remain unavailable instead of being assigned arbitrarily.

Photoresistors use the supplied positive `resistance_ohm`, modeled with Ohm’s law.
No light-to-resistance conversion is inferred.

Capacitor/inductor initial conditions are retained in JSON but do not affect
DC equilibrium. Status messages identify that transient behavior is not simulated.

Falstad export supports all current component types (see the export section below).
No schematic interaction can change physical component states.

Model references:

## Falstad export

Implemented in `falstad.py` for every current component type: resistor, DC source,
LED, diode, switch, button, wire, capacitor, inductor, potentiometer, and photoresistor.
All 11 bundled examples export. Layout still requires a single-source
series/parallel network; potentiometer wipers must currently be unloaded. The UI's
Export to Falstad button opens the encoded current circuit in the default
browser. No local MNA results are needed. CLI supports URL generation and
`--output PATH` text export; generated examples are under `artifacts/`.

Coordinates snap to an 8-pixel grid. Same-net wires are split at all taps,
overlapping segments are deduplicated, and ambiguous cross-net junctions are
rejected. Voltage-source endpoint order is reversed from our numbered terminal
convention. LED input uses CircuitJS's compatible explicit-forward-drop syntax.
Button export preserves current contact position and momentary behavior, but
does not encode separate pressed/released metadata. Unsupported layouts
produce a clear error instead of changing connectivity.

Capacitors export capacitance and initial voltage (including the reset value);
inductors export inductance and initial current. Missing initial conditions default
to zero. Explicit wires remain ideal wires. Diodes use the backward-compatible
explicit-forward-drop record, with terminal 1 as anode and terminal 2 as cathode.
Potentiometers export as two resistors with a shared wiper: R(1–3) = R × position
and R(3–2) = R × (1 − position). At exact endpoints the zero-ohm section is a wire.
This preserves the requested position without a quantized interactive slider.
Photoresistors export as ordinary resistors at their supplied resistance; light changes are not simulated in the export.
Falstad runs nonlinear/transient models independently; numerical results can differ
from the local fixed-drop DC equilibrium calculation. Export tests verify connectivity, polarity,
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
- Falstad LED results may differ from local fixed-drop predictions.
- Photoresistors export their present resistance, without an interactive light model.
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

## Highlight colour settings

The header gear opens colour settings for components (including value glow),
connected nodes, and current arrows. Save applies and persists these preferences
using Qt QSettings; Cancel discards edits, and Restore defaults resets the choices
in the popup. Component value text stays black. This changes presentation only.

## Incomplete circuit layout

Open series/parallel examples retain a rectangular ladder layout. The renderer
tries temporary rail assignments for dangling terminals to determine component
positions, then draws their actual nets separately with a 20px gap to the rail.
These assignments are drawing hints only: input topology, ground, and simulation
results are not changed. This fallback requires one source and handles up to six
dangling endpoints; other disconnected networks retain the generic net-lane layout.

## Formula reference

The Formulas sidebar tab uses expandable reference sections with equations, SI
units, and short usage notes. Content is in `formula_reference.py`; it does not
perform calculations or provide worked circuit solutions. Capacitor/inductor
time-dependent equations are educational references, not transient solver support.

Formula equations are pre-generated SVG paths using STIX math typography in
`assets/formulas/`. `tools/generate_formulas.py` regenerates them using the optional
`requirements-dev.txt` dependencies. The desktop renders SVGs with Qt, without
importing Matplotlib or requiring a LaTeX installation. Accessible text accompanies
each equation; explanations keep the application font.

## Pre-power validation and fault protection

Hardware ceilings supplied by the project: **3.3 V maximum and 1.5 A maximum**.
The battery is nominally 3.3 V and fluctuates. Fresh measured upstream battery
voltage replaces the source value in the analysis copy, without changing the
stored nominal topology. A measured voltage above 3.3 V denies authorization;
if 3.3 V is later defined as nominal rather than an absolute ceiling, the maximum
must be revised using the actual hardware specification.

`circuit_safety.py` checks a validated Circuit before power authorization:
- Exactly one DC source, source voltage ceiling, and determined DC solution.
- Supply shorts through nets, ideal wires, closed switches/buttons, inductors at
  DC, or a potentiometer’s zero-resistance endpoint.
- Unconnected terminals (an unloaded potentiometer wiper is allowed).
- Predicted absolute supply current against 1.5 A.
- Optional per-component parameters `max_current_a`, `max_voltage_v`, and
  `max_power_w`. Unspecified ratings are not guessed or certified by these checks.
- Assess settled DC conditions only for now: capacitors are open circuits and
  inductors are ideal shorts. Their presence alone does not block approval.
  Startup/inrush and turn-off behaviour are outside these checks; firmware/hardware
  must provide live current monitoring and fault protection.

`power_protection.py` now replies to **board-initiated enable requests**:
1. The physical board enable button triggers a request for validation.
2. The desktop checks the latest board topology, fresh battery/load-current
   measurements, and the 3.3 V / 1.5 A ceilings.
3. It returns a PowerDecision with the matching request ID and topology revision,
   approval/denial, reasons, and the required maximum voltage/current.
4. Firmware applies its local current limit and enables the load only if it accepts
   a matching, timely, one-use approval. A denial or no reply must leave power off.
5. Firmware/hardware independently performs automatic fault shutdown, current
   limiting, fault latching/reset, and communication-loss handling. The desktop
   sends no power-on/off, current-limit, or fault-reset commands.

Desktop decisions do not assert the physical power state. No power buttons or
Safety details button appear in the desktop. Instead, a draggable floating panel inside the schematic
shows orange/red **Error!** and yellow **Warning!** cards with grey message bodies.
Shorts, invalid data, and exceeded limits are errors. Unconnected terminals,
and partially determined solutions are warnings.
Both severities currently deny power; warnings indicate incomplete validation,
not permission to energize an uncertain circuit. Open paths identify component
IDs, terminal numbers, and net IDs; physical board coordinates are not yet known.
The panel appears automatically when issues are found. Drag a coloured Error/Warning header to
move the cards within the schematic viewport; it does not resize the schematic or open
a separate window. It stays within the viewport when the app resizes, retains its
position while dragging, resets to the top-left for new alerts or circuit loads,
and disappears when issues resolve. Card height grows with the text; there are
no internal scrollbars. Only the cards
are visible; there is no extra title block or white container.
There is no Close button to dismiss before interacting with the schematic.

Future firmware adapter entry points in CircuitWindow (call on the UI thread):
- `attach_power_transport(sender)`: sender accepts a PowerDecision response.
  Attaching emits no command and requires a new board snapshot and measurements.
- `receive_hardware_topology(data, revision)`: increasing nonnegative revision
  per device connection. Library/sample loads have no hardware revision and can
  never authorize the board. Invalid or outdated data denies requests while
  preserving the previous drawing.
- `receive_supply_measurement(voltage_v, current_a)`: fresh upstream battery voltage
  and load-output current, in SI units. Do not replay cached telemetry as new data.
  The default freshness window is 1 second and remains to be agreed with firmware.
- `handle_enable_request(request_id, topology_revision)`: explicitly revalidates and
  responds only to this request. Missing, stale, duplicate, mismatched, or unsafe
  requests are denied. Decisions never automatically enable or restart anything.
- `receive_firmware_fault(message)`: show a board-reported fault; None reports that
  firmware has cleared it. Desktop controls cannot reset the board fault.
- `disconnect_power_transport()`: discard connection context and deny requests.

The serial adapter and wire format remain pending. Firmware must bind requests,
topology revisions, and replies to its current device session, impose its own
response deadline, and consume each approval once. Changing connections/values
invalidates any prior approval. The app neither guarantees shutdown timing nor
confirms physical cutoff: firmware must protect the circuit even if USB or the app
fails. A 1.5 A supply limit alone does not protect lower-rated components.
All bundled sources, including the root and incomplete examples, use 3.3 V.
Library migration updates exact unmodified legacy 5 V records; custom records
are preserved. Falstad text exports match the 3.3 V examples.
Hardware enforcement is not integrated or hardware-tested yet.

### Locating diagnostic issues

Affected components show a red circular error badge or amber triangular warning
badge, separate from hover/pinned highlight colours. Hovering the badge shows its
messages; the error/warning cards remain visible with the same explanations.
Open paths use a warning badge at the affected terminal, without an extra open-
connection glyph. Supply-short detection identifies a path through ideal
connections, marking the source and components on that path. Global issues without
an identified component remain in the message cards rather than marking an
arbitrary part. Badges are rebuilt from the current circuit's validation report.

### Results during validation issues

If any error or warning is active, every schematic result box displays V: — and
I: — and current arrows are hidden. Nominal component labels remain available.
The solver may still calculate internal values for short/overcurrent validation,
but partial or faulted results are not presented as usable circuit results.
Validation cards use plain-language messages instead of raw solver status text.


### Component inspector

The right inspector uses one shared component selection from the schematic or
Detected Components. Its help icon opens the preserved, expandable How to read
topics without replacing the inspector. The compact identity header uses the
existing vector symbols. Electrical properties are read-only; source voltage is
labelled nominal, and solver results are labelled calculated. Any validation issue
suppresses calculated values and worked examples, while nominal properties remain.
Purpose and Related formulas are collapsible; variable definitions are nested and
collapsed by default. Formulas use the existing SVG assets. Worked examples use
available signed solver values only. Source delivered power is `-V * I` under the
solver's current-into-terminal-1 convention; formula examples instead explicitly
define source current as leaving the positive terminal. No transient example or
three-terminal potentiometer total power is inferred from a single branch current.


Inspector equations now follow each component's intrinsic model under
**Equations & behaviour**, without a generic power-formula fallback. Resistors
show Ohm's law; sources their voltage constraint; diodes/LEDs the fixed-drop
conducting/blocking rules; contacts their open/closed rules; wires zero drop;
potentiometers both track-segment resistances; and photoresistors Ohm’s law. Capacitor/inductor equations remain educational and explicitly
distinguish transient relationships from the settled-DC solver. Equation SVGs and
their container use transparent backgrounds. Circuit-specific divider/LED-sizing
formulas are not inferred for arbitrary selected components.


### Circuit overview and status placement

The left sidebar now contains Connectivity, Circuit Upload, and Circuit Status.
Validation error/warning/success cards are embedded in Circuit Status, with an
error/warning count; they no longer float over the schematic or drag independently.
Long messages grow within the existing sidebar scroll region. Schematic fault
badges remain visible. The right inspector's unselected state is Circuit overview,
with component/node counts and expandable selection lists. Component selections
reuse the same detected-component rows; node selections show node details. Clearing
a selection returns to this overview. Counts and lists come from the loaded topology,
not firmware connection/upload telemetry, which remains unintegrated.


Circuit Status now appears first in the left sidebar as one white rounded card.
Its compact headline is Checks passed, Review required, or Errors detected, with
Power approved / Power not approved beneath it. Error rows precede warning rows;
severity uses restrained red/amber icons and left-edge accents. Clicking a located
issue opens its component/node details and reveals the fault marker. Existing
schematic warning/error badges remain in place. Approval text describes desktop
validation, not confirmation that firmware has enabled physical power.


### Circuit Library page

Circuit Library is now a scrollable workspace page rather than a modal browser.
SQLite-backed cards show a renderer-generated preview, circuit name, component/node
counts, and Open circuit. Bundled examples retain filename order, including error
and incomplete diagnostics; existing saved records are preserved. Opening a card
loads the circuit and returns to Circuit. My Circuits remains a placeholder.
The inspector no longer shows an Equations section; electrical properties and
Purpose remain. Formula reference assets are retained for possible future use.


### Circuit Guide

The header's Guide button, beside Save Schematic, opens a reusable non-modal
Circuit Guide window from every page. Reading the schematic covers terminals,
nodes, voltage signs, current direction, ground, selection, fault symbols,
unavailable results, approval, settled DC, and display controls. Terminology defines
the core circuit and value labels. Guidance does not edit circuits or enable power.


### Current display modes

Settings offers Arrows + magnitude (default) or Signed current. The choice is
persisted in `display/current`. Both modes use the same solver results. Signed
mode hides current-direction arrows and displays positive/negative current using
terminal 1 → 2 as its reference, in both schematic readouts and component details.
Voltage remains signed in either mode. Unavailable results remain dashes. The
Guide explains both presentations; changing presentation does not change topology,
contact states, approval, or electrical calculations.


### Schematic grid

The canvas draws optional scene-aligned grid lines, panning/zooming with the
schematic. Major spacing is 20 scene units with 10-unit subdivisions for terminal
geometry (including potentiometer wipers). Drawing placements and planned wire
bends snap to these subdivisions without changing electrical topology or solver
inputs; disconnected wire gaps are retained. Settings → Show schematic grid
controls visibility and persists it in `display/grid`. Zoom controls and the
legend use subtle drop shadows and remain fixed to the viewport.


The schematic toolbar now includes a checkable Pan hand tool for left-button
dragging; middle-button panning remains available. Panning expands view bounds so
it works even when the circuit fits, without modifying scene geometry or solver
inputs. Disable Pan to resume component/node selection. The active navigation page
uses its existing white fill and a thin purple outline; the left-edge bar is gone.


### First-order RC timing

`simulation/rc.py` calculates the Thevenin resistance seen across a single capacitor,
with independent DC voltage sources replaced by ideal shorts. Resistor series and
parallel networks, wires, and current switch/button states are supported. The
capacitor inspector displays equivalent resistance, τ = R_th C, time to complete
90% and 99% of a voltage change, and approximate settling at 5τ (99.3%).

Delay uses t = −τ ln(1 − f), where f is progress toward the final voltage. The
`voltage_delay_s(initial_v, final_v, target_v)` API also supports a specific charging
or discharging threshold; unreachable thresholds and the exact asymptotic final
voltage are rejected. The UI currently shows percentage delays, not an editable
voltage threshold. Initial/final voltages must correspond to the actual step event.

This is analytical step-response timing, not a time-domain simulation or startup
protection. Multiple capacitors, inductors, nonlinear devices, ideal clamps, and
missing resistive paths return an unavailable explanation. Timing values are hidden
when the existing safety checks suppress calculated results. No firmware behavior,
physical switching, or safety approval rules are changed.


### Photoresistors (LDRs)

Photoresistors replace photodiodes. Use type `photoresistor`, ID such as `LDR1`,
and positive `resistance_ohm`. Both terminals are non-polarized. The supplied
resistance is used in DC MNA, safety analysis, RC timing, and Falstad export.
No illumination level or ON/OFF state is fabricated. Example 10 is a 3.3 V
voltage divider with a 10 kΩ fixed resistor and a 10 kΩ photoresistor.


### Predicted RC response

The capacitor inspector plots V(t) = Vf + (Vi − Vf) exp(−t/τ) and signed
I(t) = (Vf − Vi)/R_th exp(−t/τ), from 0 to 5τ. A slider updates both plot
markers and numerical values. Vi uses initial_voltage_v (explicitly labeled
assumed zero when omitted); Vf is the solved DC capacitor voltage. Assumptions:
instantaneous step, constant linear resistance, fixed contacts. This is an
analytical prediction, not measured data or live simulation. Schematic DC values
and safety approval remain unchanged. Unsupported RC networks or suppressed
results do not display a fabricated response. No new dependencies are required.


### Schematic RC time control

For supported, safety-check-passing first-order RC circuits, a toolbar at the
bottom of the schematic exposes a 0–5τ slider without requiring component
selection. Moving it previews all component and node voltages, branch currents,
and arrows using cached initial/final linear-network solutions. The initial
solution constrains the capacitor to its specified initial voltage (zero if
omitted); interpolation follows exp(−t/τ). This changes display data only, never
the settled DC safety result or physical circuit. Settled DC restores normal
readings. Loading a circuit resets the preview; warnings/errors suppress it.
Inspector plots follow the main slider and omit their duplicate slider. The
preview is a fixed-topology analytical step response, not hardware measurements
or transient fault protection.


RC timing is presented as a 1τ–5τ table: elapsed seconds and percentage of
the total voltage transition completed, 100(1−exp(−n)). These percentages also
apply to discharge progress; they are not the percentage of charge remaining.


### Inductor protection: deferred

Turn-off protection checks are deferred pending the hardware design. The software
does not verify flyback diodes/clamps or calculate turn-off voltage spikes. This
does not change settled-DC short detection through ideal inductors, supply limits,
or existing optional rating checks.

Example 13 adds a series RLC topology (3.3 V, 10 Ω, 10 mH, 100 µF). The main
solver and safety checks remain settled DC; the analytical series-RLC preview
now supports its changing voltage/current response. No inductor turn-off warning
is emitted; hardware protection has not been verified by the software.


### First-order RL preview

`simulation/rl.py` supports one inductor in a fixed linear resistor/photoresistor,
DC source, wire/contact network, with no capacitors or nonlinear devices.
Source-suppressed equivalent resistance gives τ = L/R_eq. Inductor current follows
I(t) = If + (Ii − If) exp(−t/τ), and voltage is R_eq(If − Ii) exp(−t/τ).
Initial current comes from `initial_current_a` (zero if omitted). Final current
comes from the settled DC solve. A cached initial voltage-constraint solve supplies
all initial branch/node values; exponential interpolation updates the entire
schematic without changing the stored DC safety result.

The schematic's 0–5τ slider supports RC or RL and remains discoverable without
selecting a component. Inductors show RL Timing (1τ–5τ table) and Predicted RL
Response plots, following the same chevron style and selected time. The Settled DC
button restores equilibrium readings. RLC/multiple storage, nonlinear networks,
zero or missing resistive paths are not previewed. No flyback protection check or
physical switching is added; this is an analytical fixed-topology prediction only.


### Analytical series RLC preview

`simulation/rlc.py` recognizes a single closed series loop containing one DC
voltage source, one capacitor, one inductor, positive total resistance, and optional
wires/closed contacts. Branches, open contacts, nonlinear devices, multiple
storage elements of the same type, and disconnected subcircuits are rejected.
Resistance is summed along the actual series path. Terminal orientation and any
selected ground reference are preserved. Initial Vc and IL use JSON values, or
zero when omitted. The fixed supply is applied as an ideal step.

Exact exponential/sinusoidal solutions cover underdamped, critically damped and
overdamped regimes (alpha = R/(2L), omega0 = 1/sqrt(LC)). Current, all branch
voltages and all net voltages follow KVL/KCL. Reversed current and capacitor
overshoot are supported. The preview is separate from the settled DC result used
for safety approval; it does not validate transient protection or component ratings.

The schematic slider uses a finite preview window in seconds, not a universal
RLC tau or charging percentage. It spans eight slow decay times, capped at ten
oscillation periods for very lightly damped responses. It is not a guaranteed
settling time. Capacitor and inductor inspectors show damping type/ratio,
oscillation frequency when applicable, and synchronized voltage/current graphs.
First-order RC/RL tables remain limited to first-order circuits. Arbitrary RLC
networks and switching events are not simulated. No new dependencies are needed.


### LED model simplification

The optional Falstad-compatible exponential LED model, its nonlinear solver, and
associated tests have been removed. `solve_dc(circuit)` uses only the fixed-drop
LED/diode model. LED input and normal UI behavior are unchanged. Falstad export
remains available and runs independently in the external simulator.


### New Circuit workspace

The header New Circuit button creates a blank in-memory workspace named Untitled N
and returns to the Circuit page. It clears rendered results, selected items,
transient previews and prior approval, without deleting saved records or sending
firmware commands. The blank workspace waits for topology; it is not an invalid
electrical circuit, and Save is available even for empty circuits; Export requires topology.

Before replacing a nonempty unsaved circuit, the app offers Save/Discard/Cancel.
Save persists the workspace and creates a blank one only after a successful save.
Cancel retains the current workspace. A document
identical to its saved database record needs no prompt; selection, zoom and
preview time do not count as edits. This is the first workspace action only; the
board-upload choice between new/existing circuits is not wired to firmware yet.

Blank workspaces can be renamed through the pencil dialog or Enter in the title.
The name is retained in memory until the header Save button persists it. Empty
circuits can be saved; Export remains disabled until topology is loaded. Blank names are rejected,
and Cancel leaves the current title unchanged.


### Rename and explicit Save

The pencil dialog and Enter in the title rename only the active workspace,
including its in-memory document. They never write to SQLite. Header Save persists
the current title and topology; empty components/nets are valid saved workspaces.
Reopening an empty record shows the waiting state, hides Circuit Overview and
does not grant power or report an invalid electrical circuit. Library thumbnails
label such records Empty circuit. A loaded saved record keeps its original storage
identity until Save atomically renames that record; duplicate names never silently
overwrite another circuit. Unsaved rename/topology changes trigger Save/Discard/
Cancel before New Circuit. Display-only changes do not.


The header circuit title is now read-only, uses an arrow cursor and takes no
keyboard focus. Only the pencil opens the editable Rename dialog. Renaming still
changes memory only; the header Save button persists the workspace.


### My Circuits and default Circuit Library

Circuit Library reads only bundled JSON files under examples/ (including diagnostic
subfolders), in filename order. Browsing or opening examples never seeds or writes
SQLite. Opening an example establishes a clean baseline without a personal-record
identity. Header Save creates/updates a user-owned record in My Circuits, including
empty circuits and copies of examples. Bundled examples are never modified by Save.

My Circuits is a separate scrollable page, using generated schematic previews and
Open circuit controls. Empty records show Empty circuit and reopen as waiting
workspaces. Rename stays in memory until Save, which updates the user's record
atomically. Different user records with the same name cannot silently overwrite
one another. A personal circuit may share a bundled example's display name.

SQLite origin metadata distinguishes user records from legacy imported examples.
On upgrading an old schema, exact bundled/recognized legacy stock documents are
marked example and hidden from My Circuits; customized records remain user. No
records are deleted by classification. Previously saved exact stock copies are
indistinguishable from auto-imports in the old schema; Save explicitly promotes a
copy to user origin. New saves always have user origin.


## Reference build preview

- Both My Circuits and Circuit Library offer **Build This Circuit**; viewing a saved circuit also offers a compact **Build Circuit** action beside its mode label. Exiting reference mode returns to viewing that saved circuit.
- A compact label below the circuit title shows **Building from Scratch**, **Viewing Saved Circuit**, or **Building from Reference**. The full comparison banner appears only during reference building. No live/connected state is claimed without firmware.
- Uploads are initiated by the physical board button, not an app check/upload button. Firmware integration is pending; the internal comparison entry point can be exercised in tests with JSON snapshots. Comparison never replaces the reference, writes a save, or grants power.
- Comparison ignores circuit/component/node names and layout; checks required nominal parameters, contact states, connections and polarized-terminal orientation. Nonpolar two-terminal components may be reversed.
- This is bounded structural matching, not general electrical equivalence: explicit wires must be represented consistently. Additional series wires or equivalent resistor substitutions are not reduced. Ambiguous/large searches may return **Comparison Inconclusive**.
- Only component count/type/value/state and generic connection/polarity differences are reported for now; exact missing-wire localization and a separate detected-circuit view remain future work.
- Future firmware integration must check a fresh, revision-bound detected snapshot. Matching a reference is separate from safety approval and physical power enablement.


### Reference-mode approval rule

- Circuit Status shows **Safety Checks** first and **Build Comparison** below it only during reference building.
- Reference-mode power approval requires both passing safety checks on the uploaded circuit and a structural match for that exact board topology revision. Pending, differing, inconclusive, invalid or stale comparisons deny approval.
- Snapshot comparisons invoked without a board revision cannot authorize firmware. A new topology, reconnect, reference change or exit invalidates previous approval.
- The reference schematic remains unchanged; safety checks and comparison use the detected snapshot. Detected faults are not highlighted on the reference schematic.
- Scratch mode retains safety-only approval. Firmware remains responsible for physical power enablement and shutdown; serial integration is still pending.


## Save workflow

- Save opens a naming dialog; Cancel leaves the workspace and database unchanged. Pencil renaming stays in memory until Save.
- New/empty circuits save new personal records. While viewing a Circuit Library example, Save is disabled and Save As creates a personal copy. Library example files are never overwritten.
- The header has separate **Save** and **Save As…** actions. Save writes the current name immediately, including the first save of an Untitled circuit; it never opens a naming dialog. Use the pencil to rename, then Save. Errors remain in the workspace without a dialog. Save As always opens a name dialog and creates a separate record. Naming dialogs have only Save and Cancel.
- In reference mode, Save is disabled. Save As always targets the uploaded build as a new personal circuit, never the displayed reference. Before an upload exists, Save As explains that a board upload is required and saves nothing. An unsaved uploaded snapshot prompts before New Circuit.
- Names must be nonempty and contain no control characters; existing personal names cannot be used for a new record. Save as New enforces this again inside the SQLite transaction.
- Database write failure keeps the dialog/workspace intact and offers Retry Save or Cancel. Success refreshes My Circuits and displays confirmation.
- Saving is independent of safety approval: incomplete or unsafe circuit drafts can still be stored, without granting power.

- Save As validates names as the user types against cached personal names: empty, control-character and duplicate names disable Save and show an inline message. An available name clears the message and enables Save. SQLite rechecks uniqueness transactionally at the final write.
