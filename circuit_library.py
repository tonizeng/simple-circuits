"""Scrollable library cards using the existing circuit renderer for previews."""
from PySide6.QtCore import Qt, Signal, QRectF
from PySide6.QtGui import QPixmap, QPainter, QColor
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel, QPushButton, QScrollArea, QGraphicsScene, QGraphicsDropShadowEffect
from topology import parse_topology
from schematic import render_circuit, ResultBox
from components import COMPONENT_NAMES


class CircuitLibraryPage(QWidget):
    circuit_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("circuitLibraryPage")
        self.setStyleSheet("""
            QWidget#circuitLibraryPage { background: #f7f7f9; border: 1.2px solid #cccccc; border-radius: 14px; }
            QFrame#libraryCard { background: white; border: 1px solid #e2e2e7; border-radius: 12px; }
            QLabel { background: transparent; }
            QPushButton#openLibraryCircuit { background: #e2e2e7; color: #42447a; border: none; border-radius: 8px; padding: 10px 16px; }
            QPushButton#openLibraryCircuit:hover { background: #d6d6e0; }
        """)
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(14)
        shadow.setOffset(0, 0)
        shadow.setColor(QColor(0, 0, 0, 28))
        self.setGraphicsEffect(shadow)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        heading = QLabel("Circuit Library")
        heading.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(heading)
        self.summary = QLabel("Browse example circuits and open one to explore its connections.")
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
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
        self.summary.setText(f"{len(records)} circuits · Select Open circuit to view a schematic.")
        content = QWidget(self.scroll.viewport())
        content.setObjectName("libraryContent")
        content.setStyleSheet("QWidget#libraryContent { background: transparent; }")
        column = QVBoxLayout(content)
        column.setContentsMargins(0, 0, 8, 0)
        column.setSpacing(12)
        for data in records:
            card = QFrame(content)
            card.setObjectName("libraryCard")
            row = QHBoxLayout(card)
            row.setContentsMargins(16, 16, 16, 16)
            row.setSpacing(20)
            preview = QLabel()
            preview.setFixedSize(220, 124)
            preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
            preview.setStyleSheet("background: #fafafa; border-radius: 8px;")
            try:
                circuit = parse_topology(data)
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
            row.addWidget(preview)
            details = QVBoxLayout()
            details.setSpacing(8)
            title = QLabel(data['name'])
            title.setWordWrap(True)
            title.setStyleSheet("font-size: 16px; font-weight: 500;")
            details.addWidget(title)
            counts = QLabel(f"{len(data.get('components', []))} components · {len(data.get('nets', []))} nodes")
            counts.setStyleSheet("color: #42447a;")
            details.addWidget(counts)
            kinds = list(dict.fromkeys(COMPONENT_NAMES.get(c.get('type'), c.get('type', 'Component')) for c in data.get('components', [])))
            description = QLabel(data.get('description') or ', '.join(kinds))
            description.setWordWrap(True)
            description.setStyleSheet("color: #606060;")
            details.addWidget(description)
            details.addStretch()
            button = QPushButton("Open circuit")
            button.setObjectName("openLibraryCircuit")
            button.setAccessibleName("Open " + data['name'])
            button.clicked.connect(lambda checked=False, name=data['name']: self.circuit_requested.emit(name))
            details.addWidget(button, 0, Qt.AlignmentFlag.AlignLeft)
            self.open_buttons[data['name']] = button
            row.addLayout(details, 1)
            column.addWidget(card)
        if not records:
            column.addWidget(QLabel("No circuits are available yet."))
        column.addStretch()
        old = self.scroll.takeWidget()
        if old:
            old.deleteLater()
        self.scroll.setWidget(content)
