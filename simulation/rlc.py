"""Exact fixed-topology series RLC step responses, including all damping regimes."""
from dataclasses import dataclass, replace
import math
from .mna import ComponentResult
from components import contact_closed


@dataclass(frozen=True)
class SeriesRLC:
    circuit: object
    source: object
    capacitor: object
    inductor: object
    # (component, traversal start net, traversal end net, terminal-reference sign)
    path: tuple
    resistance_ohm: float
    capacitor_sign: int
    inductor_sign: int
    kind = 'RLC'

    @property
    def alpha(self):
        return self.resistance_ohm / (2 * self.inductor.parameters['inductance_h'])

    @property
    def omega0(self):
        return 1 / math.sqrt(self.inductor.parameters['inductance_h'] * self.capacitor.parameters['capacitance_f'])

    @property
    def damping_ratio(self):
        return self.alpha / self.omega0

    @property
    def regime(self):
        if math.isclose(self.alpha, self.omega0, rel_tol=1e-8):
            return 'Critically damped'
        return 'Underdamped' if self.alpha < self.omega0 else 'Overdamped'

    @property
    def duration_s(self):
        if self.regime == 'Underdamped':
            period = 2 * math.pi / math.sqrt((self.omega0-self.alpha)*(self.omega0+self.alpha))
            return min(8 / self.alpha, 10 * period)
        if self.regime == 'Overdamped':
            root = math.sqrt((self.alpha-self.omega0)*(self.alpha+self.omega0))
            slow_rate = self.omega0**2 / (self.alpha + root)
            return 8 / slow_rate
        return 8 / self.alpha

    @property
    def tau_s(self):
        # UI normalization only; never presented as a universal RLC time constant.
        return self.duration_s / 5

    def state(self, time_s):
        """Return loop-oriented capacitor voltage, loop current, inductor voltage."""
        if not math.isfinite(time_s) or time_s < 0:
            raise ValueError('Time must be finite and nonnegative.')
        supply = self.source.parameters['voltage_v']
        capacitance = self.capacitor.parameters['capacitance_f']
        x0 = self.capacitor_sign * self.capacitor.parameters.get('initial_voltage_v', 0.0) - supply
        derivative0 = self.inductor_sign * self.inductor.parameters.get('initial_current_a', 0.0) / capacitance
        alpha, omega = self.alpha, self.omega0
        if self.regime == 'Underdamped':
            wd = math.sqrt((omega-alpha)*(omega+alpha))
            coefficient = (derivative0 + alpha*x0) / wd
            decay = math.exp(-alpha*time_s)
            cosine, sine = math.cos(wd*time_s), math.sin(wd*time_s)
            x = decay * (x0*cosine + coefficient*sine)
            derivative = decay * (derivative0*cosine - (alpha*coefficient + x0*wd)*sine)
        elif self.regime == 'Critically damped':
            coefficient = derivative0 + alpha*x0
            decay = math.exp(-alpha*time_s)
            x = decay * (x0 + coefficient*time_s)
            derivative = decay * (derivative0 - alpha*coefficient*time_s)
        else:
            root = math.sqrt((alpha-omega)*(alpha+omega))
            slow = -omega**2 / (alpha+root)
            fast = -(alpha+root)
            first = (derivative0-fast*x0) / (slow-fast)
            second = x0-first
            a, b = first*math.exp(slow*time_s), second*math.exp(fast*time_s)
            x, derivative = a+b, slow*a+fast*b
        voltage = supply+x
        current = capacitance*derivative
        return voltage, current, supply-self.resistance_ohm*current-voltage

    def snapshot(self, time_s, settled):
        cap_voltage, current, ind_voltage = self.state(time_s)
        supply = self.source.parameters['voltage_v']
        terminals = self.circuit.terminal_nodes()
        potentials = {terminals[self.source.id, '2']: 0.0, terminals[self.source.id, '1']: supply}
        results = {self.source.id: ComponentResult(supply, -current)}
        for component, start, end, sign in self.path:
            if component.type == 'capacitor':
                drop = cap_voltage
            elif component.type == 'inductor':
                drop = ind_voltage
            elif component.type in ('resistor', 'photoresistor'):
                drop = component.parameters['resistance_ohm'] * current
            else:
                drop = 0.0
            potentials[end] = potentials[start]-drop
            results[component.id] = ComponentResult(sign*drop, sign*current, 'predicted RLC response')
        # Ground can be any net; component voltage/current signs remain terminal-based.
        reference = potentials[settled.ground_node]
        return replace(settled, message='Predicted analytical series RLC response', components=results,
                       node_voltages={net: value-reference for net,value in potentials.items()})

    def plot_model(self, component_id):
        return RLCPlotModel(self, component_id)


