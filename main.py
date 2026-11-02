"""Barebones circuit desktop UI. Run with: python main.py."""

import sys
import argparse
import sqlite3
import json
from pathlib import Path
from dataclasses import replace

from PySide6.QtCore import Qt, QSize, QRectF, QUrl, QPoint, QSettings
from PySide6.QtSvgWidgets import QSvgWidget
from PySide6.QtGui import QFont, QFontDatabase, QPainter, QPixmap, QDesktopServices, QColor, QIcon
from topology import parse_topology, TopologyError
from schematic import render_circuit, ComponentSymbol, DEFAULT_HIGHLIGHT_COLORS
from components import COMPONENT_NAMES, COMPONENT_DESCRIPTIONS
from database import CircuitDatabase
from formula_reference import FORMULA_TOPICS, FORMULA_EQUATIONS, FORMULA_CAPTIONS
from simulation import solve_dc
from falstad import falstad_url, FalstadExportError
from PySide6.QtWidgets import (
    QApplication, QFrame, QGraphicsScene, QGraphicsView, QHBoxLayout,
    QLabel, QLineEdit, QMainWindow, QMessageBox, QPushButton,
    QVBoxLayout, QWidget, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QDialog, QListWidget, QDialogButtonBox, QScrollArea, QTabWidget, QColorDialog, QFormLayout,
)


class GuideSection(QFrame):
    """A keyboard-accessible guide topic with a collapsible explanation."""

    def __init__(self, title, text, equations=()):
        super().__init__()
        self.setObjectName("guideSection")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.toggle = QPushButton("▸ " + title)
        self.toggle.setObjectName("guideDisclosure")
        self.toggle.setCheckable(True)
        self.toggle.setAccessibleName(title)
        if equations:
            self.explanation = QWidget()
            content = QVBoxLayout(self.explanation)
            content.setContentsMargins(10, 12, 10, 12)
            content.setSpacing(12)
            for name, _, accessible_text in equations:
                if name in FORMULA_CAPTIONS:
                    content.addWidget(QLabel(FORMULA_CAPTIONS[name]))
                path = Path(__file__).resolve().parent / "assets" / "formulas" / (name + ".svg")
                equation_widget = QSvgWidget(str(path))
                if not equation_widget.renderer().isValid():
                    raise RuntimeError(f"Could not load formula: {path}")
                native = equation_widget.renderer().defaultSize()
                scale = min(1.0, 180 / max(1, native.width()))
                equation_widget.setFixedSize(round(native.width() * scale), round(native.height() * scale))
                equation_widget.setAccessibleName(accessible_text)
                equation_widget.setStyleSheet("background: transparent;")
                content.addWidget(equation_widget, 0, Qt.AlignmentFlag.AlignLeft)
            notes = QLabel(text)
            notes.setWordWrap(True)
            notes.setTextFormat(Qt.TextFormat.RichText)
            content.addWidget(notes)
        else:
            self.explanation = QLabel(text)
            self.explanation.setWordWrap(True)
            self.explanation.setTextFormat(Qt.TextFormat.RichText)
            self.explanation.setContentsMargins(10, 10, 10, 12)
        self.explanation.hide()
        layout.addWidget(self.toggle)
        layout.addWidget(self.explanation)
        def expand(checked):
            self.toggle.setText(("▾ " if checked else "▸ ") + title)
            self.explanation.setVisible(checked)
        self.toggle.toggled.connect(expand)


class ComponentRowButton(QPushButton):
    """Share hover styling across both cells of a component row."""

    def __init__(self, text=""):
        super().__init__(text)
        self.row_buttons = []

    def set_row_hover(self, active):
        for button in self.row_buttons:
            button.setProperty("rowHovered", active)
            button.style().unpolish(button)
            button.style().polish(button)
            button.update()

    def enterEvent(self, event):
        super().enterEvent(event)
        self.set_row_hover(True)

    def leaveEvent(self, event):
        super().leaveEvent(event)
        self.set_row_hover(False)


