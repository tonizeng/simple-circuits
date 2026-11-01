"""Barebones circuit desktop UI. Run with: python main.py."""

import sys
import argparse
import sqlite3
import json
from pathlib import Path
from dataclasses import replace

from PySide6.QtCore import Qt, QSize, QRectF, QUrl, QPoint
from PySide6.QtGui import QFont, QFontDatabase, QPainter, QPixmap, QDesktopServices
from topology import parse_topology, TopologyError
from schematic import render_circuit, ComponentSymbol
from components import COMPONENT_NAMES
from database import CircuitDatabase
from simulation import solve_dc
from falstad import falstad_url, FalstadExportError
from PySide6.QtWidgets import (
    QApplication, QFrame, QGraphicsScene, QGraphicsView, QHBoxLayout,
    QLabel, QLineEdit, QMainWindow, QMessageBox, QPushButton,
    QVBoxLayout, QWidget, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QDialog, QListWidget, QDialogButtonBox, QScrollArea, QTabWidget,
)


class CircuitWindow(QMainWindow):
    def __init__(self, database=None):
        super().__init__()
        self.database = database
        self.examples_dialog = None
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
        header.setFixedHeight(76)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(16, 12, 20, 12)
        header_layout.setSpacing(12)
        left_header = QWidget()
        left_layout = QHBoxLayout(left_header)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)

        logo = QLabel()
        logo.setObjectName("logo")
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo.setFixedWidth(60)
        logo_path = Path(__file__).resolve().parent / "assets" / "images" / "simple_circuits_logo.png"
        logo_pixmap = QPixmap(str(logo_path))
        if logo_pixmap.isNull():
            raise RuntimeError(f"Could not load the logo: {logo_path}")
        pixel_ratio = self.devicePixelRatioF()
        logo_display = logo_pixmap.scaled(
            round(52 * pixel_ratio), round(52 * pixel_ratio),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        logo_display.setDevicePixelRatio(pixel_ratio)
        logo.setPixmap(logo_display)
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
        left_layout.addStretch()
        right_header = QWidget()
        right_layout = QHBoxLayout(right_header)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(12)
        right_layout.addStretch()
        self.examples_button = self.button("View Examples")
        self.examples_button.clicked.connect(self.show_examples)
        right_layout.addWidget(self.examples_button)
        right_layout.addWidget(self.button("Settings"))
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
        self.component_legend.setHorizontalHeaderLabels(["Symbol", "Name"])
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
        self.sidebar_tabs.addTab(components_page, "Components")
        panel_layout.addWidget(self.sidebar_tabs, 1)
        reading_box = QFrame()
        reading_box.setObjectName("readingBox")
        reading_layout = QVBoxLayout(reading_box)
        reading_layout.setContentsMargins(18, 18, 18, 18)
        reading_layout.setSpacing(16)
        self.reading_guide = QLabel(
            '<p style="margin-top: 0; margin-bottom: 6px;"><b>Current</b></p>'
            '<p style="margin-top: 0; margin-bottom: 20px;">Blue arrows indicate conventional '
            'current direction. The displayed current is its magnitude, in amperes (A).</p>'
            '<p style="margin-top: 0; margin-bottom: 6px;"><b>Voltage</b></p>'
            '<p style="margin-top: 0; margin-bottom: 10px;">Voltage is measured from '
            'terminal 1 to terminal 2:</p>'
            '<p style="margin-top: 0; margin-bottom: 10px;">V = V(1) − V(2)</p>'
            '<p style="margin-top: 0; margin-bottom: 20px;">A positive value means terminal 1 '
            'is at a higher potential; a negative value means terminal 2 is higher.</p>'
            '<p style="margin-top: 0; margin-bottom: 6px;"><b>Unavailable results</b></p>'
            '<p style="margin-top: 0; margin-bottom: 0;">A dash (—) indicates that a result '
            'cannot be determined.</p>'
        )
        self.reading_guide.setObjectName("readingGuide")
        self.reading_guide.setTextFormat(Qt.TextFormat.RichText)
        self.reading_guide.setWordWrap(True)
        self.reading_guide.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.reading_guide.setAccessibleName("Circuit guide for the schematic")
        self.reading_scroll = QScrollArea()
        self.reading_scroll.setObjectName("readingScroll")
        self.reading_scroll.setWidgetResizable(True)
        self.reading_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.reading_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.reading_scroll.setMinimumHeight(80)
        self.reading_scroll.setWidget(self.reading_guide)
        reading_layout.addWidget(self.reading_scroll, 1)
        self.sidebar_tabs.addTab(reading_box, "Learn")
        body.addWidget(panel)

        self.scene = QGraphicsScene(self)
        self.canvas = QGraphicsView(self.scene)
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
            QFrame#readingBox { background: #d9d9d9; border: none; }
            QTabWidget#sidebarTabs::pane { border: none; border-top: 1px solid #a8a8a8; background: #d9d9d9; }
            QTabWidget#sidebarTabs > QWidget, QWidget#componentsPage { background: #d9d9d9; }
            QTabBar { background: #d9d9d9; }
            QTabBar::tab {
                background: #d9d9d9;
                color: #555555;
                padding: 9px 12px;
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
            QLabel#readingGuide { font-size: 14px; background: #d9d9d9; }
            QScrollArea#readingScroll, QScrollArea#readingScroll > QWidget { background: #d9d9d9; border: none; }
            QScrollArea#readingScroll QScrollBar:vertical {
                background: transparent;
                width: 6px;
                margin: 0;
            }
            QScrollArea#readingScroll QScrollBar::handle:vertical {
                background: #b0b0b0;
                border-radius: 3px;
                min-height: 24px;
            }
            QScrollArea#readingScroll QScrollBar::handle:vertical:hover {
                background: #888888;
            }
            QScrollArea#readingScroll QScrollBar::add-line:vertical,
            QScrollArea#readingScroll QScrollBar::sub-line:vertical {
                height: 0;
                border: none;
                background: transparent;
            }
            QScrollArea#readingScroll QScrollBar::add-page:vertical,
            QScrollArea#readingScroll QScrollBar::sub-page:vertical {
                background: transparent;
            }
            QFrame#header > QWidget { background: transparent; }
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
        self.statusBar().showMessage(self.simulation_result.message)
        self.statusBar().setToolTip("V = V1 − V2. Current displays magnitude; arrows indicate conventional current direction.")
        self.circuit = circuit
        names = COMPONENT_NAMES
        types = {}
        for component in circuit.components:
            types.setdefault(component.type, component)
        # Replaced cell widgets are deleted later by Qt; hide them immediately
        # so switching examples cannot briefly draw old symbols over new ones.
        for row in range(self.component_legend.rowCount()):
            previous = self.component_legend.cellWidget(row, 0)
            if previous is not None:
                previous.hide()
        self.component_legend.clearContents()
        self.component_legend.setRowCount(len(types))
        for row, component in enumerate(types.values()):
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
            symbol_item = QTableWidgetItem("")
            symbol_item.setToolTip(names[component.type])
            self.component_legend.setItem(row, 0, symbol_item)
            symbol_label = QLabel()
            symbol_label.setPixmap(pixmap)
            symbol_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            symbol_label.setToolTip(names[component.type])
            self.component_legend.setCellWidget(row, 0, symbol_label)
            name_item = QTableWidgetItem(names[component.type])
            name_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.component_legend.setItem(row, 1, name_item)
            self.component_legend.setRowHeight(row, 64)
        self.component_legend.setFixedHeight(
            self.component_legend.horizontalHeader().height()
            + sum(self.component_legend.rowHeight(row) for row in range(len(types)))
            + 2  # Top and bottom borders.
        )
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
            self.statusBar().showMessage("Opened in Falstad. Its exponential LED model may differ from the classroom fixed-drop result.")
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
        except (OSError, sqlite3.Error, ValueError) as error:
            QMessageBox.warning(self, "Cannot open examples", str(error))
            return

        # Use bundled file order for known examples; other database records follow.
        example_order = {}
        for path in sorted((Path(__file__).resolve().parent / "examples").glob("*.json")):
            try:
                name = json.loads(path.read_bytes())["name"]
            except (OSError, ValueError, KeyError, TypeError):
                continue
            example_order.setdefault(name, len(example_order))
        names.sort(key=lambda name: (example_order.get(name, len(example_order)), name.casefold()))

        dialog = QDialog(self)
        dialog.setWindowTitle("Circuit Examples")
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
