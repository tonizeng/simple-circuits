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

    @property
    def current_offset(self):
        return 0.0

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


class Diode(LED):
    """Ideal blocking / constant forward voltage, like the classroom LED."""


class Wire(VoltageSource):
    def stamp(self, system):
        system.voltage_constraint(self.id, self.a, self.b, 0)


class Capacitor(Device):
    """DC equilibrium: zero current. Initial voltage is a transient condition."""


class Inductor(Wire):
    """DC equilibrium: zero voltage. Initial current is a transient condition."""


class Photodiode(Diode):
    """Constant photocurrent from cathode to anode, plus a forward diode."""
    @property
    def current_offset(self):
        return -self.component.parameters["photocurrent_a"]

    def stamp(self, system):
        system.current_source(self.a, self.b, self.current_offset)
        if self.active:
            system.voltage_constraint(self.id, self.a, self.b,
                                      self.component.parameters.get("forward_voltage_v", .7))

    def inequalities(self, system):
        if self.active:
            return [(-system.branch_current(self.id), 0)]
        return [(self.voltage(system), self.component.parameters.get("forward_voltage_v", .7))]


class Potentiometer(Device):
    def __init__(self, component, nodes, active=False):
        super().__init__(component, nodes, active)
        self.wiper = nodes[(self.id, "3")]
        self.position = component.parameters["wiper_position"]
        self.resistance = component.parameters["resistance_ohm"]

    @property
    def needs_branch_current(self):
        return self.position in (0, 1)

    def stamp(self, system):
        if self.position == 0:
            system.voltage_constraint(self.id, self.a, self.wiper, 0)
        else:
            system.conductance(self.a, self.wiper, 1 / (self.resistance * self.position))
        if self.position == 1:
            system.voltage_constraint(self.id, self.wiper, self.b, 0)
        else:
            system.conductance(self.wiper, self.b, 1 / (self.resistance * (1 - self.position)))

    def current(self, system):
        # Displayed I is current entering terminal 1, NOT necessarily wiper current.
        if self.position == 0:
            return system.branch_current(self.id)
        return system.difference(self.a, self.wiper) / (self.resistance * self.position)

    def terminal_currents(self, system):
        first = self.current(system)
        second = (-system.branch_current(self.id) if self.position == 1 else
                  system.difference(self.b, self.wiper) / (self.resistance * (1 - self.position)))
        return {"1": first, "2": second, "3": -first - second}


DEVICE_TYPES.update({"diode": Diode, "wire": Wire, "capacitor": Capacitor,
                     "inductor": Inductor, "potentiometer": Potentiometer,
                     "photodiode": Photodiode})
