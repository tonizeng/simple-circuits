"""Vector symbols with rectangular series-loop and fallback net-lane layouts."""

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainterPath, QPainterPathStroker, QPen, QPolygonF
from PySide6.QtWidgets import QApplication, QGraphicsItem, QGraphicsPathItem, QGraphicsSimpleTextItem, QGraphicsDropShadowEffect
from components import nominal_label, contact_closed, engineering
from layout import series_parallel_layout, open_series_parallel_layout


DEFAULT_HIGHLIGHT_COLORS = {"component": "#a2c96e", "node": "#787aaf", "current": "#2878b5"}


def highlight_color(item, role):
    scene = item.scene()
    colors = scene.property("highlightColors") if scene is not None else None
    return QColor((colors or DEFAULT_HIGHLIGHT_COLORS)[role])


class ResultBox(QGraphicsPathItem):
    """Prototype readout with a green hover border."""

    def __init__(self, path):
        super().__init__(path)
        self.symbol = None
        self.setAcceptHoverEvents(True)
        self.setZValue(1)
        self.highlight(False)

    def highlight(self, active):
        active = active or (self.symbol is not None and self.symbol.pinned)
        self.setPen(QPen(highlight_color(self, "component") if active else QColor("#888888"),
                         3 if active else 2))
        fill = QColor("#ffffff")
        if active:
            tint = highlight_color(self, "component")
            fill = QColor(*(round(255 * 0.9 + channel * 0.1)
                            for channel in (tint.red(), tint.green(), tint.blue())))
        self.setBrush(fill)
        if self.symbol is not None:
            self.symbol.set_highlight(active)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self.symbol is not None:
                self.symbol.toggle_pin()
            event.accept()
        else:
            super().mousePressEvent(event)

    def hoverEnterEvent(self, event):
        self.highlight(True)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self.highlight(False)
        super().hoverLeaveEvent(event)


class NetLabel(QGraphicsSimpleTextItem):
    def __init__(self, text, font, net):
        super().__init__(text)
        self.setFont(font)
        self.net = net
        self.glow = QGraphicsDropShadowEffect()
        self.glow.setOffset(0, 0)
        self.glow.setBlurRadius(10)
        self.glow.setEnabled(False)
        self.setGraphicsEffect(self.glow)
        self.setAcceptHoverEvents(True)

    def boundingRect(self):
        return super().boundingRect().adjusted(-6, -6, 6, 6)

    def shape(self):
        path = QPainterPath()
        path.addRect(self.boundingRect())
        return path

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.net.toggle_pin()
            event.accept()
        else:
            super().mousePressEvent(event)

    def hoverEnterEvent(self, event):
        self.net.highlight(True)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self.net.highlight(False)
        super().hoverLeaveEvent(event)


class NetWire(QGraphicsPathItem):
    """One electrical net, with a generous hover target around thin wires."""

    def __init__(self, path):
        super().__init__(path)
        self.pinned = False
        self.label = None
        self.dots = []
        self.setAcceptHoverEvents(True)
        self.setZValue(-1)
        self.highlight(False)

    def shape(self):
        stroker = QPainterPathStroker()
        stroker.setWidth(18)
        return stroker.createStroke(self.path())

    def boundingRect(self):
        return self.path().boundingRect().adjusted(-9, -9, 9, 9)

    def highlight(self, active):
        active = active or self.pinned
        color = highlight_color(self, "node") if active else QColor("#555555")
        self.setPen(QPen(color, 3 if active else 1.5))
        if self.label is not None:
            self.label.setBrush(QColor("#222222"))
            self.label.glow.setColor(highlight_color(self, "node"))
            self.label.glow.setEnabled(active)
        for dot in self.dots:
            dot.setPen(QPen(color, 1.5))
            dot.setBrush(color)

    def toggle_pin(self):
        self.pinned = not self.pinned
        self.highlight(self.pinned)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.toggle_pin()
            event.accept()
        else:
            super().mousePressEvent(event)

    def hoverEnterEvent(self, event):
        self.highlight(True)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self.highlight(False)
        super().hoverLeaveEvent(event)


