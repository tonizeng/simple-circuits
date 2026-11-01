"""Shockley model matching CircuitJS's flag-1 explicit-Vf LED imports.

Reference: DiodeModel.getModelWithParameters in
https://github.com/sharpie7/circuitjs1/blob/master/src/com/lushprojects/circuitjs1/client/DiodeModel.java
This is not CircuitJS's named default-led model, which has different parameters.
"""

import math

SCALE_VOLTAGE = 2 * 0.025865  # Emission coefficient 2, thermal voltage at 300.15 K.


class FalstadLEDModel:
    def __init__(self, forward_voltage):
        ratio = forward_voltage / SCALE_VOLTAGE
        if not 0 < ratio < 650:
            raise ValueError("LED forward voltage is outside the supported numerical range.")
        self.saturation_current = 1 / math.expm1(ratio)
        self.log_saturation_current = math.log(self.saturation_current)

    def evaluate(self, voltage):
        """I and dI/dV; tangent continuation prevents trial-step overflow."""
        exponent = voltage / SCALE_VOLTAGE + self.log_saturation_current
        if exponent > 40:
            e = math.exp(40)
            return (e * (1 + exponent - 40) - self.saturation_current,
                    e / SCALE_VOLTAGE)
        return (math.exp(exponent) - self.saturation_current,
                math.exp(exponent) / SCALE_VOLTAGE)

    def exact_current(self, voltage):
        return math.exp(voltage / SCALE_VOLTAGE + self.log_saturation_current) - self.saturation_current
