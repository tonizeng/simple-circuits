"""App-wide reading guidance and terminology; no circuit mutations."""
from pathlib import Path
from PySide6.QtCore import Qt, QSize, QTimer
from PySide6.QtSvgWidgets import QSvgWidget
from formula_reference import FORMULA_EQUATIONS
from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QListWidget, QStackedWidget, QScrollArea, QWidget

def guide_title(value):
    minor_words = {"and", "or", "the", "of", "to", "in", "for", "with", "by", "as", "at", "from"}
    words = value.split()
    return " ".join(word.lower() if index > 0 and word.lower() in minor_words
                    else word[:1].upper() + word[1:]
                    for index, word in enumerate(words))


WORKFLOW_TOPICS = (
    ("Building from Scratch", "Start with New Circuit and build your own circuit using the physical toy. Press the board button to upload its topology, run safety checks, and display the schematic and theoretical values."),
    ("Viewing Circuit", "Open a circuit from My Circuits or Circuit Library to inspect its saved design and calculated values. Viewing does not compare it with the physical toy or change the saved circuit."),
    ("Building from Reference", "Select Build Circuit to recreate the open circuit on the physical toy. My Circuits contains your saved circuits; Circuit Library contains the provided examples. Upload your build using the board button to compare its components and connections with the reference and run safety checks on the uploaded circuit."),
    ("Saving circuits", "Save keeps the current name and updates your circuit. Use the pencil to rename it. Save As creates a separate entry in My Circuits and checks the name as you type. Library examples can only be copied with Save As. In reference mode, Save As saves the uploaded build, not the reference."),
    ("Returning to viewing", "Back to View Mode stops comparison and returns to the saved reference. It does not replace the reference with the physical build or save a new circuit."),
    ("Build matching and safety", "Matching the reference and passing safety checks are separate results. Reference mode requires both before power approval; scratch mode requires safety checks only. The reference remains unchanged during comparison. The firmware controls physical power; hardware upload integration is not connected yet."),
)

CIRCUIT_TOPICS = (
    ("Components and terminals", "V1, R1, and LED1 identify individual components. The number beside a component connection is its terminal number. Most components use terminals 1 and 2; a potentiometer uses terminal 3 for its wiper."),
    ("Nodes and connections", "A node groups electrically connected terminals. All terminals on that node have the same voltage, measured relative to ground. Junction dots mark joins."),
    ("Voltage and polarity", "V = V(1) − V(2), where 1 and 2 are terminal numbers. Positive means terminal 1 is at a higher voltage; negative means terminal 2 is higher. The source readout says Voltage; other components say Voltage drop."),
    ("Current direction", "Arrows + magnitude mode shows positive current magnitudes with arrows for conventional current direction. Signed current mode hides the arrows: positive means terminal 1 → 2; negative means terminal 2 → 1. Choose the display mode in Settings. Both use the same calculated results."),
    ("Ground reference", "Ground is the node chosen as 0 V. Every node voltage is relative to this reference. A component’s voltage is the difference between the voltages at its terminals."),
    ("Unavailable values and power approval", "A dash (—) means a calculated value is unavailable. If any warning or error exists, the app hides all calculated results and does not approve power. Power approved means the circuit validation checks passed."),
    ("What the calculations cover", "Main results describe settled DC: ideal capacitors are open circuits and ideal inductors are shorts. Supported RC, RL and series RLC circuits also offer predicted time-response previews. Hardware current limiting and turn-off spikes are not simulated."),
)

