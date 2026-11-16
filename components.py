"""Shared component definitions for input validation and presentation (no solver)."""

COMPONENT_NAMES = {
    "voltage_source": "DC Source", "resistor": "Resistor", "wire": "Wire",
    "led": "LED", "diode": "Diode", "switch": "Switch", "button": "Button",
    "photoresistor": "Photoresistor", "capacitor": "Capacitor", "inductor": "Inductor",
    "potentiometer": "Potentiometer",
}

COMPONENT_DESCRIPTIONS = {
    "voltage_source": "Maintains a fixed voltage between its positive and negative terminals.",
    "resistor": "Limits current and creates a voltage drop according to Ohm’s law.",
    "wire": "Connects terminals so they share the same electrical potential in the ideal model.",
    "led": "Emits light when forward biased and carrying current.",
    "diode": "Conducts primarily in one direction and blocks current in the reverse direction under normal conditions.",
    "switch": "Opens or closes an electrical connection.",
    "button": "Changes a connection while pressed, then returns to its normal state when released.",
    "photoresistor": "Resistance decreases as light increases. The circuit model uses the supplied resistance value.",
    "capacitor": "Stores and releases electrical energy, smoothing changes in voltage. Resistors are often used to limit charging current and control charging or discharging time.",
    "inductor": "Stores energy in a magnetic field and opposes changes in current.",
    "potentiometer": "Provides an adjustable resistance using a movable wiper along a resistive track.",
}

# Required numeric fields and ranges: (minimum, maximum, minimum_is_exclusive).
NUMERIC_PARAMETERS = {
    "voltage_source": {"voltage_v": (None, None, False)},
    "resistor": {"resistance_ohm": (0, None, True)},
    "wire": {}, "switch": {}, "button": {},
    "led": {"forward_voltage_v": (0, None, True)},
    "diode": {"forward_voltage_v": (0, None, True)},
    "photoresistor": {"resistance_ohm": (0, None, True)},
    "capacitor": {"capacitance_f": (0, None, True)},
    "inductor": {"inductance_h": (0, None, True)},
    "potentiometer": {"resistance_ohm": (0, None, True), "wiper_position": (0, 1, False)},
}

BOOLEAN_PARAMETERS = {"switch": ("closed",), "button": ("normally_closed", "pressed")}
OPTIONAL_NUMERIC_PARAMETERS = {
    "capacitor": ("initial_voltage_v",), "inductor": ("initial_current_a",),
}


def terminal_ids(kind):
    return ("1", "2", "3") if kind == "potentiometer" else ("1", "2")


def contact_closed(component):
    params = component.parameters
    if component.type == "button":
        return params["normally_closed"] != params["pressed"]
    return params["closed"]


def engineering(value, unit):
    for scale, prefix in ((1e6, "M"), (1e3, "k"), (1, ""),
                          (1e-3, "m"), (1e-6, "µ"), (1e-9, "n"), (1e-12, "p")):
        if abs(value) >= scale:
            return f"{value / scale:.4g} {prefix}{unit}"
    return f"{value:.4g} {unit}"


def current_reading(value, mode="arrows"):
    """Format solver current without changing its terminal-1-to-2 reference."""
    if value is None:
        return "—"
    if mode == "signed":
        return ("+" if value > 0 else "") + engineering(value, "A")
    return engineering(abs(value), "A")


def nominal_label(component):
    cid, kind, p = component.id, component.type, component.parameters
    fields = {"resistor": ("resistance_ohm", "Ω"),
              "voltage_source": ("voltage_v", "V"),
              "capacitor": ("capacitance_f", "F"), "inductor": ("inductance_h", "H")}
    if kind in fields:
        field, unit = fields[kind]
        return f"{cid} = {engineering(p[field], unit)}"
    if kind in ("led", "diode"):
        return f"{cid}: Vf = {engineering(p['forward_voltage_v'], 'V')}"
    if kind == "photoresistor":
        return f"{cid} = {engineering(p['resistance_ohm'], 'Ω')}"
    if kind in ("switch", "button"):
        return f"{cid}: {'Closed' if contact_closed(component) else 'Open'}"
    if kind == "potentiometer":
        return f"{cid} = {engineering(p['resistance_ohm'], 'Ω')}\nWiper: {p['wiper_position']:.0%}"
    return f"{cid}: Ideal wire"