@dataclass(frozen=True)
class RLCPlotModel:
    model: SeriesRLC
    component_id: str
    kind = 'RLC'

    @property
    def tau_s(self):
        return self.model.tau_s

    @property
    def duration_s(self):
        return self.model.duration_s

    @property
    def storage_quantity(self):
        return 0 if self.component_id == self.model.capacitor.id else 1

    @property
    def storage_name(self):
        return 'capacitor' if self.storage_quantity == 0 else 'inductor'

    def response(self, time_s, initial=None, final=None):
        vc, current, vl = self.model.state(time_s)
        if self.component_id == self.model.capacitor.id:
            return self.model.capacitor_sign*vc, self.model.capacitor_sign*current
        return self.model.inductor_sign*vl, self.model.inductor_sign*current


def series_rlc(circuit):
    """Recognize one closed series loop; reject arbitrary/multiple-storage networks."""
    groups = {kind: [c for c in circuit.components if c.type == kind]
              for kind in ('voltage_source', 'capacitor', 'inductor')}
    if any(len(group) != 1 for group in groups.values()):
        return None, 'RLC preview requires one DC source, one capacitor and one inductor in a single series loop.'
    allowed = {'voltage_source','capacitor','inductor','resistor','photoresistor','wire','switch','button'}
    if any(c.type not in allowed or (c.type in ('switch','button') and not contact_closed(c)) for c in circuit.components):
        return None, 'RLC preview supports only a closed, linear series circuit.'
    if any(len(net.terminals) != 2 for net in circuit.nets):
        return None, 'RLC preview requires a single series loop without branches or open terminals.'
    terminals = circuit.terminal_nodes()
    components = {c.id:c for c in circuit.components}
    source,cap,ind = (groups[k][0] for k in ('voltage_source','capacitor','inductor'))
    current = terminals[source.id,'1']
    target = terminals[source.id,'2']
    if current == target:
        return None, 'The source cannot be shorted for an RLC preview.'
    nets = {n.id:n for n in circuit.nets}
    visited = {source.id}
    path = []
    while current != target:
        candidates = [t for t in nets[current].terminals if t.component_id not in visited]
        if len(candidates) != 1:
            return None, 'RLC preview requires a single series loop.'
        terminal = candidates[0]
        component = components[terminal.component_id]
        sign = 1 if terminal.terminal == '1' else -1
        end = terminals[component.id, '2' if sign == 1 else '1']
        path.append((component,current,end,sign))
        visited.add(component.id)
        current = end
    if len(visited) != len(components):
        return None, 'RLC preview does not support additional disconnected circuits.'
    resistance = sum(c.parameters['resistance_ohm'] for c in components.values() if c.type in ('resistor','photoresistor'))
    if resistance <= 0 or not math.isfinite(resistance):
        return None, 'RLC preview requires positive series resistance.'
    signs = {c.id:sign for c,_,_,sign in path}
    return SeriesRLC(circuit,source,cap,ind,tuple(path),resistance,signs[cap.id],signs[ind.id]),None
