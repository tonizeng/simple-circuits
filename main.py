"""Barebones circuit desktop UI. Run with: python main.py."""

import sys
import argparse
import sqlite3
import json
from pathlib import Path
from dataclasses import replace

from PySide6.QtCore import Qt, QSize, QRectF, QUrl
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
    QAbstractItemView, QDialog, QListWidget, QDialogButtonBox,
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

        title = QLabel("Control Panel")
        title.setObjectName("panelTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setFixedHeight(44)
        panel_layout.addWidget(title)

        panel_content = QVBoxLayout()
        panel_content.setContentsMargins(14, 18, 14, 14)
        panel_content.setSpacing(12)
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
        panel_content.addWidget(self.component_legend)
        panel_content.addStretch(1)
        self.examples_button = self.button("View Examples")
        self.examples_button.clicked.connect(self.show_examples)
        panel_content.addWidget(self.examples_button)
        panel_content.addWidget(self.button("Settings"))
        panel_layout.addLayout(panel_content, 1)
        body.addWidget(panel)

        self.scene = QGraphicsScene(self)
        self.canvas = QGraphicsView(self.scene)
        self.canvas.setObjectName("schematicCanvas")
        self.canvas.setAccessibleName("Circuit schematic canvas")
        self.canvas.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.circuit = None
        self.simulation_result = None
        body.addWidget(self.canvas, 1)

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
            QFrame#header > QWidget { background: transparent; }
            QTableWidget {
                background: #ffffff;
                font-size: 13px;
                border: 1px solid #a8a8a8;
                gridline-color: #a8a8a8;
            }
            QTableWidget > QWidget { border: none; }
            QHeaderView { border: none; }
            QHeaderView::section {
                background: #e8e8e8;
                color: #111111;
                font-size: 13px;
                font-weight: normal;
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
            QLabel#panelTitle {
                background: #c6c6c6;
                border-bottom: 1px solid #a8a8a8;
                font-size: 16px;
                font-weight: bold;
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
            pixmap = QPixmap(100, 56)
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
