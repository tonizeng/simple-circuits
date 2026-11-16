"""Analytical first-order RL response for fixed linear circuit topologies."""
from dataclasses import dataclass, replace
import math
from .rc import rc_timing
from .mna import solve_dc


@dataclass(frozen=True)
class RLTiming:
    resistance_ohm: float
    inductance_h: float
    kind = "RL"
    storage_quantity = 1

    @property
    def tau_s(self):
        return self.inductance_h / self.resistance_ohm

    def response(self, time_s, initial_a, final_a):
        """Return V(1)-V(2) and signed inductor current after a step."""
        if not all(math.isfinite(v) for v in (time_s, initial_a, final_a)) or time_s < 0:
            raise ValueError("Time must be nonnegative and all inputs finite.")
        decay = math.exp(-time_s / self.tau_s)
        return (self.resistance_ohm * (final_a - initial_a) * decay,
                final_a + (initial_a - final_a) * decay)


def rl_timing(circuit, inductor_id):
    inductors = [c for c in circuit.components if c.type == "inductor"]
    if len(inductors) != 1 or inductors[0].id != inductor_id or any(c.type == "capacitor" for c in circuit.components):
        return None, "RL timing requires one inductor and no capacitors."
    inductor = inductors[0]
    # The same source-suppressed resistance network is used by RC and RL.
    probe = replace(inductor, type="capacitor", parameters={"capacitance_f": 1.0})
    resistance, reason = rc_timing(replace(circuit, components=tuple(probe if c.id == inductor_id else c for c in circuit.components)), inductor_id)
    if resistance is None:
        return None, "RL timing unavailable: " + reason.replace("capacitor", "inductor").replace("RC", "RL")
    return RLTiming(resistance.resistance_ohm, inductor.parameters["inductance_h"]), None


def rl_step_endpoints(circuit, inductor_id, timing, final_result):
    inductor = next(c for c in circuit.components if c.id == inductor_id)
    final_current = final_result.components[inductor_id].current_a
    if final_current is None:
        return None
    initial_current = inductor.parameters.get("initial_current_a", 0.0)
    initial_voltage = timing.resistance_ohm * (final_current - initial_current)
    constraint = replace(inductor, type="voltage_source", parameters={"voltage_v": initial_voltage})
    initial = solve_dc(replace(circuit, components=tuple(constraint if c.id == inductor_id else c for c in circuit.components)))
    if initial.status != "solved":
        return None
    result = initial.components[inductor_id]
    if result.current_a is None or not math.isclose(result.current_a, initial_current, rel_tol=1e-7, abs_tol=1e-9):
        return None
    return initial, final_result
