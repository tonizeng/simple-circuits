"""Nonlinear DC LED solve with residual validation and explicit ambiguity."""

import numpy as np
from scipy.optimize import least_squares
from components import contact_closed
from .devices import DEVICE_TYPES
from .led_model import FalstadLEDModel
from .mna import (MNA, MAX_UNKNOWNS, ComponentResult, SimulationResult,
                  NumericalError, operating_region, unique_value, solve_dc)


def solve_led_dc(circuit):
    # Fixed-drop results provide a starting estimate, never the final answer.
    seed = solve_dc(circuit, led_model="fixed")
    if seed.status in ("unsupported", "invalid", "empty", "numerical_error"):
        return seed
    if any(c.type in ("diode", "photodiode") for c in circuit.components):
        return SimulationResult("unsupported", "Optional exponential LED mode currently excludes other diode types; use fixed mode.")
    ground, nodes = seed.ground_node, circuit.terminal_nodes()
    devices = [DEVICE_TYPES[c.type](c, nodes, c.type == "led") for c in circuit.components]
    system = MNA(circuit, ground, devices)
    if system.size > MAX_UNKNOWNS:
        return SimulationResult("unsupported", f"Initial solver supports at most {MAX_UNKNOWNS} unknowns.", ground)
    for device in devices:
        device.stamp(system)
    leds = [d for d in devices if d.component.type == "led"]
    try:
        models = {d.id: FalstadLEDModel(d.component.parameters["forward_voltage_v"]) for d in leds}
    except ValueError as error:
        return SimulationResult("numerical_error", str(error), ground)
    matrix, rhs = system.matrix.copy(), system.rhs.copy()
    for device in leds:
        row = system.branch_indices[device.id]
        matrix[row, :], rhs[row] = 0, 0
    initial = system.zero()
    for node, index in system.node_indices.items():
        initial[index] = seed.node_voltages.get(node) or 0
    for cid, index in system.branch_indices.items():
        result = seed.components.get(cid)
        initial[index] = (result.current_a or 0) if result else 0
    scales = np.ones(system.size)
    scales[:len(system.node_indices)] = .01
    for device in leds:
        scales[system.branch_indices[device.id]] = .01

    def residual(solution, exact=False):
        values = matrix @ solution - rhs
        for device in leds:
            row = system.branch_indices[device.id]
            voltage = float(device.voltage(system) @ solution)
            current = (models[device.id].exact_current(voltage) if exact
                       else models[device.id].evaluate(voltage)[0])
            values[row] = solution[row] - current
        return values

    def jacobian(solution):
        jac = matrix.copy()
        for device in leds:
            row = system.branch_indices[device.id]
            voltage = float(device.voltage(system) @ solution)
            slope = models[device.id].evaluate(voltage)[1]
            jac[row, :] = -slope * device.voltage(system)
            jac[row, row] = 1
        return jac / scales[:, None]

    try:
        fitted = least_squares(lambda x: residual(x) / scales, initial, jac=jacobian,
                               x_scale="jac", ftol=1e-12, xtol=1e-12, gtol=1e-12, max_nfev=500)
        errors = residual(fitted.x, exact=True)
        if not fitted.success or not np.all(np.isfinite(fitted.x)) or np.max(np.abs(errors / scales)) > 1e-8:
            return SimulationResult("nonconverged", "LED solve did not converge to a validated DC operating point.", ground)
        # Strictly monotone junctions fix their V/I; analyze any remaining linear
        # freedoms without mistaking tiny reverse conductance for a disconnection.
        extra_rows, extra_rhs = [], []
        for device in leds:
            row = system.branch_indices[device.id]
            voltage = float(device.voltage(system) @ fitted.x)
            system.rhs[row] = voltage
            extra_rows.append(system.branch_current(device.id))
            extra_rhs.append(models[device.id].exact_current(voltage))
        system.matrix = np.vstack((system.matrix, extra_rows))
        system.rhs = np.concatenate((system.rhs, extra_rhs))
        region = operating_region(system, [])
        if region is None:
            raise NumericalError("LED solution did not satisfy circuit constraints.")
        value = lambda coefficients: unique_value([region.range(coefficients)])
        node_values = {net.id: value(system.difference(net.id, ground)) for net in circuit.nets}
        results = {}
        for device in devices:
            voltage, current = value(device.voltage(system)), value(device.current(system))
            state = None
            if device.component.type == "led":
                state = "on" if current is not None and current > 1e-9 else "off"
            elif device.component.type in ("switch", "button"):
                state = "closed" if contact_closed(device.component) else "open"
            results[device.id] = ComponentResult(voltage, current, state)
        partial = any(v is None for v in node_values.values()) or any(
            r.voltage_v is None or r.current_a is None for r in results.values())
        message = ("DC solved with Falstad-compatible exponential LEDs; some quantities are undetermined (—)."
                   if partial else "DC solved with Falstad-compatible exponential LEDs.")
        return SimulationResult("partial" if partial else "solved", message, ground, node_values, results)
    except (ValueError, OverflowError, FloatingPointError, np.linalg.LinAlgError, NumericalError) as error:
        return SimulationResult("numerical_error", f"Nonlinear LED solve failed: {error}", ground)
