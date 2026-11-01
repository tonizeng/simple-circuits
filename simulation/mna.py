"""Small-circuit DC MNA with ideal contacts and selectable LED behavior.

The default LED model is the introductory fixed-drop model below. The optional
Falstad-compatible exponential model is delegated to nonlinear.py.
Singular systems are analyzed, not regularized: only uniquely determined
quantities are returned. LP bounds distinguish genuine results from arbitrary
least-squares choices for floating nodes or redundant ideal branch currents.
"""

from dataclasses import dataclass, field
from itertools import product

import numpy as np
from scipy.optimize import linprog
from components import contact_closed

from .devices import DEVICE_TYPES


MAX_LEDS = 8
MAX_UNKNOWNS = 128
ATOL = 1e-9
RTOL = 1e-7


@dataclass(frozen=True)
class ComponentResult:
    voltage_v: float | None
    current_a: float | None
    state: str | None = None


@dataclass
class SimulationResult:
    status: str
    message: str
    ground_node: str | None = None
    node_voltages: dict = field(default_factory=dict)
    components: dict = field(default_factory=dict)


class MNA:
    def __init__(self, circuit, ground, devices):
        self.node_indices = {net.id: index for index, net in enumerate(
            net for net in circuit.nets if net.id != ground)}
        branches = [d.id for d in devices if d.needs_branch_current]
        self.branch_indices = {cid: len(self.node_indices) + index
                               for index, cid in enumerate(branches)}
        self.size = len(self.node_indices) + len(branches)
        self.matrix = np.zeros((self.size, self.size))
        self.rhs = np.zeros(self.size)

    def zero(self):
        return np.zeros(self.size)

    def difference(self, a, b):
        vector = self.zero()
        if a in self.node_indices:
            vector[self.node_indices[a]] += 1
        if b in self.node_indices:
            vector[self.node_indices[b]] -= 1
        return vector

    def branch_current(self, cid):
        vector = self.zero()
        vector[self.branch_indices[cid]] = 1
        return vector

    def conductance(self, a, b, value):
        incidence = self.difference(a, b)
        self.matrix += value * np.outer(incidence, incidence)

    def voltage_constraint(self, cid, a, b, value):
        index = self.branch_indices[cid]
        incidence = self.difference(a, b)
        self.matrix[:, index] += incidence
        self.matrix[index, :] += incidence
        self.rhs[index] = value


class NumericalError(RuntimeError):
    pass


class OperatingRegion:
    """All feasible solutions for one assignment of LED on/off states."""

    def __init__(self, particular, nullspace, inequalities, limits):
        self.particular = particular
        self.nullspace = nullspace
        self.inequalities = inequalities
        self.limits = limits

    def optimize(self, objective):
        return linprog(objective, A_ub=self.inequalities, b_ub=self.limits,
                       bounds=[(None, None)] * len(objective), method="highs",
                       options={"primal_feasibility_tolerance": 1e-9,
                                "dual_feasibility_tolerance": 1e-9})

    def range(self, coefficients):
        base = float(coefficients @ self.particular)
        objective = coefficients @ self.nullspace
        if not len(objective) or np.max(np.abs(objective)) < 1e-12:
            return base, base
        low, high = self.optimize(objective), self.optimize(-objective)
        if low.status not in (0, 3) or high.status not in (0, 3):
            raise NumericalError("Could not determine whether a circuit quantity is unique.")
        return (float("-inf") if low.status == 3 else base + low.fun,
                float("inf") if high.status == 3 else base - high.fun)


def operating_region(system, inequalities):
    if system.size == 0:
        particular, nullspace = np.zeros(0), np.zeros((0, 0))
    else:
        # Normalize equations without adding artificial leakage or constraints.
        scale = np.max(np.abs(system.matrix), axis=1)
        scale[scale == 0] = 1
        matrix, rhs = system.matrix / scale[:, None], system.rhs / scale
        _, singular, vh = np.linalg.svd(matrix, full_matrices=True)
        cutoff = max(matrix.shape) * np.finfo(float).eps * (singular[0] if len(singular) else 1)
        rank = int(np.sum(singular > cutoff))
        if rank == system.size and matrix.shape[0] == matrix.shape[1]:
            particular = np.linalg.solve(matrix, rhs)
        else:
            particular = np.linalg.lstsq(matrix, rhs, rcond=max(matrix.shape) * np.finfo(float).eps)[0]
        if not np.allclose(matrix @ particular, rhs, atol=ATOL, rtol=RTOL):
            return None  # Inconsistent ideal voltage constraints/KCL.
        nullspace = vh[rank:].T
    if inequalities:
        coefficients = np.array([row for row, _ in inequalities])
        bounds = np.array([bound for _, bound in inequalities])
        reduced = coefficients @ nullspace
        limits = bounds - coefficients @ particular
        # Remove invariant inequalities after checking them; normalize others.
        keep = []
        for index, row in enumerate(reduced):
            magnitude = np.max(np.abs(row)) if len(row) else 0
            if magnitude < 1e-12:
                if limits[index] < -ATOL:
                    return None
            else:
                keep.append(index)
        if keep:
            reduced, limits = reduced[keep], limits[keep]
            row_scale = np.max(np.abs(reduced), axis=1)
            reduced, limits = reduced / row_scale[:, None], limits / row_scale
        else:
            reduced, limits = None, None
    else:
        reduced, limits = None, None
    region = OperatingRegion(particular, nullspace, reduced, limits)
    if nullspace.shape[1]:
        feasibility = region.optimize(np.zeros(nullspace.shape[1]))
        if feasibility.status == 2:
            return None
        if not feasibility.success:
            raise NumericalError("LED-state feasibility could not be established.")
    return region