def add_net(scene, path, text, x, y):
    wire = NetWire(path)
    scene.addItem(wire)
    font = QFont(QApplication.font())
    font.setPixelSize(14)
    label = NetLabel(text, font, wire)
    scene.addItem(label)
    label.setPos(x, y)
    wire.label = label
    wire.setToolTip(text)
    wire.highlight(False)
    return wire


class ComponentLabel(QGraphicsSimpleTextItem):
    """Nominal values share the symbol/result hover state."""
    def __init__(self, text, symbol):
        super().__init__(text)
        self.symbol = symbol
        self.glow = QGraphicsDropShadowEffect()
        self.glow.setColor(QColor("#a2c96e"))
        self.glow.setOffset(0, 0)
        self.glow.setBlurRadius(10)
        self.glow.setEnabled(False)
        self.setGraphicsEffect(self.glow)
        self.setAcceptHoverEvents(True)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.symbol.toggle_pin()
            event.accept()
        else:
            super().mousePressEvent(event)

    def hoverEnterEvent(self, event):
        if self.symbol.result_box is not None:
            self.symbol.result_box.highlight(True)
        else:
            self.symbol.set_highlight(True)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        if self.symbol.result_box is not None:
            self.symbol.result_box.highlight(False)
        else:
            self.symbol.set_highlight(False)
        super().hoverLeaveEvent(event)


class ComponentSymbol(QGraphicsItem):
    """Terminal 1 is on the left; terminal 2 is on the right in local space."""

    def __init__(self, component):
        super().__init__()
        self.component = component
        self.highlighted = False
        self.pinned = False
        self.result_box = None
        self.value_label = None
        self.current_a = None
        self.setAcceptHoverEvents(True)
        self.terminals = {"1": QPointF(-60, 0), "2": QPointF(60, 0)}
        if component.type == "potentiometer":
            self.terminals["3"] = QPointF(0, 50)
        self.setToolTip(f"{component.id}: {component.type}\n1: local left, 2: local right"
                        + ("\n3: wiper" if component.type == "potentiometer" else ""))

    def set_highlight(self, active):
        active = active or self.pinned
        self.highlighted = active
        if self.value_label is not None:
            self.value_label.setBrush(QColor("#222222"))
            self.value_label.glow.setColor(highlight_color(self, "component"))
            self.value_label.glow.setEnabled(active)
        self.update()

    def toggle_pin(self):
        self.pinned = not self.pinned
        if self.result_box is not None:
            self.result_box.highlight(self.pinned)
        else:
            self.set_highlight(self.pinned)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.toggle_pin()
            event.accept()
        else:
            super().mousePressEvent(event)

    def terminal_position(self, terminal):
        return self.mapToScene(self.terminals[terminal])

    def hoverEnterEvent(self, event):
        self.set_highlight(True)
        if self.result_box is not None:
            self.result_box.highlight(True)
        self.update()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self.set_highlight(False)
        if self.result_box is not None:
            self.result_box.highlight(False)
        self.update()
        super().hoverLeaveEvent(event)

    def boundingRect(self):
        return QRectF(-64, -55, 128, 110)

    def current_arrow_points(self):
        if self.current_a is None or abs(self.current_a) <= 1e-12:
            return None
        start, end = QPointF(-56, -16), QPointF(-36, -16)
        return (start, end) if self.current_a > 0 else (end, start)

    def paint(self, painter, option, widget=None):
        painter.setPen(QPen(highlight_color(self, "component") if self.highlighted else QColor("#222222"),
                            3 if self.highlighted else 2))
        kind = self.component.type
        edge = 24 if kind == "voltage_source" else 30
        painter.drawLine(QPointF(-60, 0), QPointF(-edge, 0))
        painter.drawLine(QPointF(edge, 0), QPointF(60, 0))
        if kind in ("resistor", "potentiometer"):
            path = QPainterPath(QPointF(-30, 0))
            for x, y in [(-25, -10), (-15, 10), (-5, -10), (5, 10), (15, -10), (25, 10), (30, 0)]:
                path.lineTo(x, y)
            painter.drawPath(path)
            if kind == "potentiometer":
                painter.drawLine(QPointF(0, 50), QPointF(0, 14))
                self.draw_arrow(painter, QPointF(0, 36), QPointF(0, 14))
        elif kind == "voltage_source":
            painter.drawEllipse(QRectF(-24, -24, 48, 48))
            painter.drawLine(QPointF(-16, 0), QPointF(-6, 0))
            painter.drawLine(QPointF(-11, -5), QPointF(-11, 5))
            painter.drawLine(QPointF(6, 0), QPointF(16, 0))
        elif kind in ("led", "diode", "photodiode"):
            painter.drawLine(QPointF(-30, 0), QPointF(-15, 0))
            painter.drawPolygon(QPolygonF([QPointF(-15, -14), QPointF(-15, 14), QPointF(15, 0)]))
            painter.drawLine(QPointF(15, -14), QPointF(15, 14))
            painter.drawLine(QPointF(15, 0), QPointF(30, 0))
            if kind != "diode":
                for dx in (0, 12):
                    start, end = QPointF(dx, -17), QPointF(dx + 12, -32)
                    if kind == "photodiode":
                        start, end = end, start
                    self.draw_arrow(painter, start, end)
        elif kind == "wire":
            painter.drawLine(QPointF(-30, 0), QPointF(30, 0))
        elif kind in ("switch", "button"):
            closed = contact_closed(self.component)
            painter.drawEllipse(QPointF(-30, 0), 3, 3)
            painter.drawEllipse(QPointF(30, 0), 3, 3)
            if kind == "switch":
                painter.drawLine(QPointF(-30, 0), QPointF(30, 0 if closed else -22))
            else:
                contact_y = 0 if closed else -14
                painter.drawLine(QPointF(-30, contact_y), QPointF(30, contact_y))
                painter.drawLine(QPointF(0, contact_y), QPointF(0, contact_y - 15))
                painter.drawLine(QPointF(-10, contact_y - 15), QPointF(10, contact_y - 15))
        elif kind == "capacitor":
            painter.drawLine(QPointF(-30, 0), QPointF(-7, 0))
            painter.drawLine(QPointF(7, 0), QPointF(30, 0))
            painter.drawLine(QPointF(-7, -20), QPointF(-7, 20))
            painter.drawLine(QPointF(7, -20), QPointF(7, 20))
        elif kind == "inductor":
            path = QPainterPath(QPointF(-30, 0))
            for x in (-30, -15, 0, 15):
                path.cubicTo(x, -20, x + 15, -20, x + 15, 0)
            painter.drawPath(path)
        for point in self.terminals.values():
            painter.drawEllipse(point, 3, 3)
        arrow = self.current_arrow_points()
        if arrow is not None:
            painter.setPen(QPen(highlight_color(self, "current").darker(130) if self.highlighted else highlight_color(self, "current"), 2))
            self.draw_arrow(painter, *arrow)

    @staticmethod
    def draw_arrow(painter, start, end):
        import math
        angle = math.atan2(end.y() - start.y(), end.x() - start.x())
        painter.drawLine(start, end)
        for offset in (-0.5, 0.5):
            painter.drawLine(end, end - QPointF(7 * math.cos(angle + offset),
                                               7 * math.sin(angle + offset)))


