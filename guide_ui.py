"""App-wide reading guidance and terminology; no circuit mutations."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QTabWidget, QScrollArea, QWidget

CIRCUIT_TOPICS = (
    ("Components and terminals", "V1, R1, and LED1 identify individual components. The number beside a component connection is its terminal number. Most components use terminals 1 and 2; a potentiometer uses terminal 3 for its wiper."),
    ("Nodes and connections", "A node groups electrically connected terminals. All terminals on that node have the same voltage, measured relative to ground. Junction dots mark joins."),
    ("Voltage and polarity", "V = V(1) − V(2), where 1 and 2 are terminal numbers. Positive means terminal 1 is at a higher voltage; negative means terminal 2 is higher. The source readout says Voltage; other components say Voltage drop."),
    ("Current direction", "Arrows + magnitude mode shows positive current magnitudes with arrows for conventional current direction. Signed current mode hides the arrows: positive means terminal 1 → 2; negative means terminal 2 → 1. Choose the display mode in Settings. Both use the same calculated results."),
    ("Ground reference", "Ground is the node chosen as 0 V. Every node voltage is relative to this reference. A component’s voltage is the difference between the voltages at its terminals."),
    ("Unavailable values and power approval", "A dash (—) means a calculated value is unavailable. If any warning or error exists, the app hides all calculated results and does not approve power. Power approved means the circuit validation checks passed."),
    ("What the calculations cover", "Displayed results describe settled DC conditions. Ideal capacitors act as open circuits and ideal inductors as shorts. Startup current, charging waveforms, and turn-off voltage spikes are not simulated."),
)

NAVIGATION_TOPICS = (
    ("Selecting items", "Select a component or node in the schematic or Circuit Overview to view its details."),
    ("Colours and fault symbols", "Selection uses one shared colour for components and nodes, purple by default. Current arrows are blue by default. Settings lets you change these colours. Green status means checks passed; red indicates an error and amber indicates a warning. Fault symbols remain beside affected locations in the schematic."),
    ("Circuit Status", "Circuit Status lists errors and warnings. Click a located issue to reveal its affected component or connection."),
    ("Zoom and labels", "Use the mouse wheel or zoom toolbar to zoom within the schematic. Fit brings the circuit into view. Enable Pan in the toolbar to drag with the left mouse button, or drag with the middle mouse button at any time. Show labels controls node names and terminal numbers; component values and fault symbols remain visible."),
)

TERMS = (
    ("Component", "An electrical element such as a resistor, source, LED, switch, or capacitor."),
    ("Terminal", "A component connection point, identified by a number such as 1 or 2."),
    ("Node", "A set of electrically connected terminals sharing one voltage."),
    ("Ground", "The circuit’s chosen 0 V reference."),
    ("Voltage", "Electrical potential difference between two points, expressed in volts (V)."),
    ("Source voltage", "The voltage supplied between a source’s positive and negative terminals, expressed in volts (V)."),
    ("Voltage drop", "The signed voltage difference across a component, read from terminal 1 to terminal 2 in this app."),
    ("Current", "Flow of electric charge, expressed in amperes (A). The app displays either magnitude with direction arrows or signed current, depending on Settings."),
    ("Conventional current", "The direction positive charge would flow. Electron flow in a metal is in the opposite direction."),
    ("Resistance", "Opposition to current, expressed in ohms (Ω)."),
    ("Forward voltage (Vf)", "The forward-voltage parameter used for an LED or diode. The app’s fixed-drop model uses this voltage while the junction conducts."),
    ("Nominal", "A specified component or source value. It is distinct from a calculated result or a live measurement."),
    ("Calculated", "Predicted by the application’s circuit model from the supplied values and connections."),
    ("Measured", "Obtained from a physical sensor. A calculated result is not a physical measurement."),
    ("Open circuit", "A broken or intentionally open conducting path. An open switch can be intentional; a disconnected terminal may require attention."),
    ("Short circuit", "An unintended path with very low resistance. In the app’s ideal model, directly joining the supply terminals creates a supply short."),
    ("Steady state", "The settled condition after changes have died away. The app currently calculates DC steady state."),
    ("MNA", "Modified Nodal Analysis: the method that combines node current balance and component equations to calculate the circuit results."),
)


class CircuitGuideDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Circuit Guide")
        self.setModal(False)
        self.resize(540, 600)
        self.setMinimumSize(360, 360)
        self.setStyleSheet("""
            QDialog { background: #f7f7f9; }
            QLabel { background: transparent; color: #222222; font-size: 14px; }
            QLabel#guideTopic { font-weight: 500; color: #42447a; }
            QTabWidget::pane { border: 1px solid #dedee5; background: white; border-radius: 8px; }
            QTabBar::tab { background: transparent; padding: 10px 14px; border: none; }
            QTabBar::tab:selected { color: #42447a; background: #e2e2e7; border-radius: 6px; }
            QScrollArea { background: white; border: none; }
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        self.tabs = QTabWidget()
        self.tabs.setAccessibleName("Circuit Guide sections")
        self.tabs.addTab(self.topic_page(CIRCUIT_TOPICS), "Understanding the circuit")
        self.tabs.addTab(self.topic_page(NAVIGATION_TOPICS), "Navigation")
        self.tabs.addTab(self.topic_page(TERMS), "Terminology")
        layout.addWidget(self.tabs)

    def topic_page(self, topics):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = QWidget()
        content.setObjectName("guideContent")
        content.setStyleSheet("QWidget#guideContent { background: white; }")
        column = QVBoxLayout(content)
        column.setContentsMargins(16, 16, 16, 16)
        column.setSpacing(8)
        for title, explanation in topics:
            heading = QLabel(title)
            heading.setObjectName("guideTopic")
            heading.setWordWrap(True)
            column.addWidget(heading)
            body = QLabel(explanation)
            body.setTextFormat(Qt.TextFormat.PlainText)
            body.setWordWrap(True)
            column.addWidget(body)
            column.addSpacing(12)
        column.addStretch()
        scroll.setWidget(content)
        return scroll
