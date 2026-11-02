"""Static formula text and SVG generation specifications; no runtime math dependency."""

# (asset name, math expression, accessible text). Generate assets with
# tools/generate_formulas.py; the desktop app only loads the saved SVGs.
FORMULA_EQUATIONS = {
    "Ohm’s law": (
        ("ohm_voltage", r"V = IR", "V = I times R"),
        ("ohm_current", r"I = \frac{V}{R}", "I = V divided by R"),
        ("ohm_resistance", r"R = \frac{V}{I}", "R = V divided by I"),
    ),
    "Electrical power": (
        ("power", r"P = VI", "P = V times I"),
        ("resistor_power", r"P = I^2R = \frac{V^2}{R}", "For resistors: P = I squared times R = V squared divided by R"),
    ),
    "Series resistors": (
        ("series_resistance", r"R_{\mathrm{eq}} = R_1 + R_2 + \cdots + R_n", "Equivalent series resistance = R1 + R2 + ... + Rn"),
    ),
    "Parallel resistors": (
        ("parallel_resistance", r"\frac{1}{R_{\mathrm{eq}}} = \frac{1}{R_1} + \frac{1}{R_2} + \cdots + \frac{1}{R_n}", "1 over equivalent resistance = 1 over R1 + 1 over R2 + ... + 1 over Rn"),
        ("parallel_pair", r"R_{\mathrm{eq}} = \frac{R_1R_2}{R_1 + R_2}", "For two parallel resistors: equivalent resistance = R1 times R2 divided by R1 + R2"),
    ),
    "Kirchhoff’s laws": (
        ("current_law", r"\sum_k I_k = 0", "Kirchhoff current law: sum of signed node currents equals zero"),
        ("voltage_law", r"\sum_k V_k = 0", "Kirchhoff voltage law: sum of signed loop voltage changes equals zero"),
    ),
    "Voltage divider": (
        ("voltage_divider", r"V_{\mathrm{out}} = V_{\mathrm{in}}\,\frac{R_2}{R_1+R_2}", "Output voltage = input voltage times R2 divided by R1 + R2"),
    ),
    "LED resistor sizing": (
        ("led_resistance", r"R = \frac{V_s - V_f}{I}", "Resistance = supply voltage minus LED forward voltage, divided by current"),
    ),
    "Capacitors": (
        ("capacitor_charge", r"Q = CV", "Charge = capacitance times voltage"),
        ("capacitor_current", r"I = C\,\frac{dV}{dt}", "Current = capacitance times rate of voltage change"),
        ("capacitor_voltage", r"V(t) = V_0 + \frac{1}{C}\int_0^t I(\tau)\,d\tau", "Voltage at t = initial voltage + integral of current from zero to t divided by capacitance"),
    ),
    "Inductors": (
        ("inductor_voltage", r"V = L\,\frac{dI}{dt}", "Voltage = inductance times rate of current change"),
        ("inductor_current", r"I(t) = I_0 + \frac{1}{L}\int_0^t V(\tau)\,d\tau", "Current at t = initial current + integral of voltage from zero to t divided by inductance"),
    ),
}

FORMULA_CAPTIONS = {
    "resistor_power": "For resistors:",
    "parallel_resistance": "For n resistors:",
    "parallel_pair": "For 2 resistors:",
}

FORMULA_TOPICS = (
    ('Ohm’s law', '<p>V: voltage (V)<br>I: current (A)<br>R: resistance (Ω)</p><p><b>When to use</b><br>Find a resistor’s voltage, current, or resistance when the other two are known. Division requires a nonzero denominator.</p>'),
    ('Electrical power', '<p>P: power (W)<br>V: voltage (V)<br>I: current (A)<br>R: resistance (Ω)</p><p><b>When to use</b><br>Estimate energy transfer per second or resistor power dissipation. With current defined into the positive-voltage terminal, positive P means absorbed power; negative P means supplied power.</p>'),
    ('Series resistors', '<p>All resistance values are in ohms (Ω).</p><p><b>When to use</b><br>Combine resistors carrying the same current in one path, with no branch at their joining nodes.</p>'),
    ('Parallel resistors', '<p>All resistance values are in ohms (Ω).</p><p><b>When to use</b><br>Combine resistors connected across the same two nodes. They share the same voltage.</p>'),
    ('Kirchhoff’s laws', '<p>Current law: total current entering a node equals total current leaving it.</p><p>Voltage law: signed voltage changes around a closed loop sum to zero.</p><p>I: current (A)<br>V: voltage (V)<br>Σ: sum of the signed quantities</p><p><b>When to use</b><br>Relate branches or loop voltages when the circuit cannot be reduced to one simple series or parallel combination. Choose directions and polarities consistently.</p>'),
    ('Voltage divider', '<p>V<sub>in</sub>, V<sub>out</sub>: volts (V)<br>R₁, R₂: ohms (Ω)</p><p><b>When to use</b><br>Two series resistors span the input voltage; take the output across R₂. The formula assumes no load current is drawn from their junction.</p><p>For a potentiometer, R₁ is the resistance from terminal 1 to wiper 3; R₂ is from wiper 3 to terminal 2.</p>'),
    ('LED resistor sizing', '<p>R: series resistance (Ω)<br>V<sub>s</sub>: supply voltage (V)<br>V<sub>f</sub>: LED forward drop (V)<br>I: desired LED current (A)</p><p><b>When to use</b><br>Estimate a current-limiting resistor for a single forward-biased LED, using a fixed forward-drop approximation. This assumes V<sub>s</sub> &gt; V<sub>f</sub> and a positive desired current. Check resistor power and component ratings separately.</p>'),
    ('Capacitors', '<p>Q: charge (C)<br>C: capacitance (F)<br>V: voltage (V)<br>I: current (A)<br>t: time (s)<br>V₀: initial voltage at t = 0<br>τ: integration time variable (s)</p><p><b>When to use</b><br>Relate stored charge to voltage, current to the rate of voltage change, or voltage to accumulated current. Current is defined into the positive-voltage terminal.</p><p>At DC steady state, dV/dt = 0, so an ideal capacitor carries no current and acts as an open circuit. The app currently calculates this steady state, not charging waveforms.</p>'),
    ('Inductors', '<p>V: voltage (V)<br>L: inductance (H)<br>I: current (A)<br>t: time (s)<br>I₀: initial current at t = 0<br>τ: integration time variable (s)</p><p><b>When to use</b><br>Relate inductor voltage to the rate of current change, or current to accumulated voltage. Current is defined into the positive-voltage terminal.</p><p>At DC steady state, dI/dt = 0, so an ideal inductor has zero voltage and acts as a short circuit. The app currently calculates this steady state, not current-ramp waveforms.</p>'),
)