def add_label(scene, text, x, y, component=None):
    font = QFont(QApplication.font())
    font.setPixelSize(14)
    if component is None:
        label = scene.addSimpleText(text, font)
    else:
        label = ComponentLabel(text, component)
        label.setFont(font)
        scene.addItem(label)
        component.value_label = label
    label.setPos(x, y)
    label.setBrush(QColor("#222222"))
    return label


def rectangular_layout(circuit):
    """Return placements for a three-component loop, derived from connections.

    Coordinates are temporary until the physical board mapping is available.
    Each placement is (x, y, rotation); terminal identities are never swapped.
    """
    sources = [c for c in circuit.components if c.type == "voltage_source"]
    if len(circuit.components) != 3 or len(circuit.nets) != 3 or len(sources) != 1:
        return None
    if any(len(net.terminals) != 2 for net in circuit.nets):
        return None
    if any(component.type == "potentiometer" for component in circuit.components):
        return None
    peers = {}
    for net in circuit.nets:
        a, b = net.terminals
        peers[(a.component_id, a.terminal)] = (b.component_id, b.terminal)
        peers[(b.component_id, b.terminal)] = (a.component_id, a.terminal)
    source = sources[0].id
    top, top_entry = peers[(source, "1")]
    right, right_entry = peers[(top, "2" if top_entry == "1" else "1")]
    if len({source, top, right}) != 3:
        return None
    if peers[(right, "2" if right_entry == "1" else "1")] != (source, "2"):
        return None
    return {source: (100, 220, 90),
            top: (320, 80, 0 if top_entry == "1" else 180),
            right: (540, 220, 90 if right_entry == "1" else 270)}


