"""Bounded topology comparison for rebuilding a saved reference; no power control."""
from collections import Counter
from dataclasses import dataclass
from math import isclose
from components import NUMERIC_PARAMETERS, BOOLEAN_PARAMETERS, terminal_ids, COMPONENT_NAMES
from topology import parse_topology

@dataclass(frozen=True)
class BuildComparison:
    status: str
    messages: tuple[str, ...]


def compare_build(reference, detected, search_limit=50000):
    """Ignore IDs/net names, allow reversal of nonpolar two-terminal components.

    This is structural matching, not general equivalent-circuit reduction. Explicit
    wires must be present in both; ratings, layout and initial conditions are ignored.
    A search limit returns inconclusive, never a false mismatch.
    """
    ref, got = parse_topology(reference), parse_topology(detected)
    differences = []
    expected, actual = Counter(c.type for c in ref.components), Counter(c.type for c in got.components)
    for kind in sorted(expected.keys() | actual.keys()):
        delta = expected[kind] - actual[kind]
        if delta:
            differences.append(f"{'Missing' if delta > 0 else 'Extra'} {abs(delta)} × {COMPONENT_NAMES[kind]}.")
    if differences:
        return BuildComparison('different', tuple(differences))
    if not ref.components:
        return BuildComparison('inconclusive', ('Choose a reference with components first.',))

    def same_value(a, b):
        if a.type != b.type:
            return False
        keys = tuple(NUMERIC_PARAMETERS[a.type]) + tuple(BOOLEAN_PARAMETERS.get(a.type, ()))
        return all(isclose(a.parameters[k], b.parameters[k], rel_tol=1e-9, abs_tol=1e-15)
                   if type(a.parameters[k]) in (int, float) else a.parameters[k] == b.parameters[k]
                   for k in keys)

    candidates = {c.id: [d for d in got.components if same_value(c, d)] for c in ref.components}
    if any(not candidates[c.id] for c in ref.components):
        for c in ref.components:
            if not candidates[c.id]:
                differences.append(f"{c.id}: no {COMPONENT_NAMES[c.type]} with matching nominal values and state was detected.")
        return BuildComparison('different', tuple(differences))
    ordered = sorted(ref.components, key=lambda c: len(candidates[c.id]))
    rn, dn = ref.terminal_nodes(), got.terminal_nodes()
    symmetric = {'resistor', 'wire', 'switch', 'button', 'photoresistor', 'inductor'}
    attempts = 0

    def visit(index, used, mapping, reverse):
        nonlocal attempts
        if index == len(ordered):
            return True
        component = ordered[index]
        pins = terminal_ids(component.type)
        for target in candidates[component.id]:
            if target.id in used:
                continue
            orientations = (pins, tuple(reversed(pins))) if component.type in symmetric else (pins,)
            for target_pins in orientations:
                attempts += 1
                if attempts > search_limit:
                    raise OverflowError
                forward, backward = dict(mapping), dict(reverse)
                for pin, target_pin in zip(pins, target_pins):
                    r, d = rn.get((component.id, pin), (component.id, pin)), dn.get((target.id, target_pin), (target.id, target_pin))
                    if (r in forward and forward[r] != d) or (d in backward and backward[d] != r):
                        break
                    forward[r], backward[d] = d, r
                else:
                    if visit(index + 1, used | {target.id}, forward, backward):
                        return True
        return False
    try:
        matches = visit(0, set(), {}, {})
    except (OverflowError, RecursionError):
        return BuildComparison('inconclusive', ('This circuit needs a more detailed comparison; no match has been confirmed.',))
    if matches:
        return BuildComparison('matched', ('Component types, nominal values, states and terminal connections match the reference.',))
    return BuildComparison('different', ('Connections, polarity, or the combination of component values/states differ from the reference. Check the wiring and polarized terminals.',))