class SchematicView(QGraphicsView):
    """Canvas-only zoom, with cursor anchoring and middle-button panning."""

    def __init__(self, scene):
        super().__init__(scene)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.NoAnchor)
        self.pan_position = None
        self.zoom_controls = QFrame(self.viewport())
        controls = QHBoxLayout(self.zoom_controls)
        controls.setContentsMargins(0, 0, 0, 0)
        controls.setSpacing(4)
        for text, tip, callback in (
            ("−", "Zoom out (−)", lambda: self.zoom_by(1 / 1.2)),
            ("+", "Zoom in (+)", lambda: self.zoom_by(1.2)),
            ("Fit", "Fit circuit (0)", self.fit_circuit),
        ):
            button = QPushButton(text)
            button.setToolTip(tip)
            button.setAccessibleName(tip)
            button.setStyleSheet("padding: 4px 8px; font-size: 14px;")
            button.clicked.connect(callback)
            controls.addWidget(button)
        self.zoom_controls.adjustSize()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "zoom_controls"):
            self.zoom_controls.move(max(8, self.viewport().width() - self.zoom_controls.width() - 10), 10)
            self.zoom_controls.raise_()

    def zoom_by(self, factor, position=None):
        current = self.transform().m11()
        target = max(0.05, min(8.0, current * factor))
        position = position if position is not None else self.viewport().rect().center()
        before = self.mapToScene(position)
        self.scale(target / current, target / current)
        after = self.mapToScene(position)
        delta = after - before
        self.translate(delta.x(), delta.y())

    def wheelEvent(self, event):
        delta = event.angleDelta().y() or event.pixelDelta().y()
        if delta:
            self.zoom_by(1.2 ** (max(-600, min(600, delta)) / 120), event.position().toPoint())
        event.accept()

    def fit_circuit(self):
        if self.scene().items():
            self.fitInView(self.scene().sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
            self.centerOn(self.scene().sceneRect().center())

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Plus, Qt.Key.Key_Equal):
            self.zoom_by(1.2)
        elif event.key() == Qt.Key.Key_Minus:
            self.zoom_by(1 / 1.2)
        elif event.key() == Qt.Key.Key_0:
            self.fit_circuit()
        else:
            super().keyPressEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.MiddleButton:
            self.pan_position = event.position().toPoint()
            self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.pan_position is not None:
            position = event.position().toPoint()
            delta = position - self.pan_position
            self.pan_position = position
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.MiddleButton:
            self.pan_position = None
            self.viewport().unsetCursor()
            event.accept()
        else:
            super().mouseReleaseEvent(event)


class LogoWidget(QWidget):
    """Scale the original image for the current screen, including Retina displays."""

    def __init__(self, path):
        super().__init__()
        self.source = QPixmap(str(path)).toImage()
        if self.source.isNull():
            raise RuntimeError(f"Could not load the logo: {path}")
        self.setFixedSize(64, 64)
        self.cached_image = None
        self.cached_size = None

    def paintEvent(self, event):
        ratio = self.devicePixelRatioF()
        size = QSize(round(self.width() * ratio), round(self.height() * ratio))
        if self.cached_size != size:
            self.cached_image = self.source.scaled(
                size, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self.cached_image.setDevicePixelRatio(ratio)
            self.cached_size = size
        painter = QPainter(self)
        width = self.cached_image.width() / ratio
        height = self.cached_image.height() / ratio
        painter.drawImage(QRectF((self.width() - width) / 2,
                                 (self.height() - height) / 2, width, height), self.cached_image)


class SettingsButton(QPushButton):
    """Borderless image button with a white hover tint."""

    def __init__(self, path):
        super().__init__()
        self.image = QPixmap(str(path))
        if self.image.isNull():
            raise RuntimeError(f"Could not load the settings icon: {path}")
        self.setFixedSize(44, 44)
        self.pressed.connect(self.update)
        self.released.connect(self.update)

    def enterEvent(self, event):
        super().enterEvent(event)
        self.update()

    def leaveEvent(self, event):
        super().leaveEvent(event)
        self.update()

    def paintEvent(self, event):
        ratio = self.devicePixelRatioF()
        size = round(30 * ratio)
        icon = self.image.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio,
                                 Qt.TransformationMode.SmoothTransformation)
        tint = QColor("#222222" if self.isDown() else "#3a3a3a" if self.underMouse() else "#606060")
        painter = QPainter(icon)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
        painter.fillRect(icon.rect(), tint)
        painter.end()
        icon.setDevicePixelRatio(ratio)
        painter = QPainter(self)
        width, height = icon.width() / ratio, icon.height() / ratio
        painter.drawPixmap(QRectF((self.width() - width) / 2, (self.height() - height) / 2,
                                  width, height), icon, QRectF(icon.rect()))