def draw_rectangular_nets(scene, circuit, symbols):
    pen = QPen(QColor("#555555"), 1.5)
    for net in circuit.nets:
        a, b = [symbols[t.component_id].terminal_position(t.terminal) for t in net.terminals]
        if a.y() == b.y():
            points = [a, QPointF(a.x(), 360), QPointF(b.x(), 360), b]
            label_x, label_y = (a.x() + b.x()) / 2, 365
        else:
            # Horizontal component meets a vertical component at a corner.
            vertical, horizontal = (a, b) if a.y() != 80 else (b, a)
            corner = QPointF(vertical.x(), horizontal.y())
            points = [vertical, corner, horizontal]
            label_x, label_y = (corner.x() + horizontal.x()) / 2, 50
        path = QPainterPath(points[0])
        for point in points[1:]:
            path.lineTo(point)
        suffix = " (0 V reference)" if net.id == circuit.ground_node else ""
        wire = add_net(scene, path, net.id + suffix, 0, label_y)
        label = wire.label
        label.setX(label_x - label.boundingRect().width() / 2)


def draw_planned_nets(scene, circuit, plan):
    for net in circuit.nets:
        routes = plan.routes[net.id]
        path = QPainterPath()
        for points in routes:
            path.moveTo(QPointF(*points[0]))
            for point in points[1:]:
                path.lineTo(QPointF(*point))
        horizontal = [(a, b) for points in routes for a, b in zip(points, points[1:])
                      if a[1] == b[1] and a != b]
        if horizontal:
            a, b = max(horizontal, key=lambda pair: abs(pair[1][0] - pair[0][0]))
            label_x, label_y = (a[0] + b[0]) / 2, a[1] - 26
        else:
            # Internal series node: label the join between consecutive components.
            point = routes[0][-1]
            label_x, label_y = point[0] + 24, point[1] - 12
        suffix = " (0 V reference)" if net.id == circuit.ground_node else ""
        wire = add_net(scene, path, net.id + suffix, label_x, label_y)
        wire.setData(0, net.id)
        if horizontal:
            wire.label.setX(label_x - wire.label.boundingRect().width() / 2)
        # Mark joins/endpoints explicitly. Wires from other nets never gain dots
        # simply because their geometry crosses this net.
        points = {point for route in routes for point in route}
        for x, y in points:
            dot = scene.addEllipse(x - 2, y - 2, 4, 4, wire.pen(), QColor("#555555"))
            wire.dots.append(dot)


