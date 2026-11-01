"""Electrical topology independent of Qt, symbol geometry, and solver indices."""

import json
import math
from dataclasses import dataclass
from components import (NUMERIC_PARAMETERS, BOOLEAN_PARAMETERS,
                        OPTIONAL_NUMERIC_PARAMETERS, terminal_ids)


class TopologyError(ValueError):
    """A controller message does not describe a supported, valid topology."""


@dataclass(frozen=True)
class Component:
    id: str
    type: str
    parameters: dict


@dataclass(frozen=True)
class Terminal:
    component_id: str
    terminal: str


@dataclass(frozen=True)
class Net:
    id: str
    terminals: tuple[Terminal, ...]


@dataclass(frozen=True)
class Circuit:
    name: str
    components: tuple[Component, ...]
    nets: tuple[Net, ...]
    ground_node: str | None

    def terminal_nodes(self):
        return {(t.component_id, t.terminal): net.id
                for net in self.nets for t in net.terminals}


def identifier(value, context):
    if not isinstance(value, str) or not value.strip():
        raise TopologyError(f"{context} must be a nonempty string.")
    return value


def parse_topology(data):
    """Accept a JSON string/bytes or dict and return a validated Circuit.

    Components have terminals '1' and '2'; potentiometers also have '3' (wiper).
    Unconnected terminals
    should appear in singleton nets; this preserves their electrical identity.
    No connectivity or electrical solvability is inferred from screen positions.
    """
    if isinstance(data, (str, bytes)):
        try:
            data = json.loads(data)
        except (ValueError, UnicodeDecodeError) as error:
            raise TopologyError(f"Invalid JSON: {error}") from error
    if not isinstance(data, dict):
        raise TopologyError("Topology must be a JSON object.")
    version = data.get("schema_version", 1)
    if type(version) is not int or version != 1:
        raise TopologyError("Only schema_version 1 is supported.")
    if not isinstance(data.get("components"), list) or not isinstance(data.get("nets"), list):
        raise TopologyError("components and nets must be arrays.")
    name = identifier(data.get("name", "Untitled circuit"), "Circuit name")
    components, component_ids, component_types = [], set(), {}
    for record in data["components"]:
        if not isinstance(record, dict):
            raise TopologyError("Each component must be an object.")
        cid = identifier(record.get("id"), "Component ID")
        if cid in component_ids:
            raise TopologyError(f"Duplicate component ID: {cid}.")
        kind = record.get("type")
        if not isinstance(kind, str) or kind not in NUMERIC_PARAMETERS:
            raise TopologyError(f"Unsupported component type for {cid}: {kind}.")
        params = record.get("parameters")
        if not isinstance(params, dict):
            raise TopologyError(f"{cid}: parameters must be an object.")
        numeric = dict(NUMERIC_PARAMETERS[kind])
        for key in OPTIONAL_NUMERIC_PARAMETERS.get(kind, ()):
            if key in params:
                numeric[key] = (None, None, False)
        for key, (minimum, maximum, exclusive) in numeric.items():
            value = params.get(key)
            if type(value) not in (int, float):
                raise TopologyError(f"{cid}: {key} must be a finite number.")
            try:
                finite = math.isfinite(value)
            except OverflowError:
                finite = False
            if (not finite or
                (minimum is not None and (value <= minimum if exclusive else value < minimum)) or
                (maximum is not None and value > maximum)):
                raise TopologyError(f"{cid}: invalid {key} value.")
        if kind == "photodiode" and "forward_voltage_v" in params:
            value = params["forward_voltage_v"]
            if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
                raise TopologyError(f"{cid}: forward_voltage_v must be positive and finite.")
        for key in BOOLEAN_PARAMETERS.get(kind, ()):
            if type(params.get(key)) is not bool:
                raise TopologyError(f"{cid}: {key} must be a boolean.")
        components.append(Component(cid, kind, dict(params)))
        component_ids.add(cid)
        component_types[cid] = kind
    nets, net_ids, used = [], set(), set()
    for record in data["nets"]:
        if not isinstance(record, dict):
            raise TopologyError("Each net must be an object.")
        nid = identifier(record.get("id"), "Net ID")
        if nid in net_ids:
            raise TopologyError(f"Duplicate net ID: {nid}.")
        refs = record.get("terminals")
        if not isinstance(refs, list) or not refs:
            raise TopologyError(f"{nid}: terminals must be a nonempty array.")
        terminals = []
        for ref in refs:
            if not isinstance(ref, dict):
                raise TopologyError(f"{nid}: each terminal reference must be an object.")
            cid = identifier(ref.get("component_id"), "Referenced component ID")
            tid = ref.get("terminal")
            if cid not in component_ids or tid not in terminal_ids(component_types[cid]):
                raise TopologyError(f"{nid}: unknown terminal {cid}.{tid}.")
            pair = (cid, tid)
            if pair in used:
                raise TopologyError(f"Terminal {cid}.{tid} appears more than once.")
            used.add(pair)
            terminals.append(Terminal(cid, tid))
        net_ids.add(nid)
        nets.append(Net(nid, tuple(terminals)))
    expected = {(cid, tid) for cid in component_ids for tid in terminal_ids(component_types[cid])}
    if expected != used:
        missing = ", ".join(f"{cid}.{tid}" for cid, tid in sorted(expected - used))
        raise TopologyError(f"Missing terminal connections: {missing}. Use singleton nets for open terminals.")
    ground = data.get("ground_node")
    if ground is not None:
        ground = identifier(ground, "ground_node")
        if ground not in net_ids:
            raise TopologyError("ground_node must reference an existing net.")
    return Circuit(name, tuple(components), tuple(nets), ground)