class CircuitWindow(QMainWindow):
    def __init__(self, database=None):
        super().__init__()
        self.database = database
        self.examples_dialog = None
        self.preferences = QSettings("SimpleCircuits", "Desktop")
        self.highlight_colors = dict(DEFAULT_HIGHLIGHT_COLORS)
        for role in self.highlight_colors:
            stored = self.preferences.value("highlights/" + role)
            if stored and QColor(str(stored)).isValid():
                self.highlight_colors[role] = QColor(str(stored)).name()
        self.setWindowTitle("Circuit Schematic")
        self.resize(1280, 760)
        self.setMinimumSize(800, 500)

        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QFrame()
        header.setObjectName("header")
        header.setFixedHeight(88)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(16, 12, 20, 12)
        header_layout.setSpacing(12)
        left_header = QWidget()
        left_layout = QHBoxLayout(left_header)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)

        logo_path = Path(__file__).resolve().parent / "assets" / "images" / "simple_circuits_logo.png"
        logo = LogoWidget(logo_path)
        logo.setObjectName("logo")
        logo.setAccessibleName("Simple Circuits logo")
        logo.setToolTip("Simple Circuits")
        left_layout.addWidget(logo)

        self.circuit_name = QLineEdit("circuit-name")
        self.circuit_name.setObjectName("circuitName")
        self.circuit_name.setAccessibleName("Circuit name")
        self.circuit_name.setFixedSize(200, 48)
        self.circuit_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.circuit_name.textChanged.connect(self.resize_circuit_title)
        left_layout.addWidget(self.circuit_name)
        self.settings_button = SettingsButton(
            Path(__file__).resolve().parent / "assets" / "images" / "settings.png"
        )
        self.settings_button.setObjectName("settingsButton")
        self.settings_button.setFixedSize(44, 44)
        self.settings_button.setAccessibleName("Settings")
        self.settings_button.setToolTip("Settings")
        self.settings_button.clicked.connect(self.show_settings)
        left_layout.addWidget(self.settings_button)
        left_layout.addStretch()
        right_header = QWidget()
        right_layout = QHBoxLayout(right_header)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(12)
        right_layout.addStretch()
        self.examples_button = self.button("Circuit Library")
        self.examples_button.clicked.connect(self.show_examples)
        right_layout.addWidget(self.examples_button)
        right_layout.addWidget(self.button("Save Schematic"))
        self.export_button = self.button("Export to Falstad")
        self.export_button.clicked.connect(self.open_in_falstad)
        right_layout.addWidget(self.export_button)
        header_layout.addWidget(left_header)
        header_layout.addStretch()
        header_layout.addWidget(right_header)
        layout.addWidget(header)

        body = QHBoxLayout()
        body.setContentsMargins(24, 26, 24, 24)
        body.setSpacing(28)
        layout.addLayout(body, 1)

        panel = QFrame()
        panel.setObjectName("controlPanel")
        panel.setFixedWidth(260)
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        panel_layout.setSpacing(0)

        self.component_legend = QTableWidget(0, 2)
        self.component_legend.setAccessibleName("Circuit component legend")
        self.component_legend.setHorizontalHeaderLabels(["Name", "Symbol"])
        self.component_legend.setShowGrid(True)
        self.component_legend.setIconSize(QSize(100, 56))
        self.component_legend.verticalHeader().hide()
        self.component_legend.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.component_legend.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.component_legend.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.component_legend.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.component_legend.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.component_legend.setFrameShape(QFrame.Shape.NoFrame)
        self.component_legend.setFrameShadow(QFrame.Shadow.Plain)
        self.component_legend.setLineWidth(0)
        self.component_legend.setMidLineWidth(0)
        self.component_legend.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.component_legend.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.component_legend.setFixedHeight(self.component_legend.horizontalHeader().sizeHint().height())
        self.sidebar_tabs = QTabWidget()
        self.sidebar_tabs.setObjectName("sidebarTabs")
        self.sidebar_tabs.setAccessibleName("Circuit sidebar pages")
        components_page = QWidget()
        components_page.setObjectName("componentsPage")
        components_layout = QVBoxLayout(components_page)
        components_layout.setContentsMargins(14, 14, 14, 14)
        components_layout.addWidget(self.component_legend)
        components_layout.addStretch(1)
        components_scroll = QScrollArea()
        components_scroll.setObjectName("componentsScroll")
        components_scroll.setWidgetResizable(True)
        components_scroll.setFrameShape(QFrame.Shape.NoFrame)
        components_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        components_scroll.setWidget(components_page)
        self.sidebar_tabs.addTab(components_scroll, "Components")
        panel_layout.addWidget(self.sidebar_tabs, 1)
        reading_box = QFrame()
        reading_box.setObjectName("readingBox")
        reading_layout = QVBoxLayout(reading_box)
        reading_layout.setContentsMargins(18, 18, 18, 18)
        reading_layout.setSpacing(16)
        self.reading_guide = QWidget()
        self.reading_guide.setObjectName("readingGuide")
        guide_layout = QVBoxLayout(self.reading_guide)
        guide_layout.setContentsMargins(0, 0, 0, 0)
        guide_layout.setSpacing(8)
        self.guide_sections = []
        topics = (
            ('Current and direction', '<p style="margin-top: 0; margin-bottom: 20px;">Arrows indicate conventional current direction. The displayed current is its magnitude, in amperes (A).</p>'),
            ('Voltage and polarity', '<p style="margin-top: 0; margin-bottom: 10px;">Voltage is measured from terminal 1 to terminal 2:</p><p style="margin-top: 0; margin-bottom: 10px;">V = V(1) − V(2)</p><p style="margin-top: 0; margin-bottom: 20px;">A positive value means terminal 1 is at a higher potential; a negative value means terminal 2 is higher.</p>'),
            ('Ground reference', '<p style="margin-top: 0; margin-bottom: 20px;">Ground is the node chosen as 0 V. All node voltages are measured relative to it; component voltages are the difference between their terminal voltages. Ground is a reference, not necessarily a connection to earth. This app uses the specified ground node, or the negative terminal of the DC source when there is exactly one source.</p>'),
            ('How calculations work', '<p style="margin-top: 0; margin-bottom: 10px;">The app uses Modified Nodal Analysis (MNA). It combines current balance at each node with component equations, such as Ohm’s law, into a system of equations. Solving that system gives node voltages and component currents.</p><p style="margin-top: 0; margin-bottom: 10px;">LEDs and diodes use a fixed forward-voltage model by default. The solver checks conducting and non-conducting states to find a consistent solution. Switch and button states come from the circuit data.</p><p style="margin-top: 0; margin-bottom: 20px;">Results describe DC steady state, after changes have settled. Ideal capacitors act as open circuits and ideal inductors as short circuits. Changes over time are not simulated.</p>'),
            ('Unavailable results', '<p style="margin-top: 0; margin-bottom: 0;">A dash (—) indicates that a result cannot be determined.</p>'),
        )
        for title, text in topics:
            section = GuideSection(title, text)
            self.guide_sections.append(section)
            guide_layout.addWidget(section)
        guide_layout.addStretch(1)
        self.reading_scroll = QScrollArea()
        self.reading_scroll.setObjectName("readingScroll")
        self.reading_scroll.setWidgetResizable(True)
        self.reading_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.reading_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.reading_scroll.setMinimumHeight(80)
        self.reading_scroll.setWidget(self.reading_guide)
        reading_layout.addWidget(self.reading_scroll, 1)
        self.sidebar_tabs.addTab(reading_box, "Guide")
        formulas_page = QWidget()
        formulas_page.setObjectName("formulasPage")
        formulas_layout = QVBoxLayout(formulas_page)
        formulas_layout.setContentsMargins(18, 18, 18, 18)
        formulas_layout.setSpacing(8)
        self.formula_sections = []
        for title, text in FORMULA_TOPICS:
            section = GuideSection(title, text, FORMULA_EQUATIONS[title])
            self.formula_sections.append(section)
            formulas_layout.addWidget(section)
        formulas_layout.addStretch(1)
        self.formulas_scroll = QScrollArea()
        self.formulas_scroll.setObjectName("formulasScroll")
        self.formulas_scroll.setWidgetResizable(True)
        self.formulas_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.formulas_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.formulas_scroll.setWidget(formulas_page)
        self.sidebar_tabs.addTab(self.formulas_scroll, "Formulas")
        body.addWidget(panel)

        self.scene = QGraphicsScene(self)
        self.scene.setProperty("highlightColors", self.highlight_colors)
        self.canvas = SchematicView(self.scene)
        self.canvas.setObjectName("schematicCanvas")
        self.canvas.setAccessibleName("Circuit schematic canvas")
        self.canvas.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.circuit = None
        self.simulation_result = None
        schematic_area = QVBoxLayout()
        schematic_area.setContentsMargins(0, 0, 0, 0)
        schematic_area.setSpacing(8)
        schematic_area.addWidget(self.canvas, 1)
        body.addLayout(schematic_area, 1)

        self.setStyleSheet("""
            QWidget {
                background: #fafafa;
                color: #111111;
                font-size: 14px;
                font-weight: normal;
            }
            QFrame#header, QFrame#controlPanel { background: #d9d9d9; }
            QFrame#controlPanel { border: 1px solid #a8a8a8; }
            QLabel { background: transparent; }
            QToolTip {
                background-color: #ffffff;
                color: #222222;
                font-size: 12px;
                border: 1px solid #c6c6c6;
                padding: 5px 7px;
            }
            QScrollArea#componentsScroll, QScrollArea#componentsScroll > QWidget { background: #d9d9d9; border: none; }
            QFrame#readingBox { background: #d9d9d9; border: none; }
            QTabWidget#sidebarTabs::pane { border: none; border-top: 1px solid #a8a8a8; background: #d9d9d9; }
            QTabWidget#sidebarTabs > QWidget, QWidget#componentsPage { background: #d9d9d9; }
            QTabBar { background: #d9d9d9; }
            QTabBar::tab {
                background: #d9d9d9;
                color: #555555;
                padding: 9px 8px;
                border: none;
                border-bottom: 2px solid transparent;
                font-size: 14px;
            }
            QTabBar::tab:hover { background: #e3e3e3; color: #111111; }
            QTabBar::tab:selected {
                background: #f1f1f1;
                color: #111111;
                border-bottom: 2px solid #787aaf;
                font-weight: bold;
            }
            QWidget#readingGuide, QWidget#formulasPage { background: #d9d9d9; }
            QScrollArea#formulasScroll, QScrollArea#formulasScroll > QWidget { background: #d9d9d9; border: none; }
            QFrame#guideSection { background: #f5f5f5; border: none; }
            QPushButton#guideDisclosure {
                text-align: left; padding: 10px 8px; background: #e8e8e8;
                border: none; border-bottom: 1px solid #c6c6c6; font-size: 14px;
            }
            QPushButton#guideDisclosure:hover { background: #f1f1f1; }
            QPushButton#guideDisclosure:checked { background: #f1f1f1; font-weight: bold; }
            QPushButton#guideDisclosure:focus { border: 1px solid #a8a8a8; }
            QScrollArea#readingScroll, QScrollArea#readingScroll > QWidget { background: #d9d9d9; border: none; }
            QScrollArea QScrollBar:vertical {
                background: transparent;
                width: 6px;
                margin: 0;
            }
            QScrollArea QScrollBar::handle:vertical {
                background: #b0b0b0;
                border-radius: 3px;
                min-height: 24px;
            }
            QScrollArea QScrollBar::handle:vertical:hover {
                background: #888888;
            }
            QScrollArea QScrollBar::add-line:vertical,
            QScrollArea QScrollBar::sub-line:vertical {
                height: 0;
                border: none;
                background: transparent;
            }
            QScrollArea QScrollBar::add-page:vertical,
            QScrollArea QScrollBar::sub-page:vertical {
                background: transparent;
            }
            QFrame#header > QWidget { background: transparent; }
            QPushButton#componentDisclosure {
                background: transparent; border: none; padding: 0;
                text-align: center; font-size: 14px;
            }
            QPushButton#componentDisclosure[rowHovered="true"] { background: #f3f3f3; }
            QPushButton#componentDisclosure:checked { font-weight: bold; }
            QPushButton#componentDisclosure[expanded="true"],
            QPushButton#componentDisclosure[expanded="true"]:hover {
                background: #e8e8e8;
            }
            QPushButton#componentDisclosure:focus { border: none; }
            QTableWidget {
                background: #ffffff;
                font-size: 14px;
                border: 1px solid #a8a8a8;
                gridline-color: #a8a8a8;
            }
            QTableWidget > QWidget { border: none; }
            QHeaderView { border: none; }
            QHeaderView::section {
                background: #e8e8e8;
                color: #111111;
                font-size: 14px;
                font-weight: bold;
                padding: 6px 2px;
                border: 0;
                border-bottom: 1px solid #a8a8a8;
                border-right: 1px solid #a8a8a8;
            }
            QHeaderView::section:last { border-right: none; }
            QLineEdit#circuitName {
                background: #d9d9d9;
                border: 2px solid #a8a8a8;
                border-radius: 24px;
                font-size: 16px;
                font-weight: 500;
                padding: 0 10px;
            }
            QPushButton {
                background: #e8e8e8;
                border: 1px solid #a8a8a8;
                padding: 12px 18px;
            }
            QPushButton#settingsButton {
                padding: 0;
                font-size: 40px;
                background: transparent;
                border: none;
            }
            QPushButton#settingsButton:hover { background: transparent; color: #ffffff; }
            QPushButton#settingsButton:pressed { background: transparent; color: #eeeeee; }
            QPushButton#settingsButton:focus { border: none; }
            QPushButton:hover { background: #f1f1f1; }
            QPushButton:pressed { background: #cccccc; }
            QPushButton:focus { border: 2px solid #777777; }
            QGraphicsView#schematicCanvas {
                background: #fafafa;
                border: 2px solid #a8a8a8;
            }
        """)

    def resize_circuit_title(self, text):
        self.circuit_name.ensurePolished()
        width = self.circuit_name.fontMetrics().horizontalAdvance(text) + 36
        self.circuit_name.setFixedWidth(max(200, width))

    def load_topology(self, data):
        """Load controller JSON/dict; invalid input preserves the current circuit."""
        try:
            circuit = parse_topology(data)
        except TopologyError as error:
            QMessageBox.warning(self, "Invalid topology", str(error))
            return False
        return self.display_circuit(circuit)

    def display_circuit(self, circuit, preserve_view=False):
        center = self.canvas.mapToScene(self.canvas.viewport().rect().center())
        transform = self.canvas.transform()
        self.simulation_result = solve_dc(circuit)
        display_circuit = (replace(circuit, ground_node=self.simulation_result.ground_node)
                           if self.simulation_result.ground_node is not None else circuit)
        render_circuit(self.scene, display_circuit, self.simulation_result)
        self.statusBar().showMessage(
            "" if self.simulation_result.status == "solved" else self.simulation_result.message
        )
        self.statusBar().setToolTip("V = V1 − V2. Current displays magnitude; arrows indicate conventional current direction.")
        self.circuit = circuit
        names = COMPONENT_NAMES
        types = {}
        for component in circuit.components:
            types.setdefault(component.type, component)
        # Hide replaced widgets before Qt deletes them on the next event cycle.
        for row in range(self.component_legend.rowCount()):
            for column in range(2):
                previous = self.component_legend.cellWidget(row, column)
                if previous is not None:
                    previous.hide()
        self.component_legend.clearContents()
        self.component_legend.clearSpans()
        self.component_legend.setRowCount(2 * len(types))
        for index, component in enumerate(types.values()):
            row = 2 * index
            icon_scene = QGraphicsScene()
            icon_scene.addItem(ComponentSymbol(component))
            # Render vectors at display density instead of enlarging a small bitmap.
            pixel_ratio = max(2.0, self.devicePixelRatioF())
            pixmap = QPixmap(round(100 * pixel_ratio), round(56 * pixel_ratio))
            pixmap.setDevicePixelRatio(pixel_ratio)
            pixmap.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            if component.type == "potentiometer":
                icon_scene.render(painter, QRectF(14.16, 0, 71.68, 56), QRectF(-64, -40, 128, 100))
            else:
                icon_scene.render(painter, QRectF(5.2, 0, 89.6, 56), QRectF(-64, -40, 128, 80))
            painter.end()
            toggle = ComponentRowButton("▸ " + names[component.type])
            toggle.setObjectName("componentDisclosure")
            toggle.setCheckable(True)
            toggle.setAccessibleName("About " + names[component.type])
            icon_button = ComponentRowButton()
            toggle.row_buttons = icon_button.row_buttons = [toggle, icon_button]
            icon_button.setObjectName("componentDisclosure")
            icon_button.setIcon(QIcon(pixmap))
            icon_button.setIconSize(QSize(100, 56))
            icon_button.setAccessibleName("About " + names[component.type] + " symbol")
            icon_button.clicked.connect(toggle.click)
            description = QLabel(COMPONENT_DESCRIPTIONS[component.type])
            description.setWordWrap(True)
            description.setContentsMargins(12, 10, 12, 12)
            description.setStyleSheet("background: #f5f5f5;")
            self.component_legend.setCellWidget(row, 0, toggle)
            self.component_legend.setCellWidget(row, 1, icon_button)
            self.component_legend.setSpan(row + 1, 0, 1, 2)
            self.component_legend.setCellWidget(row + 1, 0, description)
            self.component_legend.setRowHeight(row, 64)
            self.component_legend.setRowHidden(row, False)
            self.component_legend.setRowHidden(row + 1, True)
            toggle.toggled.connect(
                lambda expanded, row=row + 1, label=description, button=toggle, name=names[component.type]:
                    self.toggle_component_description(row, label, button, name, expanded)
            )
        self.resize_component_legend()
        self.circuit_name.setText(circuit.name)
        if preserve_view:
            self.canvas.setTransform(transform)
            self.canvas.centerOn(center)
        else:
            self.canvas.resetTransform()
            bounds = self.scene.sceneRect()
            viewport = self.canvas.viewport().rect()
            if bounds.width() > viewport.width() or bounds.height() > viewport.height():
                self.canvas.fitInView(bounds, Qt.AspectRatioMode.KeepAspectRatio)
            self.canvas.centerOn(self.scene.sceneRect().center())
        return True

    def resize_component_legend(self):
        self.component_legend.setFixedHeight(
            self.component_legend.horizontalHeader().height()
            + sum(self.component_legend.rowHeight(row)
                  for row in range(self.component_legend.rowCount())
                  if not self.component_legend.isRowHidden(row)) + 2
        )

    def toggle_component_description(self, row, label, button, name, expanded):
        for column in range(2):
            cell = self.component_legend.cellWidget(row - 1, column)
            cell.setProperty("expanded", expanded)
            cell.style().unpolish(cell)
            cell.style().polish(cell)
            cell.update()
        button.setText(("▾ " if expanded else "▸ ") + name)
        width = max(100, self.component_legend.viewport().width())
        self.component_legend.setRowHeight(row, max(40, label.heightForWidth(width)))
        self.component_legend.setRowHidden(row, not expanded)
        self.resize_component_legend()

    def show_settings(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Settings")
        dialog.setMinimumWidth(360)
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel("<b>Highlight colours</b>"))
        form = QFormLayout()
        layout.addLayout(form)
        draft = dict(self.highlight_colors)
        swatches = {}

        def update_swatch(role):
            button = swatches[role]
            color = QColor(draft[role])
            foreground = "#111111" if color.lightness() > 140 else "#ffffff"
            button.setText(color.name())
            button.setStyleSheet(f"background: {color.name()}; color: {foreground}; padding: 8px 16px;")

        def choose(role):
            color = QColorDialog.getColor(QColor(draft[role]), dialog, "Choose highlight colour")
            if color.isValid():
                draft[role] = color.name()
                update_swatch(role)

        for role, title in (("component", "Components"), ("node", "Connected nodes"),
                            ("current", "Current arrows")):
            button = QPushButton()
            button.setAccessibleName(title + " colour")
            button.clicked.connect(lambda checked=False, role=role: choose(role))
            swatches[role] = button
            update_swatch(role)
            form.addRow(title, button)
        reset = QPushButton("Restore defaults")
        def restore():
            draft.update(DEFAULT_HIGHLIGHT_COLORS)
            for role in swatches:
                update_swatch(role)
        reset.clicked.connect(restore)
        layout.addWidget(reset)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save |
                                   QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.apply_highlight_colors(draft)

    def apply_highlight_colors(self, colors):
        self.highlight_colors = dict(colors)
        self.scene.setProperty("highlightColors", self.highlight_colors)
        for role, color in colors.items():
            self.preferences.setValue("highlights/" + role, color)
        if self.circuit is not None:
            displayed = replace(self.circuit, ground_node=self.simulation_result.ground_node)
            render_circuit(self.scene, displayed, self.simulation_result)
        self.scene.update()

    def open_in_falstad(self):
        if self.circuit is None:
            self.statusBar().showMessage("Load a circuit before exporting to Falstad.")
            return
        try:
            url = falstad_url(self.circuit)
        except FalstadExportError as error:
            self.statusBar().showMessage(str(error))
            return
        if QDesktopServices.openUrl(QUrl(url)):
            self.statusBar().showMessage("Opened in Falstad.")
        else:
            self.statusBar().showMessage("Could not open the browser. Use falstad.py --output to save circuit text.")

    def show_examples(self):
        """Browse SQLite records; seed bundled examples only for an empty DB."""
        if self.examples_dialog is not None and self.examples_dialog.isVisible():
            self.examples_dialog.raise_()
            return
        try:
            if self.database is None:
                self.database = CircuitDatabase()
            names = self.database.list_names()
            if not names:
                self.database.import_folder(Path(__file__).resolve().parent / "examples")
                names = self.database.list_names()
            # Add diagnostic examples to existing libraries without overwriting records.
            for path in sorted((Path(__file__).resolve().parent / "examples" / "incomplete").glob("*.json")):
                data = json.loads(path.read_bytes())
                if data["name"] not in names:
                    self.database.save(data)
                    names.append(data["name"])
        except (OSError, sqlite3.Error, ValueError) as error:
            QMessageBox.warning(self, "Cannot open circuit library", str(error))
            return

        # Use bundled file order for known examples; other database records follow.
        example_order = {}
        for path in sorted((Path(__file__).resolve().parent / "examples").rglob("*.json")):
            try:
                name = json.loads(path.read_bytes())["name"]
            except (OSError, ValueError, KeyError, TypeError):
                continue
            example_order.setdefault(name, len(example_order))
        names.sort(key=lambda name: (example_order.get(name, len(example_order)), name.casefold()))

        dialog = QDialog(self)
        dialog.setWindowTitle("Circuit Library")
        dialog.resize(440, 440)
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel("Select a circuit to view:"))
        circuits = QListWidget()
        circuits.setAccessibleName("Circuits stored in the database")
        circuits.addItems(names)
        layout.addWidget(circuits)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Open | QDialogButtonBox.StandardButton.Cancel
        )
        layout.addWidget(buttons)
        open_button = buttons.button(QDialogButtonBox.StandardButton.Open)
        open_button.setEnabled(bool(names))
        if names:
            current_name = self.circuit.name if self.circuit is not None else None
            circuits.setCurrentRow(names.index(current_name) if current_name in names else 0)
        else:
            layout.insertWidget(1, QLabel("No circuits are stored yet."))

        def open_selected():
            item = circuits.currentItem()
            if item is None:
                return
            try:
                data = self.database.load(item.text())
            except (OSError, sqlite3.Error, ValueError, KeyError) as error:
                QMessageBox.warning(dialog, "Cannot load circuit", str(error))
                return
            if self.load_topology(data):
                dialog.accept()

        buttons.accepted.connect(open_selected)
        buttons.rejected.connect(dialog.reject)
        circuits.itemDoubleClicked.connect(lambda item: open_selected())
        def close_browser(result):
            if self.examples_dialog is dialog:
                self.examples_dialog = None
            dialog.deleteLater()

        dialog.finished.connect(close_browser)
        self.examples_dialog = dialog
        dialog.open()

    def button(self, label):
        button = QPushButton(label)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        return button


def main():
    parser = argparse.ArgumentParser(description="Circuit schematic desktop app")
    parser.add_argument("topology_file", nargs="?", type=Path,
                        help="Optional circuit JSON file to display on startup")
    args = parser.parse_args()
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    font_dir = Path(__file__).resolve().parent / "assets" / "fonts"
    font_family = None
    for filename in ("UlagadiSansRegular.ttf", "UlagadiSansMedium.ttf"):
        font_path = font_dir / filename
        font_id = QFontDatabase.addApplicationFont(str(font_path))
        families = QFontDatabase.applicationFontFamilies(font_id)
        if not families:
            raise RuntimeError(f"Could not load the application font: {font_path}")
        if font_family is None:
            font_family = families[0]
    font = QFont(font_family)
    font.setPixelSize(14)
    font.setWeight(QFont.Weight.Normal)
    app.setFont(font)
    window = CircuitWindow()
    window.show()
    if args.topology_file is not None:
        try:
            data = args.topology_file.read_bytes()
        except OSError as error:
            QMessageBox.warning(window, "Cannot open topology", str(error))
        else:
            window.load_topology(data)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
