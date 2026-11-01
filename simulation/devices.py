"""DC device equations, independent of Qt and schematic geometry."""

from components import contact_closed


class Device:
    def __init__(self, component, nodes, active=False):
        self.component = component
        self.id = component.id
        self.a = nodes[(self.id, "1")]
        self.b = nodes[(self.id, "2")]
        self.active = active

    @property
    def needs_branch_current(self):
        return False

    def stamp(self, system):
        pass

    def voltage(self, system):
        return system.difference(self.a, self.b)

    def current(self, system):
        return system.zero()

    def inequalities(self, system):
        return []


class Resistor(Device):
    def stamp(self, system):
        system.conductance(self.a, self.b, 1 / self.component.parameters["resistance_ohm"])

    def current(self, system):
        return self.voltage(system) / self.component.parameters["resistance_ohm"]


class VoltageSource(Device):
    @property
    def needs_branch_current(self):
        return True

    def stamp(self, system):
        system.voltage_constraint(self.id, self.a, self.b,
                                  self.component.parameters["voltage_v"])

    def current(self, system):
        return system.branch_current(self.id)


class Switch(Device):
    @property
    def needs_branch_current(self):
        return contact_closed(self.component)

    def stamp(self, system):
        if self.needs_branch_current:
            system.voltage_constraint(self.id, self.a, self.b, 0)

    def current(self, system):
        return system.branch_current(self.id) if self.needs_branch_current else system.zero()


class Button(Switch):
    """Momentary contact state is derived by the shared contact_closed helper."""


class LED(Device):
    @property
    def needs_branch_current(self):
        return self.active

    def stamp(self, system):
        if self.active:
            system.voltage_constraint(self.id, self.a, self.b,
                                      self.component.parameters["forward_voltage_v"])

    def current(self, system):
        return system.branch_current(self.id) if self.active else system.zero()

    def inequalities(self, system):
        # Every inequality is coefficient-vector @ solution <= upper_bound.
        if self.active:
            return [(-self.current(system), 0)]  # Forward current cannot be negative.
        return [(self.voltage(system), self.component.parameters["forward_voltage_v"])]


DEVICE_TYPES = {"resistor": Resistor, "voltage_source": VoltageSource,
                "switch": Switch, "button": Button, "led": LED}
