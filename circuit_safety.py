"""Conservative DC pre-power checks. Passing is not a hardware safety guarantee."""
from dataclasses import dataclass
import math
from components import contact_closed
from simulation import solve_dc


def is_finite_number(value):
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


@dataclass(frozen=True)
class SafetyLimits:
    max_voltage_v: float = 3.3
    max_current_a: float = 1.5

    def __post_init__(self):
        for value in (self.max_voltage_v, self.max_current_a):
            if not is_finite_number(value) or value <= 0:
                raise ValueError("Safety limits must be positive finite numbers.")


@dataclass(frozen=True)
class SafetyIssue:
    code: str
    message: str
    component_ids: tuple = ()
    severity: str = "error"
    terminal_refs: tuple = ()


@dataclass(frozen=True)
class SafetyReport:
    issues: tuple
    predicted_supply_current_a: float | None = None

    @property
    def allowed(self):
        return not self.issues


def component_rating_values(component, result, simulation, nodes):
    """Return absolute current, voltage, and power; include all three pot terminals."""
    if result is None:
        return None, None, None
    current = abs(result.current_a) if result.current_a is not None else None
    voltage = abs(result.voltage_v) if result.voltage_v is not None else None
    power = abs(result.voltage_v * result.current_a) if current is not None and voltage is not None else None
    if component.type == 'potentiometer':
        currents = result.terminal_currents_a or {}
        voltages = [simulation.node_voltages.get(nodes[(component.id, tid)]) for tid in ('1', '2', '3')]
        if len(currents) != 3 or any(value is None for value in currents.values()):
            return None, None, None
        current = max(abs(value) for value in currents.values())
        if any(value is None for value in voltages):
            return current, None, None
        # Sum power at each terminal using the wiper as the reference.
        v1, v2, v3 = voltages
        voltage = max(voltages) - min(voltages)
        power = abs((v1 - v3) * currents['1'] + (v2 - v3) * currents['2'])
    return current, voltage, power

def assess_circuit(circuit, limits=SafetyLimits(), simulation=None):
    """Check topology and modeled supply demand; do not energize or alter a circuit."""
    issues = []
    sources = [c for c in circuit.components if c.type == 'voltage_source']
    if len(sources) != 1:
        issues.append(SafetyIssue('source_count', 'Connect exactly one voltage source before enabling power.'))
    nodes = circuit.terminal_nodes()
    parents = {net.id: net.id for net in circuit.nets}

    def find(node):
        if parents[node] != node:
            parents[node] = find(parents[node])
        return parents[node]

    # Inductors are ideal shorts at DC. Capacitors are not treated as wires.
    ideal_edges = []
    for component in circuit.components:
        if (component.type in ('wire', 'inductor') or
            component.type in ('switch', 'button') and contact_closed(component) or
            component.type == 'potentiometer' and component.parameters['wiper_position'] in (0, 1)):
            a = '1'
            b = '2'
            if component.type == 'potentiometer':
                a, b = ('1', '3') if component.parameters['wiper_position'] == 0 else ('3', '2')
            first, second = nodes[(component.id, a)], nodes[(component.id, b)]
            parents[find(first)] = find(second)
            ideal_edges.append((component.id, first, second))
    for source in sources:
        voltage = source.parameters['voltage_v']
        if abs(voltage) > limits.max_voltage_v:
            issues.append(SafetyIssue('overvoltage',
                f'{source.id}: {voltage:g} V exceeds the {limits.max_voltage_v:g} V maximum.', (source.id,)))
        start, end = nodes[(source.id, '1')], nodes[(source.id, '2')]
        if find(start) == find(end):
            paths, pending = {start: ()}, [start]
            while pending and end not in paths:
                node = pending.pop(0)
                for cid, a, b in ideal_edges:
                    neighbor = b if a == node else a if b == node else None
                    if neighbor is not None and neighbor not in paths:
                        paths[neighbor] = paths[node] + (cid,)
                        pending.append(neighbor)
            affected = (source.id,) + paths.get(end, ())
            issues.append(SafetyIssue('supply_short',
                f'{source.id}: supply terminals are shorted through ideal connections.', affected))
    for net in circuit.nets:
        if len(net.terminals) == 1:
            ref = net.terminals[0]
            component = next(c for c in circuit.components if c.id == ref.component_id)
            if component.type == 'potentiometer' and ref.terminal == '3':
                continue
            issues.append(SafetyIssue('unconnected_terminal',
                f'{net.id}: {ref.component_id} terminal {ref.terminal} is unconnected.', (ref.component_id,), severity='warning', terminal_refs=((ref.component_id, ref.terminal),)))
    # Assessment is limited to settled DC; startup and turn-off are not checked.
    simulation = simulation if simulation is not None else solve_dc(circuit)
    if simulation.status != 'solved' and not (
            simulation.status == 'inconsistent' and any(i.code == 'supply_short' for i in issues)):
        messages = {
            'partial': 'Values cannot be fully determined. Check for disconnected components.',
            'inconsistent': 'The circuit has conflicting connections or source values.',
            'invalid': 'The circuit needs a valid voltage reference and power source.',
            'unsupported': 'This circuit cannot be checked with the supported component models.',
            'empty': 'Add components and connections before requesting power.',
        }
        message = messages.get(simulation.status,
            'The circuit could not be checked. Review its connections and component values.')
        issues.append(SafetyIssue('unresolved_circuit', message,
                                 severity='warning' if simulation.status == 'partial' else 'error'))
    predicted = None
    if len(sources) == 1:
        result = simulation.components.get(sources[0].id)
        current = result.current_a if result is not None else None
        if current is not None and math.isfinite(current):
            predicted = abs(current)
            if predicted > limits.max_current_a:
                issues.append(SafetyIssue('predicted_overcurrent',
                    f'Predicted supply current {predicted:g} A exceeds {limits.max_current_a:g} A.', (sources[0].id,)))
        elif not any(i.code == 'unresolved_circuit' for i in issues):
            issues.append(SafetyIssue('unknown_current', 'Supply current cannot be determined.'))
    # Optional component-specific ratings; no generic LED/resistor rating is assumed.
    for component in circuit.components:
        result = simulation.components.get(component.id)
        current, voltage, power = component_rating_values(component, result, simulation, nodes)
        for field, actual, unit in (
            ('max_current_a', current, 'A'),
            ('max_voltage_v', voltage, 'V'),
            ('max_power_w', power, 'W'),
        ):
            if field not in component.parameters:
                continue
            rating = component.parameters[field]
            if not is_finite_number(rating) or rating <= 0:
                issues.append(SafetyIssue('invalid_rating', f'{component.id}: invalid {field} rating.', (component.id,)))
            elif actual is None or not math.isfinite(actual):
                issues.append(SafetyIssue('unknown_rating_check', f'{component.id}: cannot verify {field}.', (component.id,)))
            elif actual > rating:
                issues.append(SafetyIssue('component_rating_exceeded',
                    f'{component.id}: predicted {actual:g} {unit} exceeds its {rating:g} {unit} rating.', (component.id,)))
    return SafetyReport(tuple(issues), predicted)