NAVIGATION_TOPICS = (
    ("Selecting items", "Select a component or node in the schematic or Circuit Overview to view its details."),
    ("Colours and fault symbols", "Selection uses one shared colour for components and nodes, purple by default. Current arrows are blue by default. Settings lets you change these colours. Green status means checks passed; red indicates an error and amber indicates a warning. Fault symbols remain beside affected locations in the schematic."),
    ("Circuit Status", "Circuit Status lists errors and warnings. Click a located issue to reveal its affected component or connection."),
    ("Zoom and labels", "Use the mouse wheel or zoom toolbar to zoom within the schematic. Fit brings the circuit into view. Enable Pan in the toolbar to drag with the left mouse button, or drag with the middle mouse button at any time. Show Labels controls node names and terminal numbers; component values and fault symbols remain visible."),
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
        self.resize(820, 700)
        self.setMinimumSize(700, 480)
        self.setStyleSheet("""
            QDialog { background: #f7f7f9; }
            QLabel { background: transparent; color: #222222; font-size: 14px; }
            QLabel#guideTopic { font-family: 'DM Sans'; font-weight: 600; color: #42447a; }
            QPushButton#guidePageArrow { background: #e7e3f3; color: #42447a; border: none; border-radius: 8px; font-size: 22px; padding: 0; }
            QPushButton#guidePageArrow:hover { background: #dcd6ec; }
            QPushButton#guidePageArrow:disabled { background: #eff1f0; color: #adb5b2; }
            QListWidget#guideSections { background: #f1f5f3; border: none; border-radius: 10px; outline: none; }
            QListWidget#guideSections::item { padding: 10px; border: none; border-radius: 8px; color: #222222; }
            QListWidget#guideSections::item:hover { background: #e9eeeb; }
            QListWidget#guideSections::item:selected { background: #e7e3f3; color: #42447a; }
            QStackedWidget#guidePages { background: white; border: none; }
            QScrollArea { background: white; border: none; }
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        body = QHBoxLayout()
        body.setSpacing(12)
        self.section_list = QListWidget()
        self.section_list.setObjectName("guideSections")
        self.section_list.setAccessibleName("Circuit Guide sections")
        self.section_list.setFixedWidth(216)
        self.section_list.setWordWrap(True)
        self.section_list.setTextElideMode(Qt.TextElideMode.ElideNone)
        self.section_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        body.addWidget(self.section_list)
        self.pages = QStackedWidget()
        self.pages.setObjectName("guidePages")
        sections = (
            ("Getting Started", self.topic_page(WORKFLOW_TOPICS)),
            ("Understanding the circuit", self.topic_page(CIRCUIT_TOPICS)),
            ("Navigation", self.topic_page(NAVIGATION_TOPICS)),
            ("Terminology", self.topic_page(TERMS)),
            ("Formulas", self.formulas_page()),
        )
        for title, page in sections:
            self.section_list.addItem(guide_title(title))
            self.section_list.item(self.section_list.count() - 1).setSizeHint(QSize(196, 60))
            self.pages.addWidget(page)
        self.section_list.currentRowChanged.connect(self.pages.setCurrentIndex)
        self.pages.currentChanged.connect(self.section_list.setCurrentRow)
        page_column = QVBoxLayout()
        page_column.addWidget(self.pages, 1)
        body.addLayout(page_column, 1)
        layout.addLayout(body, 1)
        footer = QHBoxLayout()
        footer.addStretch()
        self.previous_page = QPushButton("←")
        self.next_page = QPushButton("→")
        for button, label in ((self.previous_page, "Previous guide page"), (self.next_page, "Next guide page")):
            button.setObjectName("guidePageArrow")
            button.setAccessibleName(label)
            button.setFixedSize(44, 36)
            footer.addWidget(button)
        footer.addStretch()
        page_column.addLayout(footer)
        self.previous_page.clicked.connect(lambda: self.section_list.setCurrentRow(self.pages.currentIndex() - 1))
        self.next_page.clicked.connect(lambda: self.section_list.setCurrentRow(self.pages.currentIndex() + 1))
        self.pages.currentChanged.connect(self.update_page_arrows)
        self.section_list.setCurrentRow(0)
        self.update_page_arrows()

    def update_page_arrows(self, index=None):
        self.previous_page.setEnabled(self.pages.currentIndex() > 0)
        self.next_page.setEnabled(self.pages.currentIndex() < self.pages.count() - 1)

    def show_formulas(self, component_type=None):
        self.section_list.setCurrentRow(4)
        section = {
            "voltage_source": "DC Voltage Source",
            "resistor": "Resistors and Photoresistors — Ohm’s Law",
            "photoresistor": "Resistors and Photoresistors — Ohm’s Law",
            "led": "LED or Diode Series Resistor",
            "diode": "LED or Diode Series Resistor",
            "potentiometer": "Potentiometer",
            "capacitor": "Capacitor",
            "inductor": "Inductor",
        }.get(component_type, "Nodal Analysis")
        anchor = self.formula_anchors[section]
        self.formulas_scroll.widget().layout().activate()
        QTimer.singleShot(0, lambda: self.formulas_scroll.verticalScrollBar().setValue(max(0, anchor.y() - 16)))

    def formulas_page(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = QWidget()
        content.setStyleSheet("background: white;")
        column = QVBoxLayout(content)
        column.setContentsMargins(16, 16, 16, 16)
        column.setSpacing(10)
        self.formula_anchors = {}
        self.formulas_scroll = scroll
        def text(value, heading=False):
            label = QLabel(guide_title(value) if heading else value)
            label.setWordWrap(True)
            label.setTextFormat(Qt.TextFormat.PlainText)
            if heading:
                label.setObjectName("guideTopic")
                self.formula_anchors[value] = label
            column.addWidget(label)
        text("Nodal Analysis", True)
        text("Nodal analysis finds the voltage at each node relative to ground. Once those voltages are known, use the voltage difference across each component to calculate its current.")
        text("1. Choose a ground node and label it 0 V. Label the other node voltages, such as Vₐ and Vᵦ.")
        text("2. Write each resistor current as (Vₐ − Vᵦ)/R, choosing a consistent direction.")
        text("3. Apply Kirchhoff’s current law at each unknown node: total current entering equals total current leaving.")
        text("4. Solve the simultaneous equations, then calculate component voltage drops and currents. A negative answer means the actual polarity or current direction is opposite to your chosen reference.")
        text("The app uses Modified Nodal Analysis (MNA), which adds unknown source currents so voltage sources can be included in the same equation system. The formulas below are for hand calculations, rather than solver implementation.")
        text("Use volts (V), amperes (A), ohms (Ω), farads (F) and henries (H). These are general references; apply the stated assumptions.")
        groups = (
            ("Kirchhoff’s Laws", "Kirchhoff’s laws", None, "At a node, signed currents sum to zero. Around a closed loop, signed voltage changes sum to zero. Use consistent directions and polarities."),
            ("Resistors and Photoresistors — Ohm’s Law", "Ohm’s law", None, "V is the voltage across the resistance R, and I is its current. A photoresistor follows the same relationship for its resistance at that light level. Division requires a nonzero denominator."),
            ("Series Resistors", "Series resistors", None, "Use when resistors carry the same current with no branch at their joining nodes."),
            ("Parallel Resistors", "Parallel resistors", None, "Use when resistors connect across the same two nodes and share the same voltage. The second expression is the shortcut for two resistors."),
            ("Voltage Divider", "Voltage divider", None, "Two series resistors span Vᵢₙ. Take Vₒᵤₜ across R₂. This expression assumes the output is unloaded."),
            ("DC Voltage Source", "DC voltage source", None, "V₁ and V₂ are the source terminal voltages; Vₛ is the supplied voltage. If the negative terminal is ground, the positive node voltage equals Vₛ."),
            ("LED or Diode Series Resistor", "LED resistor sizing", None, "For a forward-conducting LED or diode with a known drop Vꜰ, choose a series resistor using supply voltage Vₛ and desired current I. This assumes Vₛ > Vꜰ and uses a constant-drop approximation."),
            ("Potentiometer", "Potentiometer track", None, "R is total track resistance, x is wiper position from 0 to 1, and terminal 3 is the wiper. For an unloaded potentiometer divider, also use the voltage-divider formula."),
            ("Capacitor", "Capacitors", None, "Q is stored charge, C is capacitance, and V₀ is initial voltage. Current enters the positive-voltage terminal. At settled DC, capacitor current is zero; during charging, voltage changes over time."),
            ("Inductor", "Inductors", None, "L is inductance and I₀ is initial current. Current enters the positive-voltage terminal. At settled DC, ideal inductor voltage is zero; during changes, voltage depends on how quickly current changes."),
        )
        for title, key, selected, explanation in groups:
            column.addSpacing(12)
            text(title, True)
            for asset, expression, accessible in FORMULA_EQUATIONS[key]:
                if selected and asset not in selected:
                    continue
                path = Path(__file__).resolve().parent / "assets" / "formulas" / (asset + ".svg")
                equation = QSvgWidget(str(path))
                equation.setAccessibleName(accessible)
                equation.setObjectName("guideEquation")
                native = equation.renderer().defaultSize()
                scale = min(1.0, 400 / max(1, native.width()))
                equation.setFixedSize(max(1, round(native.width() * scale)), max(1, round(native.height() * scale)))
                column.addWidget(equation, 0, Qt.AlignmentFlag.AlignHCenter)
            text(explanation)
        column.addStretch()
        scroll.setWidget(content)
        return scroll

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
            heading = QLabel(guide_title(title))
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