def render_circuit(scene, circuit, simulation=None):
    """Draw three-component series loops rectangularly, otherwise use net lanes.

    This initial layout prioritizes explicit connections over compact textbook
    circuit arrangements. It does not simulate, merge raw wires, or optimize
    crossings. Only pass circuits produced by parse_topology().
    """
    scene.clear()
    symbols = {}
    placements = rectangular_layout(circuit)
    plan = None if placements else (series_parallel_layout(circuit) or open_series_parallel_layout(circuit))
    if plan is not None:
        placements = plan.placements
    y = 80 + 50 * len(circuit.nets)
    for index, component in enumerate(circuit.components):
        symbol = ComponentSymbol(component)
        scene.addItem(symbol)
        if placements:
            x, symbol_y, rotation = placements[component.id]
            symbol.setPos(x, symbol_y)
            symbol.setRotation(rotation)
        else:
            symbol.setPos(160 + index * 220, y)
        symbols[component.id] = symbol
        label = add_label(
            scene, nominal_label(component),
            0, symbol.y() + (90 if component.type == "potentiometer" else 28), component=symbol,
        )
        if component.type == "led" and simulation is not None:
            label.setToolTip("Nominal LED forward voltage; the default classroom model treats this as a fixed drop while conducting.")
        if placements and symbol.rotation() in (90, 270):
            if component.type == "potentiometer":
                label.setPos(symbol.x() - label.boundingRect().width() - 38,
                             symbol.y() + 30)
            elif component.type == "voltage_source":
                label.setPos(symbol.x() + 38, symbol.y() - label.boundingRect().height() / 2)
            else:
                label.setPos(symbol.x() - label.boundingRect().width() - 38,
                             symbol.y() - label.boundingRect().height() / 2)
        else:
            label.setX(symbol.x() - label.boundingRect().width() / 2)
        result = simulation.components.get(component.id) if simulation is not None else None
        voltage = engineering(result.voltage_v, "V") if result is not None and result.voltage_v is not None else "—"
        current = engineering(abs(result.current_a), "A") if result is not None and result.current_a is not None else "—"
        symbol.current_a = result.current_a if result is not None else None
        output = add_label(scene, f"V: {voltage}\nI: {current}", 0, 0)
        message = (simulation.message if simulation.status != "solved" else "") if simulation is not None else "No simulation results supplied."
        if result is not None and result.terminal_currents_a is not None:
            message += "\nPotentiometer I is current entering terminal 1; V is across track ends 1 and 2."
            message += "\nTerminal currents: " + ", ".join(
                f"{terminal}: {engineering(current, 'A') if current is not None else '—'}"
                for terminal, current in result.terminal_currents_a.items())
        if result is not None and result.state:
            message += f"\nState: {result.state}"
        output.setToolTip((message + "\nV = V1 − V2. I displays magnitude; the arrow shows conventional current direction.").strip())
        if placements:
            if component.type == "voltage_source":
                output.setPos(symbol.x() - output.boundingRect().width() - 47,
                              symbol.y() - output.boundingRect().height() / 2)
            elif symbol.rotation() in (90, 270):
                output.setPos(symbol.x() + 60, symbol.y() + 22)
            else:
                output.setPos(symbol.x() - output.boundingRect().width() / 2,
                              symbol.y() - output.boundingRect().height() - 35)
        else:
            output.setPos(symbol.x() - output.boundingRect().width() / 2,
                          label.sceneBoundingRect().bottom() + 18)
        box_path = QPainterPath()
        box_path.addRoundedRect(
            output.sceneBoundingRect().adjusted(-8, -6, 8, 6),
            5, 5,
        )
        box = ResultBox(box_path)
        box.symbol = symbol
        symbol.result_box = box
        scene.addItem(box)
        output.setParentItem(box)
        output.setZValue(2)
        for terminal in symbol.terminals:
            point = symbol.terminal_position(terminal)
            add_label(scene, terminal, point.x() - 5, point.y() + 7)
    if placements:
        if plan is not None:
            draw_planned_nets(scene, circuit, plan)
        else:
            draw_rectangular_nets(scene, circuit, symbols)
        scene.setSceneRect(scene.itemsBoundingRect().adjusted(-30, -30, 30, 30))
        return symbols
    pen = QPen(QColor("#555555"), 1.5)
    for index, net in enumerate(circuit.nets):
        lane_y = 35 + index * 50
        points = [symbols[t.component_id].terminal_position(t.terminal) for t in net.terminals]
        # Route a bottom-facing wiper around the symbol instead of through it.
        taps = [QPointF(p.x() + 90, lane_y) if t.terminal == "3"
                else QPointF(p.x(), lane_y) for p, t in zip(points, net.terminals)]
        left, right = min(p.x() for p in taps), max(p.x() for p in taps)
        path = QPainterPath(QPointF(left, lane_y))
        path.lineTo(right, lane_y)
        for point, tap, terminal in zip(points, taps, net.terminals):
            path.moveTo(tap)
            if terminal.terminal == "3":
                path.lineTo(tap.x(), point.y() + 25)
                path.lineTo(point.x(), point.y() + 25)
            path.lineTo(point)
        suffix = " (0 V reference)" if net.id == circuit.ground_node else ""
        wire = add_net(scene, path, net.id + suffix, left, lane_y - 24)
        for point in taps:
            dot = scene.addEllipse(point.x() - 2.5, lane_y - 2.5, 5, 5, pen, QColor("#555555"))
            wire.dots.append(dot)
    scene.setSceneRect(scene.itemsBoundingRect().adjusted(-30, -30, 30, 30))
    return symbols
