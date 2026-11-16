"""Read-only engineering inspector using component data and solved DC results."""
from pathlib import Path
import math
from html import escape
from PySide6.QtCore import Qt, Signal, QRectF, QTimer
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtGui import QColor, QPixmap, QPainter, QPen
from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
    QScrollArea, QWidget, QDialog, QGraphicsScene, QSizePolicy, QGraphicsDropShadowEffect,
)
from components import COMPONENT_NAMES, COMPONENT_DESCRIPTIONS, nominal_label, engineering, current_reading
from schematic import ComponentSymbol
from simulation.rlc import series_rlc
from simulation.rl import rl_timing
from simulation.rc import rc_timing, rc_response_phase
from rc_response_ui import RCResponseWidget

# Inspector colours: edit these to adjust the purple-grey tint.
PANEL_BACKGROUND = "#edf4f2"
ACCENT_BACKGROUND = "#ffffff"
HOVER_BACKGROUND = "#dedede"

OVERVIEW_ROW_STYLE = "QPushButton { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #ffffff, stop:1 #fafcfc); color: #111111; border: 1px solid #bccbc9; border-radius: 10px; margin: 3px 0px; text-align: left; } QPushButton:hover { background: #f7f9f9; border-color: #c9d4d3; } QPushButton:checked { background: #dedede; border-color: #aab6b5; }"


def add_list_row_shadow(widget):
    shadow = QGraphicsDropShadowEffect(widget)
    shadow.setBlurRadius(6)
    shadow.setOffset(0, 1)
    shadow.setColor(QColor(0, 0, 0, 18))
    widget.setGraphicsEffect(shadow)


HELP_TOPICS = (
    ("Voltage and polarity", "V = V(1) − V(2). A positive value means terminal 1 is at a higher voltage; a negative value means terminal 2 is higher."),
    ("Current direction", "Arrows show conventional current direction using your current highlight colour. Displayed current values show magnitude; zero current has no arrow."),
    ("Ground reference", "The ground node is the 0 V reference. Node voltages are measured relative to it; this does not necessarily mean earth ground."),
    ("Unavailable values", "A dash (—) means results are unavailable. Any warning or error hides all calculated results until the circuit passes its checks."),
)
TYPE_SUBTITLES = {
    "voltage_source": "DC voltage supply", "resistor": "Passive component",
    "led": "Light-emitting diode", "diode": "Semiconductor diode",
    "photoresistor": "Light-dependent resistor", "capacitor": "Electric-field energy storage",
    "inductor": "Magnetic-field energy storage", "potentiometer": "Three-terminal variable resistor",
    "switch": "Maintained contact", "button": "Momentary contact", "wire": "Ideal electrical connection",
}
PRIMARY_NAMES = {
    "voltage_source": "Source voltage", "resistor": "Resistance", "led": "Forward voltage",
    "diode": "Forward voltage", "photoresistor": "Resistance", "capacitor": "Capacitance",
    "inductor": "Inductance", "potentiometer": "Track resistance and wiper",
    "switch": "Contact state", "button": "Contact state", "wire": "Connection",
}


def available(value):
    return value is not None and math.isfinite(value)


def delivered_power(result):
    """Current is defined into terminal 1: negative absorbed power is delivered."""
    if result and available(result.voltage_v) and available(result.current_a):
        return -result.voltage_v * result.current_a
    return None


def text_label(text, parent=None, role=None):
    label = QLabel(text, parent)
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setWordWrap(True)
    if role:
        label.setObjectName(role)
    return label


class DisclosureButton(QPushButton):
    """A fixed-size SVG chevron at the right edge, independent of title length."""
    def __init__(self, colour="#222222"):
        super().__init__()
        self.chevrons = {}
        for direction in ("right", "down"):
            path = Path(__file__).resolve().parent / "assets" / "images" / f"chevron-{direction}.svg"
            self.chevrons[direction] = QSvgRenderer(path.read_bytes().replace(b"currentColor", colour.encode()))
        self.setCheckable(True)
        self.toggled.connect(self.update)

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        renderer = self.chevrons["down" if self.isChecked() else "right"]
        renderer.render(painter, QRectF(self.width() - 20, (self.height() - 16) / 2, 16, 16))