def unique_value(ranges):
    low, high = min(a for a, _ in ranges), max(b for _, b in ranges)
    if not np.isfinite(low) or not np.isfinite(high) or not np.isclose(low, high, atol=ATOL, rtol=RTOL):
        return None
    value = (low + high) / 2
    return 0.0 if abs(value) < 1e-12 else float(value)


def solve_dc(circuit, led_model="fixed"):
    """Solve a parsed Circuit. Signed V/I are from terminal 1 toward terminal 2.

    Unsupported circuits return a status, never silently drop devices. The
    original topology is not mutated by reference selection or LED states.
    led_model='falstad' matches the explicit-Vf Falstad export; 'fixed' preserves
    the introductory constant-drop model for comparison.
    """
    if led_model not in ("falstad", "fixed"):
        raise ValueError("led_model must be 'falstad' or 'fixed'.")
    if led_model == "falstad" and any(c.type == "led" for c in circuit.components):
        from .nonlinear import solve_led_dc
        return solve_led_dc(circuit)
    unsupported = sorted({c.type for c in circuit.components} - DEVICE_TYPES.keys())
    if unsupported:
        return SimulationResult("unsupported", "DC simulation not supported for: " + ", ".join(unsupported))
    if not circuit.components:
        return SimulationResult("empty", "No circuit loaded.")
    ground = circuit.ground_node
    if ground is None:
        sources = [c for c in circuit.components if c.type == "voltage_source"]
        if len(sources) != 1:
            return SimulationResult("invalid", "Choose an explicit ground_node unless there is exactly one DC source.")
        ground = circuit.terminal_nodes()[(sources[0].id, "2")]
    leds = [c.id for c in circuit.components if c.type == "led"]
    if len(leds) > MAX_LEDS:
        return SimulationResult("unsupported", f"Initial solver supports at most {MAX_LEDS} LEDs.", ground)
    nodes = circuit.terminal_nodes()
    ranges = {("node", net.id): [] for net in circuit.nets}
    for c in circuit.components:
        ranges[("voltage", c.id)], ranges[("current", c.id)] = [], []
    feasible = 0
    try:
        for states in product((False, True), repeat=len(leds)):
            active = dict(zip(leds, states))
            devices = [DEVICE_TYPES[c.type](c, nodes, active.get(c.id, False)) for c in circuit.components]
            system = MNA(circuit, ground, devices)
            if system.size > MAX_UNKNOWNS:
                return SimulationResult("unsupported", f"Initial solver supports at most {MAX_UNKNOWNS} unknowns.", ground)
            for device in devices:
                device.stamp(system)
            inequalities = [entry for device in devices for entry in device.inequalities(system)]
            region = operating_region(system, inequalities)
            if region is None:
                continue
            feasible += 1
            for net in circuit.nets:
                ranges[("node", net.id)].append(region.range(system.difference(net.id, ground)))
            for device in devices:
                ranges[("voltage", device.id)].append(region.range(device.voltage(system)))
                ranges[("current", device.id)].append(region.range(device.current(system)))
    except (np.linalg.LinAlgError, NumericalError, FloatingPointError) as error:
        return SimulationResult("numerical_error", f"Numerical solve failed: {error}", ground)
    if not feasible:
        return SimulationResult("inconsistent", "No valid DC operating point: check shorts, ideal sources, and LED constraints.", ground)
    values = {key: unique_value(bounds) for key, bounds in ranges.items()}
    node_voltages = {net.id: values[("node", net.id)] for net in circuit.nets}
    results = {}
    for c in circuit.components:
        voltage, current = values[("voltage", c.id)], values[("current", c.id)]
        state = None
        if c.type == "led":
            state = "unknown" if current is None else ("on" if current > ATOL else "off")
        elif c.type in ("switch", "button"):
            state = "closed" if contact_closed(c) else "open"
        results[c.id] = ComponentResult(voltage, current, state)
    partial = any(value is None for value in values.values())
    message = ("DC solved partially: floating voltages or ideal-branch currents are not uniquely determined (—)."
               if partial else "DC operating point solved.")
    return SimulationResult("partial" if partial else "solved", message, ground, node_voltages, results)
