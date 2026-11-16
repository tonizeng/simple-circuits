"""First-order RC timing; analytical step response, not transient simulation."""
from dataclasses import dataclass
import math
import numpy as np
from components import contact_closed


@dataclass(frozen=True)
class RCTiming:
    resistance_ohm: float
    capacitance_f: float

    @property
    def tau_s(self):
        return self.resistance_ohm * self.capacitance_f

    def response(self, time_s, initial_v, final_v):
        """Capacitor voltage and signed current into terminal 1 after a step."""
        if not all(math.isfinite(v) for v in (time_s, initial_v, final_v)) or time_s < 0:
            raise ValueError("Time must be nonnegative and all inputs finite.")
        decay = math.exp(-time_s / self.tau_s)
        return (final_v + (initial_v - final_v) * decay,
                (final_v - initial_v) / self.resistance_ohm * decay)

    def delay_s(self, fraction):
        """Time to complete a fraction of the change toward the final voltage."""
        if not math.isfinite(fraction) or not 0 <= fraction < 1:
            raise ValueError("Progress must be between 0 (inclusive) and 1 (exclusive).")
        return -self.tau_s * math.log1p(-fraction)

    def voltage_delay_s(self, initial_v, final_v, target_v):
        """Threshold-crossing time for charging or discharging."""
        if not all(math.isfinite(v) for v in (initial_v, final_v, target_v)):
            raise ValueError("Voltages must be finite.")
        if target_v == initial_v:
            return 0.0
        if final_v == initial_v:
            raise ValueError("The voltage does not change toward this threshold.")
        return self.delay_s((target_v - initial_v) / (final_v - initial_v))


def rc_timing(circuit, capacitor_id):
    """Find Thevenin resistance seen by a single capacitor with DC sources shorted.

    Returns (timing, reason). Nonlinear and multiple-storage circuits are excluded.
    Contacts retain their present topology; this does not predict future switching.
    """
    capacitors = [c for c in circuit.components if c.type == "capacitor"]
    if len(capacitors) != 1 or capacitors[0].id != capacitor_id:
        return None, "Timing requires a circuit with one capacitor."
    allowed = {"capacitor", "resistor", "photoresistor", "voltage_source", "wire", "switch", "button"}
    if any(c.type not in allowed for c in circuit.components):
        return None, "Timing is unavailable for this component network."
    nodes = circuit.terminal_nodes()
    parent = {n.id: n.id for n in circuit.nets}
    def find(n):
        while parent[n] != n:
            parent[n] = parent[parent[n]]
            n = parent[n]
        return n
    for c in circuit.components:
        if (c.id, "1") not in nodes or (c.id, "2") not in nodes:
            return None, "Connect all component terminals before calculating timing."
        if c.type in {"wire", "voltage_source"} or (c.type in {"switch", "button"} and contact_closed(c)):
            parent[find(nodes[c.id, "1"])] = find(nodes[c.id, "2"])
    cap = capacitors[0]
    a, b = (find(nodes[cap.id, t]) for t in ("1", "2"))
    if a == b:
        return None, "An ideal connection clamps the capacitor; no finite RC delay is modeled."
    edges = []
    adjacency = {find(n): set() for n in parent}
    for c in circuit.components:
        if c.type in ("resistor", "photoresistor"):
            x, y = (find(nodes[c.id, t]) for t in ("1", "2"))
            if x != y:
                edges.append((x, y, 1 / c.parameters["resistance_ohm"]))
                adjacency[x].add(y)
                adjacency[y].add(x)
    connected, pending = {a}, [a]
    while pending:
        for n in adjacency[pending.pop()] - connected:
            connected.add(n)
            pending.append(n)
    if b not in connected:
        return None, "No resistive charging or discharging path connects the capacitor terminals."
    indices = {n: i for i, n in enumerate(sorted(connected - {b}))}
    matrix = np.zeros((len(indices), len(indices)))
    rhs = np.zeros(len(indices))
    rhs[indices[a]] = 1.0
    for x, y, g in edges:
        if x not in connected:
            continue
        for n in (x, y):
            if n != b:
                matrix[indices[n], indices[n]] += g
        if x != b and y != b:
            matrix[indices[x], indices[y]] -= g
            matrix[indices[y], indices[x]] -= g
    try:
        resistance = float(np.linalg.solve(matrix, rhs)[indices[a]])
    except np.linalg.LinAlgError:
        return None, "The equivalent resistance cannot be determined."
    if not math.isfinite(resistance) or resistance <= 0:
        return None, "A finite positive equivalent resistance is required."
    return RCTiming(resistance, cap.parameters["capacitance_f"]), None


def rc_step_endpoints(circuit, capacitor_id, final_result):
    """Cache linear-network endpoints for preview without modifying DC safety results."""
    from dataclasses import replace
    from .mna import solve_dc
    cap = next(c for c in circuit.components if c.id == capacitor_id)
    replacement = replace(cap, type="voltage_source", parameters={"voltage_v": cap.parameters.get("initial_voltage_v", 0.0)})
    initial = solve_dc(replace(circuit, components=tuple(replacement if c.id == cap.id else c for c in circuit.components)))
    if initial.status != "solved":
        return None
    initial.components[cap.id] = replace(initial.components[cap.id], state="predicted RC response")
    # The constraint source current has the same terminal-1 reference as the capacitor.
    return initial, final_result


def rc_step_snapshot(timing, endpoints, time_s):
    """Interpolate all linear node voltages and branch currents with one RC mode."""
    from dataclasses import replace
    initial, final = endpoints
    decay = math.exp(-time_s / timing.tau_s)
    def interpolate(a, b):
        return None if a is None or b is None else b + (a - b) * decay
    components = {}
    for cid, result in final.components.items():
        start = initial.components[cid]
        components[cid] = replace(result, voltage_v=interpolate(start.voltage_v, result.voltage_v),
                                  current_a=interpolate(start.current_a, result.current_a),
                                  state=f"predicted {getattr(timing, 'kind', 'RC')} response" if result.state in ("dc open circuit", "dc zero voltage") else result.state)
    return replace(final, message=f"Predicted first-order {getattr(timing, 'kind', 'RC')} response", components=components,
                   node_voltages={nid: interpolate(initial.node_voltages.get(nid), v) for nid, v in final.node_voltages.items()})


def rc_response_phase(initial_v, final_v):
    """Charging/discharging for fixed-polarity steps; reversal is a transition."""
    if initial_v == final_v:
        return "steady"
    if initial_v * final_v < 0:
        return "transition"
    return "charging" if abs(final_v) > abs(initial_v) else "discharging"
