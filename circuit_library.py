"""Scrollable library cards using the existing circuit renderer for previews."""
from PySide6.QtCore import Qt, Signal, QRectF
from PySide6.QtGui import QPixmap, QPainter, QColor
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel, QPushButton, QScrollArea, QGraphicsScene, QGraphicsDropShadowEffect, QSizePolicy
from topology import parse_topology
from schematic import render_circuit, ResultBox
from components import COMPONENT_NAMES
from circuit_safety import assess_circuit


class CircuitLibraryPage(QWidget):
    circuit_requested = Signal(str)
    build_requested = Signal(str)
    delete_requested = Signal(str)

    def __init__(self, parent=None, *, title="Circuit Library", empty_message="No circuits are available yet.", validate_builds=False):
        super().__init__(parent)
        self.setObjectName("circuitLibraryPage")
        self.setStyleSheet("""
            QWidget#circuitLibraryPage { background: #eff5f3; border: none; border-radius: 14px; }
            QFrame#libraryCard { background: white; border: none; border-radius: 12px; }
            QLabel { background: transparent; }
            QPushButton#openLibraryCircuit { background: #e7e3f3; color: #42447a; border: none; border-radius: 8px; padding: 10px 16px; }
            QPushButton#openLibraryCircuit:hover:enabled { background: #d6d6e0; }
            QPushButton#openLibraryCircuit:disabled { background: #f1f3f2; color: #9ba4a1; }
        """)
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(18)
        shadow.setOffset(0, 0)
        shadow.setColor(QColor(26, 49, 55, 65))
        self.setGraphicsEffect(shadow)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        self.validate_builds = validate_builds
        self.empty_message = empty_message
        heading = QLabel(title)
        heading.setStyleSheet("font-family: 'Space Grotesk'; font-size: 18px; font-weight: 600;")
        layout.addWidget(heading)
        self.summary = QLabel("Browse example circuits and open one to explore its connections.")
        self.summary.setWordWrap(True)
        summary_row = QHBoxLayout()
        summary_row.setSpacing(12)
        summary_row.setContentsMargins(0, 0, 14, 0)
        summary_row.addWidget(self.summary, 1)
        self.circuit_count = QLabel()
        self.circuit_count.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.circuit_count.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.circuit_count.setStyleSheet("background: #ffffff; color: #42447a; border-radius: 10px; padding: 6px 12px; font-weight: 600;")
        summary_row.addWidget(self.circuit_count)
        layout.addLayout(summary_row)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet("QScrollArea { border: none; background: transparent; } QScrollBar:vertical { width: 6px; }")
        layout.addWidget(self.scroll, 1)
        self.records = []
        self.open_buttons = {}
        self.set_records([])

    def set_records(self, records):
        self.records = list(records)
        self.open_buttons = {}
        self.summary.setText("Select Open Circuit to view a schematic.")
        self.circuit_count.setText(f"{len(records)} circuit" + ("" if len(records) == 1 else "s"))
        content = QWidget(self.scroll.viewport())
        content.setObjectName("libraryContent")
        content.setStyleSheet("QWidget#libraryContent { background: transparent; }")
        column = QVBoxLayout(content)
        column.setContentsMargins(0, 0, 8, 0)
        column.setSpacing(12)
        for data in records:
            card = QFrame(content)
            card.setObjectName("libraryCard")
            card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
            row = QHBoxLayout(card)
            row.setContentsMargins(16, 16, 16, 16)
            row.setSpacing(20)
            preview = QLabel()
            preview.setFixedSize(220, 124)
            preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
            preview.setStyleSheet("background: #fafafa; border-radius: 8px;")
            build_allowed = False
            build_reason = "This circuit could not be validated. Open it to review its data."
            try:
                circuit = parse_topology(data)
                report = assess_circuit(circuit) if self.validate_builds and circuit.components else None
                build_allowed = bool(circuit.components) and (report is None or report.allowed)
                if not circuit.components:
                    build_reason = "This circuit is empty. Add a circuit before building from it."
                elif report is not None and not report.allowed:
                    build_reason = "This saved circuit has unresolved issues. To correct it, choose New Circuit, rebuild it on the board, upload it, and save the corrected circuit.\n\nIssues:\n" + "\n".join("• " + issue.message for issue in report.issues)
                if not circuit.components:
                    preview.setText("Empty circuit")
                else:
                    scene = QGraphicsScene()
                    render_circuit(scene, circuit)
                    for item in scene.items():
                        if isinstance(item, ResultBox):
                            item.hide()
                    bounds = QRectF()
                    for item in scene.items():
                        if item.isVisible():
                            bounds = bounds.united(item.sceneBoundingRect())
                    pixmap = QPixmap(440, 248)
                    pixmap.setDevicePixelRatio(2)
                    pixmap.fill(Qt.GlobalColor.transparent)
                    painter = QPainter(pixmap)
                    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                    scene.render(painter, QRectF(8, 8, 204, 108), bounds.adjusted(-12, -12, 12, 12))
                    painter.end()
                    preview.setPixmap(pixmap)
            except (ValueError, KeyError, TypeError):
                preview.setText("Preview unavailable")
            row.addWidget(preview, 0, Qt.AlignmentFlag.AlignTop)
            details = QVBoxLayout()
            details.setSpacing(8)
            title = QLabel(data['name'])
            title.setWordWrap(True)
            title.setStyleSheet("font-family: 'DM Sans'; font-size: 16px; font-weight: 600;")
            details.addWidget(title)
            counts = QLabel(f"{len(data.get('components', []))} components · {len(data.get('nets', []))} nodes")
            counts.setStyleSheet("color: #42447a;")
            details.addWidget(counts)
            kinds = list(dict.fromkeys(COMPONENT_NAMES.get(c.get('type'), c.get('type', 'Component')) for c in data.get('components', [])))
            description = QLabel(data.get('description') or ', '.join(kinds) or 'Waiting for circuit topology')
            description.setWordWrap(True)
            description.setStyleSheet("color: #596e6b;")
            details.addWidget(description)
            details.addSpacing(4)
            details.setAlignment(Qt.AlignmentFlag.AlignTop)
            button = QPushButton("Open Circuit")
            button.setObjectName("openLibraryCircuit")
            button.setAccessibleName("Open " + data['name'])
            button.clicked.connect(lambda checked=False, name=data['name']: self.circuit_requested.emit(name))
            actions = QHBoxLayout()
            actions.addWidget(button)
            build_button = QPushButton("Build This Circuit")
            build_button.setObjectName("openLibraryCircuit")
            build_button.setAccessibleName("Build " + data['name'])
            build_button.setEnabled(build_allowed)
            if not build_allowed:
                build_button.setProperty("allowTooltip", True)
                build_button.setToolTip(build_reason)
            build_button.clicked.connect(lambda checked=False, name=data['name']: self.build_requested.emit(name))
            actions.addWidget(build_button)
            if self.validate_builds:
                delete_button = QPushButton("Delete")
                delete_button.setObjectName("openLibraryCircuit")
                delete_button.setAccessibleName("Delete " + data['name'])
                delete_button.clicked.connect(lambda checked=False, name=data['name']: self.delete_requested.emit(name))
                actions.addWidget(delete_button)
            actions.addStretch()
            details.addLayout(actions)
            self.open_buttons[data['name']] = button
            row.addLayout(details, 1)
            column.addWidget(card)
        if not records:
            column.addWidget(QLabel(self.empty_message))
        column.addStretch()
        old = self.scroll.takeWidget()
        if old:
            old.deleteLater()
        self.scroll.setWidget(content)