class ComponentDetailsPanel(QFrame):
    panel_close_requested = Signal()
    clear_requested = Signal()
    node_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("componentDetailsPanel")
        self.setMinimumWidth(0)
        self.setMaximumWidth(280)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        self.setStyleSheet("""
            QFrame#componentDetailsPanel { background: #f5f5f5; border: 1.2px solid #cccccc; border-radius: 14px; }
            QFrame#componentDetailsPanel QWidget { font-family: "Ulagadi Sans"; font-size: 14px; }
            QLabel { background: transparent; color: #161616; }
            QLabel#inspectorEyebrow { font-size: 11px; color: #777777; font-weight: 500; }
            QFrame#componentDetailsPanel QLabel#componentTitle { font-size: 16px; font-weight: bold; color: #111111; background: transparent; padding: 0px; }
            QLabel#secondaryText { color: #444444; font-size: 14px; }
            QLabel#primaryReading { font-size: 16px; font-weight: 500; }
            QFrame#componentDetailsPanel QLabel#metricReading { font-size: 16px; font-weight: bold; }
            QFrame#componentDetailsPanel QLabel#electricalHeading { color: #3f4288; font-size: 14.5px; font-weight: bold; }
            QLabel#sectionTitle { font-size: 14.5px; font-weight: bold; }
            QFrame#primarySurface { background: #f6f6f6; border: 1px solid #c7d3d1; border-radius: 12px; }
            QFrame#equationSurface { background: transparent; border: none; border-radius: 12px; }
            QFrame#symbolSurface { background: #ffffff; border: 1px solid #c7d3d1; border-radius: 12px; }
            QFrame#thinDivider { background: #eeeeee; border: none; }
            QPushButton { background: transparent; border: none; padding: 4px; color: #222222; }
            QPushButton:hover { background: #eeeeee; border-radius: 6px; }
            QPushButton#inspectorDisclosure { text-align: left; font-weight: 500; padding: 8px 24px 8px 0px; }
        """.replace("#f5f5f5", PANEL_BACKGROUND)
            .replace("#f6f6f6", ACCENT_BACKGROUND)
            .replace("#eeeeee", HOVER_BACKGROUND))
        self.component_id = None
        self.node_id = None
        self.current_display = "arrows"
        self.overview_circuit = None
        self.component_list = None
        self.expanded_sections = {}
        self.help_dialog = None
        self.header_timer = QTimer(self)
        self.header_timer.setSingleShot(True)
        self.header_timer.timeout.connect(self.fit_header_text)
        outer_shadow = QGraphicsDropShadowEffect(self)
        outer_shadow.setBlurRadius(14)
        outer_shadow.setOffset(0, 0)
        outer_shadow.setColor(QColor(0, 0, 0, 28))
        self.setGraphicsEffect(outer_shadow)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 8, 16)
        layout.setSpacing(12)
        self.selection_prompt = text_label("Select a component or node to learn more.", role="secondaryText")
        identity = QHBoxLayout()
        identity.setSpacing(8)
        self.symbol_surface = QFrame()
        self.symbol_surface.setObjectName("symbolSurface")
        symbol_shadow = QGraphicsDropShadowEffect(self.symbol_surface)
        symbol_shadow.setBlurRadius(8)
        symbol_shadow.setOffset(0, 2)
        symbol_shadow.setColor(QColor(0, 0, 0, 18))
        self.symbol_surface.setGraphicsEffect(symbol_shadow)
        self.symbol_surface.setFixedSize(64, 56)
        symbol_layout = QVBoxLayout(self.symbol_surface)
        symbol_layout.setContentsMargins(4, 4, 4, 4)
        self.symbol_icon = QLabel()
        self.symbol_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        symbol_layout.addWidget(self.symbol_icon)
        identity.addWidget(self.symbol_surface)
        names = QVBoxLayout()
        names.setSpacing(0)
        names.setContentsMargins(0, 0, 0, 0)
        names.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        self.title = text_label("Circuit details", role="componentTitle")
        names.addWidget(self.title)
        self.subtitle = text_label("", role="secondaryText")
        names.addWidget(self.subtitle)
        identity.addLayout(names, 1)
        self.close_button = QPushButton("×")
        self.close_button.setFixedSize(24, 24)
        self.close_button.setStyleSheet("QPushButton { background: transparent; border: none; padding: 0px; border-radius: 6px; } QPushButton:hover { background: #f7f9f9; }")
        self.close_button.setAccessibleName("Back to circuit overview")
        self.close_button.setToolTip("Back to circuit overview")
        self.close_button.clicked.connect(self.close_or_clear)
        identity.addWidget(self.close_button, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(identity)
        header_divider = QFrame()
        header_divider.setObjectName("thinDivider")
        header_divider.setFixedHeight(1)
        layout.addWidget(header_divider)
        layout.addWidget(self.selection_prompt)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet("QScrollArea { background: #f5f5f5; border: none; } QScrollBar:vertical { width: 6px; }".replace("#f5f5f5", PANEL_BACKGROUND))
        layout.addWidget(self.scroll, 1)
        self.clear_selection()

    def fit_header_text(self):
        for label in (self.title, self.subtitle):
            if not label.isHidden():
                label.ensurePolished()
                height = label.heightForWidth(max(1, label.width()))
                label.setMinimumHeight(max(label.fontMetrics().height(), height))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "header_timer"):
            self.header_timer.start(0)

    def show_help(self):
        if self.help_dialog is not None:
            self.help_dialog.show()
            self.help_dialog.raise_()
            return
        self.help_dialog = QDialog(self)
        self.help_dialog.setWindowTitle("How to read")
        self.help_dialog.resize(380, 420)
        layout = QVBoxLayout(self.help_dialog)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)
        for title, explanation in HELP_TOPICS:
            toggle = QPushButton("▸ " + title)
            toggle.setCheckable(True)
            body = text_label(explanation, self.help_dialog)
            body.hide()
            def expand(checked, button=toggle, text=title, description=body):
                description.setVisible(checked)
                button.setText(("▾ " if checked else "▸ ") + text)
            toggle.toggled.connect(expand)
            layout.addWidget(toggle)
            layout.addWidget(body)
        layout.addStretch()
        self.help_dialog.setModal(False)
        self.help_dialog.show()

    def close_or_clear(self):
        if self.component_id is None and self.node_id is None:
            self.panel_close_requested.emit()
        else:
            self.clear_requested.emit()

    def clear_selection(self):
        self.close_button.show()
        self.close_button.setAccessibleName("Hide Circuit Overview")
        self.component_id = None
        self.node_id = None
        self.title.setText("Circuit Overview")
        self.symbol_icon.clear()
        self.symbol_surface.hide()
        self.subtitle.hide()
        self.selection_prompt.show()
        self.set_content(None)

    def disclosure(self, container, title, body, key, default=True):
        accented = title.casefold() in ("purpose", "connected terminals", "rc timing", "predicted rc response", "rl timing", "predicted rl response", "rlc response", "predicted rlc response")
        button = DisclosureButton("#3e407b" if accented else "#222222")
        button.setObjectName("inspectorDisclosure")
        if accented:
            button.setStyleSheet("""
                QPushButton { color: #3f4288; font-size: 14.5px; font-weight: bold; text-align: left; padding: 8px 24px 8px 0px; background: transparent; border: none; }
                QPushButton:hover, QPushButton:pressed, QPushButton:checked, QPushButton:focus { background: transparent; border: none; }
            """)
        button.setCheckable(True)
        expanded = self.expanded_sections.get(key, default)
        button.setChecked(expanded)
        # Parent the content before showing it, so it can never become a window.
        body.setParent(container.parentWidget())
        body.setVisible(expanded)
        def update(checked):
            self.expanded_sections[key] = checked
            button.setText(title)
            body.setVisible(checked)
        update(expanded)
        button.toggled.connect(update)
        container.addWidget(button)
        container.addWidget(body)

    def detach_component_list(self):
        if self.component_list is not None:
            self.component_list.hide()
            self.component_list.setParent(self)

    def set_node_content(self, net, voltage, ground_node):
        self.detach_component_list()
        self.component_id = None
        self.node_id = net.id
        self.selection_prompt.hide()
        self.close_button.show()
        self.close_button.setAccessibleName("Back to circuit overview")
        is_ground = net.id == ground_node
        self.title.setText(f"{net.id} · {'Ground' if is_ground else 'Node'}")
        self.subtitle.setText("0 V reference" if is_ground else "Shared electrical connection")
        self.subtitle.show()
        self.symbol_surface.show()
        pixmap = QPixmap(224, 160)
        pixmap.setDevicePixelRatio(4)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor("#555555"), 1.8))
        if is_ground:
            painter.drawLine(28, 6, 28, 18)
            for y, half_width in ((18, 13), (24, 9), (30, 4)):
                painter.drawLine(28 - half_width, y, 28 + half_width, y)
        else:
            painter.drawLine(8, 20, 48, 20)
            painter.drawLine(28, 6, 28, 34)
            painter.setBrush(QColor("#555555"))
            painter.drawEllipse(QRectF(24, 16, 8, 8))
        painter.end()
        self.symbol_icon.setPixmap(pixmap)
        content = QWidget(self.scroll.viewport())
        content.setObjectName("inspectorContent")
        content.setStyleSheet("QWidget#inspectorContent { background: " + PANEL_BACKGROUND + "; }")
        column = QVBoxLayout(content)
        column.setContentsMargins(0, 0, 12, 8)
        column.setSpacing(16)
        def divider():
            line = QFrame(content)
            line.setObjectName("thinDivider")
            line.setFixedHeight(1)
            column.addWidget(line)
        column.addWidget(text_label("Electrical Properties", role="electricalHeading"))
        reading_layout = QVBoxLayout()
        reading_layout.setContentsMargins(0, 0, 0, 0)
        reading_layout.setSpacing(4)
        reading_layout.addWidget(text_label("Voltage relative to ground", role="secondaryText"))
        reading_layout.addWidget(text_label(engineering(voltage, "V") if available(voltage) else "—", role="metricReading"))
        reading_layout.addWidget(text_label("Calculated", role="secondaryText"))
        column.addLayout(reading_layout)
        divider()
        explanation = ("This node is the circuit’s 0 V reference. Other node voltages are measured relative to it. Ground does not necessarily mean a connection to earth."
                       if is_ground else "A node groups terminals joined by ideal electrical connections. Every terminal on this node shares the same voltage, measured relative to the circuit’s ground reference.")
        purpose = text_label(explanation, content)
        self.disclosure(column, "Purpose", purpose, ("node", net.id, "about"))
        divider()
        terminals = QWidget(content)
        terminals.setObjectName("nodeTerminals")
        terminals.setStyleSheet("QWidget#nodeTerminals { background: transparent; }")
        terminal_layout = QVBoxLayout(terminals)
        terminal_layout.setContentsMargins(0, 0, 0, 0)
        terminal_layout.setSpacing(12)
        for terminal in net.terminals:
            row = QHBoxLayout()
            row.addWidget(text_label(terminal.component_id, role="sectionTitle"), 1)
            row.addWidget(text_label(f"Terminal {terminal.terminal}", role="secondaryText"))
            terminal_layout.addLayout(row)
        if len(net.terminals) == 1:
            terminal_layout.addWidget(text_label("Only one terminal is listed on this node. Check any disconnection warnings for this circuit."))
        self.disclosure(column, "Connected terminals", terminals, ("node", net.id, "terminals"))
        column.addStretch()
        old = self.scroll.takeWidget()
        if old:
            old.deleteLater()
        self.scroll.setWidget(content)
        self.header_timer.start(0)

    def electrical_properties(self, column, parent, caption, nominal, voltage_caption, voltage, current):
        primary = QFrame(parent)
        primary.setObjectName("primarySurface")
        value_shadow = QGraphicsDropShadowEffect(primary)
        value_shadow.setBlurRadius(8)
        value_shadow.setOffset(0, 2)
        value_shadow.setColor(QColor(0, 0, 0, 18))
        primary.setGraphicsEffect(value_shadow)
        primary_layout = QVBoxLayout(primary)
        primary_layout.setContentsMargins(12, 12, 12, 12)
        primary_layout.setSpacing(4)
        is_nominal = caption.endswith(" · nominal")
        property_name = caption.removesuffix(" · nominal")
        primary_layout.addWidget(text_label(property_name, role="secondaryText"))
        primary_layout.addWidget(text_label(nominal, role="metricReading"))
        if is_nominal:
            primary_layout.addWidget(text_label("Nominal", role="secondaryText"))
        column.addWidget(primary)
        readings = QHBoxLayout()
        readings.setSpacing(12)
        for index, (title, value) in enumerate(((voltage_caption, voltage), ("Current", current))):
            if index:
                separator = QFrame(parent)
                separator.setObjectName("thinDivider")
                separator.setFixedWidth(1)
                separator.setMinimumHeight(64)
                readings.addWidget(separator)
            cell = QVBoxLayout()
            cell.setSpacing(4)
            cell.addWidget(text_label(title, role="secondaryText"))
            cell.addWidget(text_label(value, role="metricReading"))
            cell.addWidget(text_label("Calculated", role="secondaryText"))
            readings.addLayout(cell, 1)
        column.addLayout(readings)

    def set_content(self, component, result=None):
        self.detach_component_list()
        self.node_id = None
        previous_id = self.component_id
        content = QWidget(self.scroll.viewport())
        content.setObjectName("inspectorContent")
        content.setStyleSheet("QWidget#inspectorContent { background: #f5f5f5; }".replace("#f5f5f5", PANEL_BACKGROUND))
        column = QVBoxLayout(content)
        column.setContentsMargins(0, 0, 12, 8)
        column.setSpacing(16)
        def divider():
            line = QFrame(content)
            line.setObjectName("thinDivider")
            line.setFixedHeight(1)
            column.addWidget(line)
        if component is None and self.overview_circuit is not None:
            circuit = self.overview_circuit
            def section_heading(title, count):
                header = QVBoxLayout()
                header.setContentsMargins(0, 0, 0, 0)
                header.setSpacing(8)
                row = QHBoxLayout()
                heading = text_label(title)
                heading.setStyleSheet("color: #3f4288; font-weight: bold; background: transparent;")
                row.addWidget(heading, 1)
                number = text_label(str(count), role="secondaryText")
                number.setAccessibleName(f"{count} {title.lower()}")
                number.setAlignment(Qt.AlignmentFlag.AlignRight)
                row.addWidget(number)
                header.addLayout(row)
                line = QFrame(content)
                line.setFixedHeight(1)
                line.setStyleSheet("background: #d9e2e1; border: none;")
                header.addWidget(line)
                column.addLayout(header)
            section_heading("Components", len(circuit.components))
            if self.component_list is not None:
                self.component_list.setStyleSheet("QTableWidget { background: transparent; border: none; }")
                column.addWidget(self.component_list)
                self.component_list.show()
            section_heading("Nodes", len(circuit.nets))
            nodes = QWidget(content)
            nodes.setStyleSheet("background: transparent;")
            node_layout = QVBoxLayout(nodes)
            node_layout.setContentsMargins(0, 0, 0, 0)
            node_layout.setSpacing(0)
            for net in circuit.nets:
                button = QPushButton()
                button.setFixedHeight(72)
                button.setStyleSheet(OVERVIEW_ROW_STYLE)
                add_list_row_shadow(button)
                row = QHBoxLayout(button)
                row.setContentsMargins(8, 8, 8, 8)
                row.setSpacing(8)
                icon = QLabel()
                icon.setFixedSize(60, 44)
                icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
                pixmap = QPixmap(224, 160)
                pixmap.setDevicePixelRatio(4)
                pixmap.fill(Qt.GlobalColor.transparent)
                painter = QPainter(pixmap)
                painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                painter.setPen(QPen(QColor("#222222"), 1.8))
                painter.drawLine(8, 20, 48, 20)
                painter.drawLine(28, 6, 28, 34)
                painter.setBrush(QColor("#222222"))
                painter.drawEllipse(QRectF(24, 16, 8, 8))
                painter.end()
                icon.setPixmap(pixmap)
                icon.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
                row.addWidget(icon)
                name = "Ground" if net.id == circuit.ground_node else "Node"
                text = QLabel(f'<span style="font-weight: 500;">{escape(net.id)} · {name}</span><br>{len(net.terminals)} connected terminals')
                text.setWordWrap(True)
                text.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
                row.addWidget(text, 1)
                button.setAccessibleName("Inspect node " + net.id)
                button.clicked.connect(lambda checked=False, node_id=net.id: self.node_requested.emit(node_id))
                node_layout.addWidget(button)
            column.addWidget(nodes)
        if component is not None:
            if getattr(self, "rc_preview_position", None) is not None:
                column.addWidget(text_label("Predicted values at the selected time", role="secondaryText"))
            column.addWidget(text_label("Electrical Properties", role="electricalHeading"))
            self.component_id = component.id
            self.title.setText(f"{component.id} · {COMPONENT_NAMES[component.type]}")
            self.selection_prompt.hide()
            self.close_button.show()
            self.close_button.setAccessibleName("Back to circuit overview")
            self.subtitle.setText(TYPE_SUBTITLES[component.type])
            self.subtitle.show()
            self.symbol_surface.show()
            icon_scene = QGraphicsScene()
            icon_scene.addItem(ComponentSymbol(component))
            pixmap = QPixmap(224, 160)
            pixmap.setDevicePixelRatio(4)
            pixmap.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            icon_scene.render(painter, QRectF(0, 0, 56, 40), QRectF(-64, -44, 128, 88))
            painter.end()
            self.symbol_icon.setPixmap(pixmap)
            primary_caption = PRIMARY_NAMES[component.type]
            if component.type not in ("switch", "button", "wire"):
                primary_caption += " · nominal"
            value = nominal_label(component)
            for prefix in (component.id + " = ", component.id + ": "):
                if value.startswith(prefix):
                    value = value[len(prefix):]
                    break
            for prefix in ("Vf = ", "Iph = "):
                if value.startswith(prefix):
                    value = value[len(prefix):]
                    break
            voltage = result.voltage_v if result and available(result.voltage_v) else None
            current = result.current_a if result and available(result.current_a) else None
            self.electrical_properties(
                column, content, primary_caption, value,
                "Voltage" if component.type == "voltage_source" else "Voltage drop",
                engineering(voltage, "V") if voltage is not None else "—",
                current_reading(current, self.current_display),
            )
            divider()
            purpose = text_label(COMPONENT_DESCRIPTIONS[component.type], content)
            purpose.setContentsMargins(0, 0, 0, 8)
            self.disclosure(column, "Purpose", purpose, (component.id, "purpose"))
            mixed_storage = self.overview_circuit and {"capacitor", "inductor"}.issubset({c.type for c in self.overview_circuit.components})
            if component.type in ("capacitor", "inductor") and mixed_storage:
                divider()
                model, reason = series_rlc(self.overview_circuit)
                if result is None:
                    model, reason = None, "Response unavailable until circuit checks pass."
                summary = QWidget(content)
                summary.setStyleSheet("background: transparent;")
                summary_layout = QVBoxLayout(summary)
                summary_layout.setContentsMargins(0, 0, 0, 8)
                summary_layout.setSpacing(8)
                if model is None:
                    summary_layout.addWidget(text_label(reason, role="secondaryText"))
                else:
                    summary_layout.addWidget(text_label(model.regime, role="sectionTitle"))
                    summary_layout.addWidget(text_label(f"Damping ratio: {model.damping_ratio:.4g}", role="secondaryText"))
                    summary_layout.addWidget(text_label(f"Preview window: 0–{engineering(model.duration_s, 's')}", role="secondaryText"))
                    if model.regime == "Underdamped":
                        frequency = math.sqrt((model.omega0-model.alpha)*(model.omega0+model.alpha)) / (2*math.pi)
                        summary_layout.addWidget(text_label(f"Oscillation frequency: {engineering(frequency, 'Hz')}", role="secondaryText"))
                    summary_layout.addWidget(text_label("Analytical series RLC step response. The preview window is not a guaranteed settling time.", role="secondaryText"))
                self.disclosure(column, "RLC Response", summary, (component.id, "rlc_summary"))
                if model is not None:
                    divider()
                    adapter = model.plot_model(component.id)
                    initial = component.parameters.get("initial_voltage_v" if component.type == "capacitor" else "initial_current_a", 0.0)
                    final = model.capacitor_sign * model.source.parameters["voltage_v"] if component.type == "capacitor" else 0.0
                    response = RCResponseWidget(adapter, initial, final, parent=content)
                    if getattr(self, "rc_time_requested", None) is not None:
                        response.slider.hide()
                        position = getattr(self, "rc_preview_position", None)
                        response.inspect_time(0 if position is None else position)
                    response.title.hide()
                    self.disclosure(column, "Predicted RLC Response", response, (component.id, "rlc_response"))
            elif component.type in ("capacitor", "inductor"):
                is_rl = component.type == "inductor"
                response_kind = "RL" if is_rl else "RC"
                divider()
                timing_body = QWidget(content)
                timing_body.setStyleSheet("background: transparent;")
                timing_layout = QVBoxLayout(timing_body)
                timing_layout.setContentsMargins(0, 0, 0, 8)
                timing_layout.setSpacing(12)
                timing, reason = (rl_timing if is_rl else rc_timing)(self.overview_circuit, component.id) if self.overview_circuit else (None, "Circuit unavailable.")
                if result is None:
                    timing, reason = None, "Timing is unavailable until circuit checks pass."
                if timing is not None:
                    formula = (f"τ = L/R = {engineering(timing.inductance_h, 'H')} / {engineering(timing.resistance_ohm, 'Ω')} = {engineering(timing.tau_s, 's')}"
                               if is_rl else f"τ = RC = {engineering(timing.resistance_ohm, 'Ω')} × {engineering(timing.capacitance_f, 'F')} = {engineering(timing.tau_s, 's')}")
                    timing_layout.addWidget(text_label(formula, role="secondaryText"))
                    final_voltage = getattr(self, "rl_final_current" if is_rl else "rc_final_voltage", None)
                    target_voltage = (current if is_rl else voltage) if final_voltage is None else final_voltage
                    phase = rc_response_phase(component.parameters.get("initial_current_a" if is_rl else "initial_voltage_v", 0.0), target_voltage) if target_voltage is not None else "transition"
                    progress_heading = {"charging": "Charged (%)", "discharging": "Discharged (%)", "transition": "Change (%)", "steady": "Change (%)"}[phase]
                    if is_rl:
                        progress_heading = {"charging": "Current rise", "discharging": "Current decay", "transition": "Current change", "steady": "Current change"}[phase]
                    table = QFrame(content)
                    table.setObjectName("rcTimingTable")
                    table.setStyleSheet("QFrame#rcTimingTable { background: #f7faf9; border: 1px solid #cbd7d4; border-radius: 10px; } QLabel { background: transparent; font-size: 12px; padding: 4px 0px; }")
                    table_layout = QGridLayout(table)
                    table_layout.setContentsMargins(8, 8, 8, 8)
                    table_layout.setHorizontalSpacing(8)
                    table_layout.setVerticalSpacing(0)
                    for col, heading in enumerate(("Time", "Elapsed", progress_heading)):
                        label = text_label(heading)
                        label.setWordWrap(False)
                        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                        label.setStyleSheet("font-size: 12px; font-weight: 500; color: #42447a; background: transparent; padding: 4px 0px;")
                        table_layout.addWidget(label, 0, col)
                        table_layout.setColumnStretch(col, 2 if col == 2 else 1)
                        if col == 2:
                            label.ensurePolished()
                            table_layout.setColumnMinimumWidth(col, label.sizeHint().width())
                    for multiple in range(1, 6):
                        values = (f"{multiple}τ", engineering(multiple * timing.tau_s, "s"),
                                  f"{0 if phase == 'steady' else 100 * (1 - math.exp(-multiple)):.1f}%")
                        for col, value in enumerate(values):
                            cell = text_label(value)
                            cell.setAlignment(Qt.AlignmentFlag.AlignCenter)
                            table_layout.addWidget(cell, multiple, col)
                    timing_layout.addWidget(table)
                    timing_layout.addWidget(text_label("Percentage of the transition completed toward the final current." if is_rl else "Percentage of the transition completed toward the final voltage.", role="secondaryText"))
                else:
                    timing_layout.addWidget(text_label("—", role="metricReading"))
                    timing_layout.addWidget(text_label(reason, role="secondaryText"))
                self.disclosure(column, response_kind + " Timing", timing_body, (component.id, "rc_timing"))
                if timing is not None and (current if is_rl else voltage) is not None:
                    divider()
                    final_voltage = getattr(self, "rl_final_current" if is_rl else "rc_final_voltage", None)
                    response = RCResponseWidget(
                        timing, component.parameters.get("initial_current_a" if is_rl else "initial_voltage_v", 0.0),
                        (current if is_rl else voltage) if final_voltage is None else final_voltage,
                        initial_assumed=("initial_current_a" if is_rl else "initial_voltage_v") not in component.parameters, parent=content,
                    )
                    if getattr(self, "rc_time_requested", None) is not None:
                        response.slider.hide()
                        position = getattr(self, "rc_preview_position", None)
                        response.inspect_time(0 if position is None else position)
                    response.title.hide()
                    self.disclosure(column, "Predicted " + response_kind + " Response", response, (component.id, "rc_response"))
        column.addStretch()
        old_position = self.scroll.verticalScrollBar().value()
        old = self.scroll.takeWidget()
        if old:
            old.deleteLater()
        self.scroll.setWidget(content)
        self.header_timer.start(0)
        if previous_id == self.component_id:
            self.scroll.verticalScrollBar().setValue(old_position)
