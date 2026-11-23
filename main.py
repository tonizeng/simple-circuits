"""Barebones circuit desktop UI. Run with: python main.py."""

import sys
import argparse
import sqlite3
import json
import copy
import math
from pathlib import Path
from dataclasses import replace, asdict

from PySide6.QtCore import Qt, QSize, QRectF, QUrl, QPoint, QSettings, QTimer, Signal, QObject, QEvent, QVariantAnimation, QEasingCurve
from PySide6.QtSvgWidgets import QSvgWidget
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtGui import QFont, QFontDatabase, QPainter, QPixmap, QDesktopServices, QColor, QIcon, QPen, QLinearGradient, QCursor, QPalette
from topology import parse_topology, TopologyError
from schematic import render_circuit, ComponentSymbol, NetWire, DEFAULT_HIGHLIGHT_COLORS
from components import COMPONENT_NAMES, COMPONENT_DESCRIPTIONS, nominal_label
from database import CircuitDatabase
from formula_reference import FORMULA_TOPICS, FORMULA_EQUATIONS, FORMULA_CAPTIONS
from simulation import solve_dc, SimulationResult
from simulation.rlc import series_rlc
from simulation.rl import rl_timing, rl_step_endpoints
from simulation.rc import rc_timing, rc_step_endpoints, rc_step_snapshot, rc_response_phase
from circuit_safety import SafetyLimits, SafetyReport, SafetyIssue, assess_circuit
from power_protection import PowerProtection
from safety_ui import SafetyAlertsPanel
from component_details import ComponentDetailsPanel, OVERVIEW_ROW_STYLE, add_list_row_shadow, PANEL_BACKGROUND
from circuit_library import CircuitLibraryPage
from guide_ui import CircuitGuideDialog
from falstad import falstad_url, FalstadExportError
from PySide6.QtWidgets import (
    QStyle, QStylePainter, QStyleOptionButton, QDockWidget, QApplication, QFrame, QGraphicsScene, QGraphicsView, QGraphicsDropShadowEffect, QHBoxLayout,
    QLabel, QLineEdit, QMainWindow, QMessageBox, QPushButton, QToolButton,
    QVBoxLayout, QWidget, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QStackedWidget, QButtonGroup, QSizePolicy, QSlider, QCheckBox, QComboBox, QMenu, QDialog, QListWidget, QDialogButtonBox, QScrollArea, QTabWidget, QColorDialog, QFormLayout,
)


class RoundedMenu(QMenu):
    """Shared rounded popup styling for Views and zoom presets."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        self.setStyleSheet("""
            QMenu { background: PANEL_BACKGROUND; color: #222222; border: 1px solid #d5d5df;
                    border-radius: 12px; padding: 6px; }
            QMenu::item { padding: 8px 24px; border-radius: 6px; }
            QMenu::item:selected { background: #fafffe; color: #222222; }
            QMenu::separator { height: 1px; background: #e4e4eb; margin: 4px 8px; }
        """.replace("PANEL_BACKGROUND", PANEL_BACKGROUND))


class IconTextButton(QPushButton):
    """Use the same 8px icon-to-label gap as the inspector rows."""

    def __init__(self, text, *, align_left=False):
        super().__init__(text)
        self.align_left = align_left

    def sizeHint(self):
        size = super().sizeHint()
        if self.objectName() == "headerActionButton":
            self.ensurePolished()
            size.setWidth(self.fontMetrics().horizontalAdvance(self.text()) + self.iconSize().width() + (6 if self.text() else 0) + 20 + 3)
            return size
        if not self.icon().isNull():
            size.setWidth(size.width() + 4)
        return size

    def paintEvent(self, event):
        if self.icon().isNull():
            return super().paintEvent(event)
        option = QStyleOptionButton()
        self.initStyleOption(option)
        icon, text = QIcon(self.icon()), self.text()
        option.icon, option.text = QIcon(), ""
        painter = QStylePainter(self)
        painter.save()
        if self.objectName() == "pageNavigation" and self.isChecked():
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#e7e3f3"))
            painter.drawRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), 12, 12)
            option.palette.setColor(QPalette.ColorRole.ButtonText, QColor("#42447a"))
        else:
            painter.drawControl(QStyle.ControlElement.CE_PushButton, option)
        painter.restore()
        rect = self.style().subElementRect(QStyle.SubElement.SE_PushButtonContents, option, self)
        icon_size = self.iconSize()
        text_width = option.fontMetrics.horizontalAdvance(text)
        gap = (6 if self.objectName() == "headerActionButton" else 8) if text else 0
        width = icon_size.width() + gap + text_width
        if not text:
            rect = self.rect()
            x = (self.width() - icon_size.width()) // 2
        else:
            x = rect.left() if self.align_left else rect.center().x() - width // 2
        state = QIcon.State.On if self.isChecked() else QIcon.State.Off
        mode = (QIcon.Mode.Active if self.underMouse() or self.isDown() else QIcon.Mode.Normal) if self.isEnabled() else QIcon.Mode.Disabled
        icon_y = (self.height() - icon_size.height()) // 2 if not text else rect.center().y() - icon_size.height() // 2
        icon.paint(painter, x, icon_y,
                   icon_size.width(), icon_size.height(), Qt.AlignmentFlag.AlignCenter, mode, state)
        text_rect = QRectF(x + icon_size.width() + gap, rect.top(), text_width, rect.height()).toRect()
        self.style().drawItemText(painter, text_rect,
                                  Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                                  option.palette, self.isEnabled(), text, QPalette.ColorRole.ButtonText)


class OverviewToggle(QPushButton):
    """Persistent bottom-right control for the overview sidebar."""
    REST_WIDTH = 32
    TAB_HEIGHT = 36
    HOVER_WIDTH = 44

    def __init__(self, parent, action):
        super().__init__(parent)
        self.action = action
        self.setFixedSize(self.REST_WIDTH, self.TAB_HEIGHT)
        self.extension = QVariantAnimation(self)
        self.extension.setDuration(280)
        self.extension.setEasingCurve(QEasingCurve.Type.OutBack)
        self.extension.valueChanged.connect(self.animate_width)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAccessibleName("Toggle Circuit Overview")
        self.setToolTip("")
        self.setStyleSheet("QPushButton { background: #fdfefe; border: none; border-top-left-radius: 18px; border-bottom-left-radius: 18px; border-top-right-radius: 0; border-bottom-right-radius: 0; padding: 0; } QPushButton:hover { background: #e7e3f3; }")
        self.clicked.connect(lambda: action.setChecked(not action.isChecked()))
        action.toggled.connect(self.reset_extension)
        parent.installEventFilter(self)
        workspace = getattr(parent.window(), "workspace", None)
        if workspace is not None:
            workspace.installEventFilter(self)
        dock = getattr(parent.window(), "overview_dock", None)
        if dock is not None:
            dock.installEventFilter(self)
        panel = getattr(parent.window(), "component_details", None)
        if panel is not None:
            panel.installEventFilter(self)
        action.toggled.connect(lambda checked: QTimer.singleShot(0, self.reposition))
        self.reposition()

    def reposition(self):
        root = self.parentWidget()
        workspace = getattr(root.window(), "workspace", root)
        bottom = workspace.mapTo(root, QPoint(0, workspace.height())).y()
        self.move(max(0, root.width() - self.width()),
                  max(0, bottom - self.height() - 24))
        self.raise_()

    def reset_extension(self, checked):
        self.extension.stop()
        self.setFixedWidth(self.REST_WIDTH)
        self.reposition()
        self.update()

    def animate_width(self, value):
        self.setFixedWidth(round(value))
        self.reposition()

    def animate_to(self, width):
        self.extension.stop()
        expanding = width > self.width()
        self.extension.setEasingCurve(QEasingCurve.Type.OutBack if expanding else QEasingCurve.Type.OutCubic)
        self.extension.setDuration(280 if expanding else 180)
        self.extension.setStartValue(float(self.width()))
        self.extension.setEndValue(float(width))
        self.extension.start()

    def enterEvent(self, event):
        if not self.action.isChecked():
            self.animate_to(self.HOVER_WIDTH)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.extension.stop()
        self.setFixedWidth(self.REST_WIDTH)
        self.reposition()
        super().leaveEvent(event)

    def eventFilter(self, watched, event):
        if event.type() in (QEvent.Type.Resize, QEvent.Type.Move, QEvent.Type.Show, QEvent.Type.Hide, QEvent.Type.LayoutRequest):
            self.reposition()
            QTimer.singleShot(0, self.reposition)
        return False

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#e7e3f3" if self.underMouse() else "#fdfefe"))
        painter.drawRoundedRect(QRectF(self.rect()), 18, 18)
        # Fill the attachment side completely, including the last pixel.
        painter.drawRect(QRectF(self.width() / 2, 0, self.width() / 2, self.height()))
        painter.setPen(QPen(QColor("#42447a" if self.underMouse() else "#4c5558"), 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        # Point toward the panel when closed and toward its edge when open.
        tip = 20 if self.action.isChecked() else 12
        tail = 12 if self.action.isChecked() else 20
        painter.drawLine(tail, 12, tip, 18)
        painter.drawLine(tip, 18, tail, 24)


class StatusToggle(OverviewToggle):
    """Mirror the overview control at the application's left edge."""
    def reposition(self):
        root = self.parentWidget()
        workspace = getattr(root.window(), "workspace", root)
        bottom = workspace.mapTo(root, QPoint(0, workspace.height())).y()
        self.move(0, max(0, bottom - self.height() - 24))
        self.raise_()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#e7e3f3" if self.underMouse() else "#fdfefe"))
        painter.drawRoundedRect(QRectF(self.rect()), 18, 18)
        painter.drawRect(QRectF(0, 0, self.width() / 2, self.height()))
        painter.setPen(QPen(QColor("#42447a" if self.underMouse() else "#4c5558"), 2,
                            Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        tip = 12 if self.action.isChecked() else 20
        tail = 20 if self.action.isChecked() else 12
        painter.drawLine(tail, 12, tip, 18)
        painter.drawLine(tip, 18, tail, 24)


class NoHoverTooltips(QObject):
    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.ToolTip and not watched.property("allowTooltip"):
            return True
        return super().eventFilter(watched, event)


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

    component_clicked = Signal(str)
    node_clicked = Signal(str, bool)
    selection_cleared = Signal()
    rc_time_changed = Signal(int)
    rc_settled_requested = Signal()

    def __init__(self, scene):
        super().__init__(scene)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.NoAnchor)
        self.pan_position = None
        self.grid_visible = True
        self.zoom_controls = QFrame(self.viewport())
        self.zoom_controls.setObjectName("zoomToolbar")
        self.zoom_controls.setStyleSheet("QFrame#zoomToolbar { background: white; border: none; border-radius: 10px; } QPushButton { background: transparent; border: none; padding: 0px; color: #222222; font-size: 12px; } QPushButton:hover { background: #eeeeee; border-radius: 6px; } QPushButton:pressed { background: #dddddd; }")
        controls = QHBoxLayout(self.zoom_controls)
        controls.setContentsMargins(6, 4, 6, 4)
        controls.setSpacing(3)
        self.display_controls = QFrame(self.viewport())
        self.display_controls.setObjectName("displayControls")
        self.display_controls.setStyleSheet("QFrame#displayControls { background: white; border: none; border-radius: 10px; }")
        display_layout = QHBoxLayout(self.display_controls)
        display_layout.setContentsMargins(6, 8, 6, 8)
        display_layout.setSpacing(3)
        self.labels_toggle = QCheckBox("Show labels")
        self.labels_toggle.setChecked(True)
        self.labels_toggle.setToolTip("Show node names and terminal numbers")
        checkmark_path = (Path(__file__).resolve().parent / "assets" / "images" / "checkmark.svg").as_posix()
        self.labels_toggle.setStyleSheet("""
            QCheckBox { background: transparent; padding: 0px 6px; font-size: 12px; spacing: 6px; }
            QCheckBox::indicator { width: 16px; height: 16px; border: 1px solid #9b9ba6; border-radius: 2px; background: white; }
            QCheckBox::indicator:checked { background: #e7e3f3; border-color: #787aaf; image: url("CHECKMARK_PATH"); }
            QCheckBox::indicator:hover { border-color: #42447a; }
        """.replace("CHECKMARK_PATH", checkmark_path))
        self.labels_toggle.toggled.connect(self.set_labels_visible)
        display_layout.addWidget(self.labels_toggle)
        self.legend_toggle = QCheckBox("Show legend")
        self.legend_toggle.setChecked(True)
        self.legend_toggle.setStyleSheet(self.labels_toggle.styleSheet())
        self.legend_toggle.setAccessibleName("Show sign convention legend")
        display_layout.addWidget(self.legend_toggle)

        def icon(kind):
            pixmap = QPixmap(48, 48)
            pixmap.fill(Qt.GlobalColor.transparent)
            pixmap.setDevicePixelRatio(2)
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setPen(QPen(QColor("#222222"), 1.6))
            if kind == "fit":
                for x, y, dx, dy in ((4, 4, 1, 1), (20, 4, -1, 1), (4, 20, 1, -1), (20, 20, -1, -1)):
                    painter.drawLine(x, y, x + dx * 5, y)
                    painter.drawLine(x, y, x, y + dy * 5)
            else:
                painter.drawEllipse(QRectF(3, 3, 13, 13))
                painter.drawLine(14, 14, 20, 20)
                painter.drawLine(6, 9, 13, 9)
                if kind == "in":
                    painter.drawLine(9, 6, 9, 13)
            painter.end()
            return QIcon(pixmap)

        def icon_button(kind, tip, callback):
            button = QPushButton()
            button.setIcon(icon(kind))
            button.setIconSize(QSize(20, 20))
            button.setFixedSize(30, 30)
            button.setToolTip(tip)
            button.setAccessibleName(tip)
            button.clicked.connect(callback)
            controls.addWidget(button)

        icon_button("out", "Zoom out (−)", lambda: self.zoom_by(1 / 1.2))
        self.zoom_percentage = QPushButton("100%  ⌄")
        self.zoom_percentage.setFixedSize(68, 30)
        self.zoom_percentage.setAccessibleName("Zoom percentage")
        menu = RoundedMenu(self.zoom_percentage)
        for percentage in (25, 50, 75, 100, 125, 150, 200, 400):
            action = menu.addAction(f"{percentage}%")
            action.triggered.connect(lambda checked=False, value=percentage: self.zoom_by(value / 100 / self.transform().m11()))
        menu.addSeparator()
        menu.addAction("Fit circuit", self.fit_circuit)
        self.zoom_percentage.setMenu(menu)
        self.zoom_percentage.setStyleSheet("QPushButton::menu-indicator { image: none; width: 0px; }")
        controls.addWidget(self.zoom_percentage)
        icon_button("in", "Zoom in (+)", lambda: self.zoom_by(1.2))
        divider = QFrame()
        divider.setFixedSize(1, 20)
        divider.setStyleSheet("background: #e1e1e1; border: none;")
        controls.addWidget(divider)
        icon_button("fit", "Fit circuit (0)", self.fit_circuit)
        self.pan_button = QPushButton()
        self.pan_button.setCheckable(True)
        self.pan_button.setIcon(QIcon(str(Path(__file__).resolve().parent / "assets" / "images" / "hand-pan.svg")))
        self.pan_button.setIconSize(QSize(18, 18))
        self.pan_button.setFixedSize(30, 30)
        self.pan_button.setAccessibleName("Pan schematic with left mouse drag")
        self.pan_button.setStyleSheet("QPushButton { border: none; border-radius: 6px; padding: 0px; } QPushButton:checked { background: #e7e3f3; color: #42447a; }")
        self.pan_cursor = QCursor(Qt.CursorShape.OpenHandCursor)
        self.pan_button.toggled.connect(lambda active: self.viewport().setCursor(self.pan_cursor if active else QCursor(Qt.CursorShape.ArrowCursor)))
        controls.addWidget(self.pan_button)
        self.zoom_controls.adjustSize()
        self.display_controls.adjustSize()
        controls_width = max(self.zoom_controls.width(), self.display_controls.width())
        self.zoom_controls.setFixedWidth(controls_width)
        self.display_controls.setFixedWidth(controls_width)
        self.current_reference = QLabel("<b style='color: #42447a;'>Sign Convention</b><br>Voltage&nbsp;&nbsp; V(1) − V(2)<br>Positive current&nbsp;&nbsp; 1 → 2", self.viewport())
        self.current_reference.setWordWrap(True)
        self.current_reference.setStyleSheet("background: #ffffff; color: #555555; font-size: 12px; padding: 10px 12px; border: none; border-radius: 8px;")
        self.legend_toggle.toggled.connect(self.current_reference.setVisible)
        self.update_current_reference()
        self.rc_controls = QFrame(self.viewport())
        self.rc_controls.setObjectName("rcTimeToolbar")
        self.rc_controls.setStyleSheet("QFrame#rcTimeToolbar { background: #ffffff; border: none; border-radius: 10px; } QLabel { background: transparent; color: #263c3f; font-size: 12px; } QPushButton { background: #edf4f2; border: none; border-radius: 6px; padding: 4px 8px; font-size: 12px; }")
        rc_layout = QVBoxLayout(self.rc_controls)
        rc_layout.setContentsMargins(12, 8, 12, 8)
        rc_layout.setSpacing(6)
        self.rc_time_label = QLabel("Predicted response · Settled DC")
        self.rc_time_label.setWordWrap(True)
        rc_layout.addWidget(self.rc_time_label)
        rc_row = QHBoxLayout()
        self.rc_slider = QSlider(Qt.Orientation.Horizontal)
        self.rc_slider.setRange(0, 500)
        self.rc_slider.setAccessibleName("Response preview time, zero to five time constants")
        self.rc_slider.setStyleSheet("QSlider { background: transparent; } QSlider::groove:horizontal { height: 4px; background: #cbd7d4; border-radius: 2px; } QSlider::handle:horizontal { width: 12px; background: #527f85; border-radius: 6px; margin: -4px 0; }")
        self.rc_slider.valueChanged.connect(self.rc_time_changed.emit)
        self.rc_slider.sliderPressed.connect(lambda: self.rc_time_changed.emit(self.rc_slider.value()))
        rc_row.addWidget(self.rc_slider, 1)
        self.rc_settled_button = QPushButton("Settled DC")
        self.rc_settled_button.clicked.connect(self.rc_settled_requested.emit)
        rc_row.addWidget(self.rc_settled_button)
        rc_layout.addLayout(rc_row)
        self.rc_controls.hide()
        for overlay in (self.zoom_controls, self.display_controls, self.current_reference):
            shadow = QGraphicsDropShadowEffect(overlay)
            shadow.setBlurRadius(10)
            shadow.setOffset(0, 2)
            shadow.setColor(QColor(0, 0, 0, 28))
            overlay.setGraphicsEffect(shadow)

    def drawBackground(self, painter, rect):
        painter.fillRect(rect, QColor("#ffffff"))
        if not self.grid_visible:
            return
        scale = max(.001, abs(self.transform().m11()))
        step = 10
        while step * scale < 8:
            step *= 2
        painter.save()
        pen = QPen()
        pen.setCosmetic(True)
        for axis in (0, 1):
            low, high = (rect.left(), rect.right()) if axis == 0 else (rect.top(), rect.bottom())
            for index in range(math.floor(low / step), math.ceil(high / step) + 1):
                position = index * step
                pen.setColor(QColor("#e0e6e5" if index % 2 == 0 else "#eef1f0"))
                painter.setPen(pen)
                if axis == 0:
                    painter.drawLine(QRectF(position, rect.top(), 0, rect.height()).topLeft(), QRectF(position, rect.top(), 0, rect.height()).bottomLeft())
                else:
                    painter.drawLine(QRectF(rect.left(), position, rect.width(), 0).topLeft(), QRectF(rect.left(), position, rect.width(), 0).topRight())
        painter.restore()

    def update_current_reference(self):
        signed = self.scene().property("currentDisplay") == "signed"
        current_note = "<b>Positive current:</b> terminal 1 → terminal 2" if signed else "<b>Current:</b> displays magnitude, arrows show conventional direction."
        self.current_reference.setText("<b style='color: #42447a;'>Sign Convention</b><br><b>Voltage:</b> voltage at terminal 1 − voltage at terminal 2<br>" + current_note)
        self.current_reference.setVisible(self.legend_toggle.isChecked())
        self.current_reference.setFixedWidth(min(380, max(1, self.viewport().width() - 20)))
        self.current_reference.setFixedHeight(max(1, self.current_reference.heightForWidth(self.current_reference.width())))
        self.current_reference.move(10, 10)
        self.current_reference.raise_()

    def set_labels_visible(self, visible):
        self.scene().setProperty("showConnectionLabels", visible)
        for item in self.scene().items():
            if item.data(0) == "connectionLabel":
                item.setVisible(visible)

    def update_zoom_percentage(self):
        self.zoom_percentage.setText(f"{self.transform().m11() * 100:.0f}%  ⌄")

    def scrollContentsBy(self, dx, dy):
        # QGraphicsView scrolls viewport children too; overlays must stay anchored.
        overlays = [child for child in self.viewport().children()
                    if isinstance(child, SafetyAlertsPanel) or child in (getattr(self, "zoom_controls", None), getattr(self, "display_controls", None), getattr(self, "current_reference", None), getattr(self, "rc_controls", None))]
        positions = [(widget, widget.pos()) for widget in overlays]
        super().scrollContentsBy(dx, dy)
        for widget, position in positions:
            widget.move(position)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "zoom_controls"):
            self.zoom_controls.move(max(8, self.viewport().width() - self.zoom_controls.width() - 10), 10)
            self.zoom_controls.raise_()
            self.display_controls.move(max(8, self.viewport().width() - self.display_controls.width() - 10), self.zoom_controls.y() + self.zoom_controls.height() + 8)
            self.display_controls.raise_()
            if hasattr(self, "current_reference"):
                self.update_current_reference()
            self.position_rc_controls()

    def position_rc_controls(self):
        if hasattr(self, "rc_controls"):
            self.rc_controls.setFixedWidth(max(120, min(460, self.viewport().width()-20)))
            self.rc_controls.adjustSize()
            self.rc_controls.move((self.viewport().width()-self.rc_controls.width())//2,
                                  max(8, self.viewport().height()-self.rc_controls.height()-10))
            self.rc_controls.raise_()

    def zoom_by(self, factor, position=None):
        current = self.transform().m11()
        target = max(0.05, min(8.0, current * factor))
        position = position if position is not None else self.viewport().rect().center()
        before = self.mapToScene(position)
        self.scale(target / current, target / current)
        after = self.mapToScene(position)
        delta = after - before
        self.translate(delta.x(), delta.y())
        self.update_zoom_percentage()

    def wheelEvent(self, event):
        delta = event.angleDelta().y() or event.pixelDelta().y()
        if delta:
            self.zoom_by(1.2 ** (max(-600, min(600, delta)) / 120), event.position().toPoint())
        event.accept()

    def fit_circuit(self):
        if self.scene().items():
            self.fitInView(self.scene().sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
            self.centerOn(self.scene().sceneRect().center())
            self.update_zoom_percentage()

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
        if event.button() == Qt.MouseButton.MiddleButton or (event.button() == Qt.MouseButton.LeftButton and self.pan_button.isChecked()):
            # Give the view scrollable space even when the whole circuit fits.
            center = self.mapToScene(self.viewport().rect().center())
            visible = self.mapToScene(self.viewport().rect()).boundingRect()
            self.setSceneRect(self.sceneRect().united(visible).adjusted(-visible.width(), -visible.height(), visible.width(), visible.height()))
            self.centerOn(center)
            self.pan_position = event.position().toPoint()
            self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
        else:
            component_id = None
            net_wire = None
            clicked_empty = False
            if event.button() == Qt.MouseButton.LeftButton:
                item = self.itemAt(event.position().toPoint())
                clicked_empty = item is None
                while item is not None:
                    symbol = item if isinstance(item, ComponentSymbol) else getattr(item, "symbol", None)
                    if isinstance(symbol, ComponentSymbol):
                        component_id = symbol.component.id
                        break
                    net = item if isinstance(item, NetWire) else getattr(item, "net", getattr(item, "net_wire", None))
                    if isinstance(net, NetWire):
                        net_wire = net
                        break
                    item = item.parentItem()
            super().mousePressEvent(event)
            if component_id is not None:
                self.component_clicked.emit(component_id)
            elif net_wire is not None and net_wire.net_id is not None:
                self.node_clicked.emit(net_wire.net_id, net_wire.pinned)
            elif clicked_empty:
                self.selection_cleared.emit()

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
        if self.pan_position is not None and event.button() in (Qt.MouseButton.MiddleButton, Qt.MouseButton.LeftButton):
            self.pan_position = None
            self.viewport().setCursor(self.pan_cursor if self.pan_button.isChecked() else QCursor(Qt.CursorShape.ArrowCursor))
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
        self.setFixedSize(52, 52)
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


class AppHeader(QFrame):
    """Light turquoise header background with individually raised action controls."""
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#fafcfb"))


class SettingsButton(QPushButton):
    """Borderless vector settings icon with grey hover/pressed tints."""

    def __init__(self, path):
        super().__init__()
        self.renderer = QSvgRenderer(str(path))
        if not self.renderer.isValid():
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
        size = round(20 * ratio)
        icon = QPixmap(size, size)
        icon.fill(Qt.GlobalColor.transparent)
        vector_painter = QPainter(icon)
        self.renderer.render(vector_painter, QRectF(0, 0, size, size))
        vector_painter.end()
        tint = QColor("#42447a" if self.isDown() or self.underMouse() else "#263c3f")
        painter = QPainter(icon)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
        painter.fillRect(icon.rect(), tint)
        painter.end()
        icon.setDevicePixelRatio(ratio)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#e5e5ef" if self.isDown() else "#f4f3f8" if self.underMouse() else "#ffffff"))
        painter.drawRoundedRect(QRectF(self.rect()), 12, 12)
        width, height = icon.width() / ratio, icon.height() / ratio
        painter.drawPixmap(QRectF((self.width() - width) / 2, (self.height() - height) / 2,
                                  width, height), icon, QRectF(icon.rect()))


class CircuitWindow(QMainWindow):
    def __init__(self, database=None):
        super().__init__()
        app = QApplication.instance()
        if not hasattr(app, "hover_tooltip_filter"):
            app.hover_tooltip_filter = NoHoverTooltips(app)
            app.installEventFilter(app.hover_tooltip_filter)
        self.database = database
        self.draft_circuit_name = None
        self.saved_record_name = None
        self.saved_document = None
        self.blank_original_name = "circuit-name"
        self.topology_valid = False
        self.hardware_topology_revision = None
        self.power_granted = False
        self.safety_panel = None
        self.safety_alert_key = ()
        self.request_issues = ()
        self.safety_limits = SafetyLimits(3.3, 1.5)
        self.power_protection = PowerProtection(self.safety_limits)
        self.safety_report = SafetyReport((SafetyIssue("no_circuit", "Load a circuit before enabling power."),))
        self.power_protection.update_report(self.safety_report)
        self.examples_dialog = None
        self.preferences = QSettings("SimpleCircuits", "Desktop")
        self.current_display = self.preferences.value("display/current", "arrows")
        if self.current_display not in ("arrows", "signed"):
            self.current_display = "arrows"
        self.highlight_colors = dict(DEFAULT_HIGHLIGHT_COLORS)
        for role in self.highlight_colors:
            stored = self.preferences.value("highlights/" + role)
            if stored and QColor(str(stored)).isValid():
                self.highlight_colors[role] = QColor(str(stored)).name()
        selection = self.preferences.value("highlights/selection", self.highlight_colors["node"])
        selection = QColor(str(selection)).name() if QColor(str(selection)).isValid() else DEFAULT_HIGHLIGHT_COLORS["node"]
        self.highlight_colors["component"] = self.highlight_colors["node"] = selection

        self.setWindowTitle("Circuit Schematic")
        self.resize(1440, 800)
        self.setMinimumSize(1100, 600)

        root = QWidget()
        self.setCentralWidget(root)
        self.statusBar().setSizeGripEnabled(False)
        self.statusBar().messageChanged.connect(lambda message: self.statusBar().setVisible(bool(message)))
        self.statusBar().hide()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = AppHeader()
        header.setObjectName("header")
        header.setFixedHeight(96)
        header_divider = QFrame(header)
        header_divider.setObjectName("headerEdgeDivider")
        header_divider.setStyleSheet("QFrame#headerEdgeDivider { background: #d9dddd; border: none; }")
        header_divider.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        header_divider.hide()
        header.edge_divider = header_divider
        edge_shadow = QGraphicsDropShadowEffect(header)
        edge_shadow.setBlurRadius(12)
        edge_shadow.setOffset(0, 3)
        edge_shadow.setColor(QColor(26, 49, 55, 35))
        header.setGraphicsEffect(edge_shadow)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(24, 20, 16, 12)
        header_layout.setSpacing(12)
        left_header = QWidget()
        left_layout = QHBoxLayout(left_header)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)

        logo_path = Path(__file__).resolve().parent / "assets" / "images" / "simple_circuits_logo.png"
        logo = LogoWidget(logo_path)
        logo.setObjectName("logo")
        logo.setStyleSheet("background: transparent;")
        logo.setAccessibleName("Simple Circuits logo")
        logo.setToolTip("Simple Circuits")
        left_layout.addWidget(logo)

        self.circuit_name = QLineEdit("circuit-name")
        self.circuit_name.setObjectName("circuitName")
        self.circuit_name.setAccessibleName("Circuit name")
        self.circuit_name.setReadOnly(True)
        self.circuit_name.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.circuit_name.setCursor(Qt.CursorShape.ArrowCursor)
        self.circuit_name.setFixedSize(200, 44)
        self.circuit_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.circuit_name.textChanged.connect(self.resize_circuit_title)
        self.circuit_name.setToolTip("Click the pencil to rename; click Save to keep changes")
        pencil_path = Path(__file__).resolve().parent / "assets" / "images" / "pencil.svg"
        pencil_renderer = QSvgRenderer(pencil_path.read_bytes().replace(b"currentColor", b"#000000"))
        pencil = QPixmap(72, 72)
        pencil.setDevicePixelRatio(3)
        pencil.fill(Qt.GlobalColor.transparent)
        pencil_painter = QPainter(pencil)
        pencil_renderer.render(pencil_painter, QRectF(0, 0, 24, 24))
        pencil_painter.end()
        edit_title = self.circuit_name.addAction(QIcon(pencil), QLineEdit.ActionPosition.TrailingPosition)
        for pencil_button in self.circuit_name.findChildren(QToolButton):
            if pencil_button.defaultAction() == edit_title:
                pencil_button.setIconSize(QSize(24, 24))
        edit_title.setToolTip("Rename circuit")
        edit_title.triggered.connect(self.edit_circuit_title)
        left_layout.addWidget(self.circuit_name)
        self.settings_button = IconTextButton("")
        self.settings_button.setAccessibleName("Settings")
        self.settings_button.setToolTip("Settings")
        self.settings_button.clicked.connect(self.show_settings)
        # Match visible icon gaps: utility icons have 10px of inset on each side.
        left_layout.addSpacing(10)
        left_layout.addWidget(self.settings_button)
        left_layout.addStretch()
        right_header = QWidget()
        right_layout = QHBoxLayout(right_header)
        right_layout.setContentsMargins(10, 10, 10, 10)
        right_layout.setSpacing(12)
        right_layout.addStretch()
        self.examples_button = self.button("Circuit Library")
        self.examples_button.clicked.connect(self.show_examples)
        self.examples_button.hide()
        self.new_circuit_button = IconTextButton("New Circuit")
        self.new_circuit_button.clicked.connect(self.new_circuit)
        right_layout.addWidget(self.new_circuit_button)
        self.save_button = IconTextButton("Save")
        self.save_button.clicked.connect(self.save_circuit_title)
        self.guide_button = IconTextButton("")
        self.guide_button.setAccessibleName("Open Circuit Guide")
        self.guide_button.clicked.connect(self.show_guide)
        left_layout.insertWidget(left_layout.count() - 1, self.guide_button)
        right_layout.addWidget(self.save_button)
        self.export_button = IconTextButton("Export to Falstad")
        self.export_button.clicked.connect(self.open_in_falstad)
        right_layout.addWidget(self.export_button)
        for button, asset in ((self.new_circuit_button, "file-plus.svg"),
                              (self.settings_button, "settings.svg"),
                              (self.save_button, "save.svg"),
                              (self.guide_button, "circle-help.svg"),
                              (self.export_button, "square-arrow-up-right-exit.svg")):
            button.setObjectName("headerActionButton")
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            path = Path(__file__).resolve().parent / "assets" / "images" / asset
            renderer = QSvgRenderer(path.read_bytes().replace(b"currentColor", b"#000000").replace(b"#222222", b"#000000"))
            icon = QPixmap(72, 72) if button in (self.settings_button, self.guide_button) else QPixmap(60, 60)
            icon.setDevicePixelRatio(3)
            icon.fill(Qt.GlobalColor.transparent)
            icon_painter = QPainter(icon)
            icon_extent = 24 if button in (self.settings_button, self.guide_button) else 20
            renderer.render(icon_painter, QRectF(0, 0, icon_extent, icon_extent))
            icon_painter.end()
            button.setIcon(QIcon(icon))
            button.setIconSize(QSize(icon_extent, icon_extent))
            button.setFixedHeight(44)
            button.setStyleSheet("""
                QPushButton#headerActionButton {
                    background: #ffffff; color: #000000;
                    border: none; border-radius: 12px;
                    padding: 10px 10px; font-size: 14px;
                }
                QPushButton#headerActionButton::menu-indicator { image: none; width: 0px; }
                QPushButton#headerActionButton:hover { background: #f1f1f1; color: #555555; }
                QPushButton#headerActionButton:pressed { background: #f1f1f1; color: #555555; }
                QPushButton#headerActionButton:focus { border: none; }
            """)
        header_layout.addWidget(left_header)
        header_layout.addStretch()
        header_layout.addWidget(right_header)
        layout.addWidget(header)

        body = QHBoxLayout()
        body.setContentsMargins(16, 14, 16, 16)
        body.setSpacing(16)
        layout.addLayout(body, 1)

        panel = QFrame()
        panel.setObjectName("controlPanel")
        panel.setFixedWidth(280)
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        panel_layout.setSpacing(16)
        panel_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        navigation_frame = QFrame()
        navigation_frame.setObjectName("navigationFrame")
        navigation_frame.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        navigation_frame.setStyleSheet("QFrame#navigationFrame { background-color: #fafcfb; border: none; border-radius: 14px; }")
        navigation_frame.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        navigation_shadow = QGraphicsDropShadowEffect(navigation_frame)
        navigation_shadow.setBlurRadius(18)
        navigation_shadow.setOffset(0, 0)
        navigation_shadow.setColor(QColor(26, 49, 55, 65))
        navigation_frame.setGraphicsEffect(navigation_shadow)
        navigation_layout = QVBoxLayout(navigation_frame)
        navigation_layout.setContentsMargins(16, 16, 16, 16)
        navigation_layout.setSpacing(2)
        self.navigation_frame = navigation_frame
        self.navigation_layout = navigation_layout
        panel_layout.addWidget(navigation_frame)
        self.page_navigation = QButtonGroup(self)
        self.page_navigation.setExclusive(True)
        self.navigation_buttons = []
        for index, (asset, title) in enumerate((("circuit-board.svg", "Circuit"), ("square-user-round.svg", "My Circuits"), ("square-library.svg", "Circuit Library"))):
            button = IconTextButton(title, align_left=True)
            if asset:
                path = Path(__file__).resolve().parent / "assets" / "images" / asset
                vector_icon = QIcon()
                for state, colour in ((QIcon.State.Off, "#222222"), (QIcon.State.On, "#42447a")):
                    renderer = QSvgRenderer(path.read_bytes().replace(b"currentColor", colour.encode()))
                    pixmap = QPixmap(66, 66)
                    pixmap.setDevicePixelRatio(3)
                    pixmap.fill(Qt.GlobalColor.transparent)
                    painter = QPainter(pixmap)
                    renderer.render(painter, QRectF(0, 0, 22, 22))
                    painter.end()
                    vector_icon.addPixmap(pixmap, QIcon.Mode.Normal, state)
                button.setIcon(vector_icon)
                button.setIconSize(QSize(22, 22))
            button.setObjectName("pageNavigation")
            button.setGraphicsEffect(None)
            button.setCheckable(True)
            button.setChecked(index == 0)
            self.page_navigation.addButton(button, index)
            self.navigation_buttons.append(button)
            navigation_layout.addWidget(button)

        def sidebar_card(title):
            card = QFrame()
            card.setObjectName("sidebarCard")
            add_list_row_shadow(card)
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(12, 12, 12, 12)
            card_layout.setSpacing(10)
            heading = QLabel(title)
            heading.setWordWrap(True)
            heading.setMinimumWidth(0)
            heading.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
            heading.setStyleSheet("font-family: 'DM Sans'; font-size: 14.5px; font-weight: 600; background: transparent;")
            card_layout.addWidget(heading)
            return card, card_layout

        self.circuit_sidebar = QWidget()
        self.circuit_sidebar.setObjectName("circuitSidebarContent")
        self.circuit_sidebar.setStyleSheet("QWidget#circuitSidebarContent { background: " + PANEL_BACKGROUND + "; }")
        self.circuit_sidebar.setMinimumWidth(0)
        self.circuit_sidebar.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        circuit_sidebar_layout = QVBoxLayout(self.circuit_sidebar)
        circuit_sidebar_layout.setContentsMargins(0, 0, 0, 0)
        circuit_sidebar_layout.setSpacing(10)
        connectivity, connection_layout = sidebar_card("Connectivity")
        self.connection_status = QLabel("●  Not connected")
        self.connection_status.setStyleSheet("color: #666666;")
        connection_layout.addWidget(self.connection_status)
        self.connection_device = QLabel("Device: —")
        self.connection_port = QLabel("Port: —")
        connection_layout.addWidget(self.connection_device)
        connection_layout.addWidget(self.connection_port)
        circuit_sidebar_layout.addWidget(connectivity)
        upload, upload_layout = sidebar_card("Circuit Upload")
        self.last_uploaded_label = QLabel("Last uploaded: —")
        self.last_synced_label = QLabel("Last synced: —")
        upload_layout.addWidget(self.last_uploaded_label)
        upload_layout.addWidget(self.last_synced_label)
        circuit_sidebar_layout.addWidget(upload)
        self.circuit_status_card, status_layout = sidebar_card("Safety Checks")
        self.status_summary = QLabel("Waiting for a circuit")
        self.status_summary.setWordWrap(True)
        self.status_summary.hide()
        self.safety_panel = SafetyAlertsPanel(self.circuit_status_card, embedded=True)
        self.safety_panel.issue_selected.connect(self.inspect_safety_issue)
        self.safety_panel.set_issues(())
        status_layout.addWidget(self.safety_panel)
        circuit_sidebar_layout.insertWidget(0, self.circuit_status_card)
        circuit_sidebar_layout.addStretch(1)
        self.circuit_sidebar_scroll = QScrollArea()
        self.circuit_sidebar_scroll.setWidgetResizable(True)
        self.circuit_sidebar_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.circuit_sidebar_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.circuit_sidebar_scroll.setWidget(self.circuit_sidebar)
        self.circuit_sidebar_scroll.setStyleSheet("QScrollArea { background: " + PANEL_BACKGROUND + "; border: none; } QScrollArea > QWidget { background: " + PANEL_BACKGROUND + "; } QScrollBar:vertical { width: 6px; }")
        self.connection_section_frame = QFrame()
        self.connection_section_frame.setObjectName("connectionSectionFrame")
        self.connection_section_frame.setStyleSheet("QFrame#connectionSectionFrame { background: " + PANEL_BACKGROUND + "; border: none; border-radius: 14px; }")
        outer_shadow = QGraphicsDropShadowEffect(self.connection_section_frame)
        outer_shadow.setBlurRadius(18)
        outer_shadow.setOffset(0, 0)
        outer_shadow.setColor(QColor(26, 49, 55, 65))
        self.connection_section_frame.setGraphicsEffect(outer_shadow)
        section_layout = QVBoxLayout(self.connection_section_frame)
        section_layout.setContentsMargins(16, 16, 16, 16)
        section_layout.setSpacing(12)
        information_header = QWidget()
        information_header.setStyleSheet("background: transparent;")
        information_layout = QVBoxLayout(information_header)
        information_layout.setContentsMargins(0, 0, 0, 0)
        information_layout.setSpacing(12)
        information_title = QLabel("Circuit Status")
        information_title.setStyleSheet("font-family: 'Space Grotesk'; font-size: 16px; font-weight: 600; color: #222222; background: transparent;")
        information_title_row = QHBoxLayout()
        information_title.setMinimumHeight(24)
        information_title_row.setContentsMargins(0, 0, 0, 0)
        information_title_row.addWidget(information_title, 1)
        self.status_close_button = QPushButton("×")
        self.status_close_button.setFixedSize(24, 24)
        self.status_close_button.setAccessibleName("Hide Circuit Status")
        self.status_close_button.setStyleSheet("QPushButton { background: transparent; border: none; padding: 0px; border-radius: 6px; } QPushButton:hover { background: #f7f9f9; }")
        self.status_close_button.hide()
        information_layout.addLayout(information_title_row)
        information_divider = QFrame()
        information_divider.setFixedHeight(1)
        information_divider.setStyleSheet("background: #cdd8d6; border: none;")
        information_layout.addWidget(information_divider)
        section_layout.addWidget(information_header)
        section_layout.addWidget(self.circuit_sidebar_scroll)
        panel_layout.addWidget(self.connection_section_frame, 1)

        self.component_legend = QTableWidget(0, 2)
        self.component_legend.setAccessibleName("Circuit component legend")
        self.component_legend.setHorizontalHeaderLabels(["Name", "Symbol"])
        self.component_legend.setShowGrid(False)
        self.component_legend.horizontalHeader().hide()
        self.component_legend.setStyleSheet("QTableWidget { background: #ffffff; border: none; }")
        self.component_legend.setIconSize(QSize(100, 56))
        self.component_legend.verticalHeader().hide()
        self.component_legend.setMinimumWidth(0)
        self.component_legend.horizontalHeader().setMinimumSectionSize(24)
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
        self.component_legend.hide()


        self.scene = QGraphicsScene(self)
        self.scene.setProperty("highlightColors", self.highlight_colors)
        self.scene.setProperty("currentDisplay", self.current_display)
        self.canvas = SchematicView(self.scene)
        self.rc_preview_result = None
        self.rc_preview_timing = None
        self.rc_endpoints = None
        self.rc_preview_position = None
        self.canvas.rc_time_changed.connect(self.preview_rc_time)
        self.canvas.rc_settled_requested.connect(self.restore_settled_dc)
        self.canvas.grid_visible = self.preferences.value("display/grid", True, type=bool)
        self.canvas.setObjectName("schematicCanvas")
        self.canvas.setFrameShape(QFrame.Shape.NoFrame)
        self.canvas.setAccessibleName("Circuit schematic canvas")
        self.canvas.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.circuit = None
        self.simulation_result = None
        schematic_area = QVBoxLayout()
        schematic_area.setContentsMargins(10, 10, 10, 10)
        schematic_area.setSpacing(8)
        self.safety_status_text = "Waiting for a circuit"
        self.schematic_frame = QFrame()
        self.schematic_frame.setObjectName("schematicFrame")
        outer_shadow = QGraphicsDropShadowEffect(self.schematic_frame)
        outer_shadow.setBlurRadius(18)
        outer_shadow.setOffset(0, 0)
        outer_shadow.setColor(QColor(26, 49, 55, 65))
        self.schematic_frame.setGraphicsEffect(outer_shadow)
        frame_layout = QVBoxLayout(self.schematic_frame)
        frame_layout.setContentsMargins(16, 16, 16, 16)
        frame_layout.addWidget(self.canvas)
        schematic_area.addWidget(self.schematic_frame, 1)
        self.protection_timer = QTimer(self)
        self.protection_timer.setInterval(100)
        self.protection_timer.timeout.connect(self.poll_power_protection)
        self.protection_timer.start()
        circuit_page = QWidget()
        circuit_page.setLayout(schematic_area)
        self.content_pages = QStackedWidget()
        self.content_pages.addWidget(circuit_page)
        self.my_circuits_page = CircuitLibraryPage(title="My Circuits", empty_message="No saved circuits yet. Use Save to keep your current circuit here.")
        self.my_circuits_page.circuit_requested.connect(self.open_saved_circuit)
        self.content_pages.addWidget(self.my_circuits_page)
        self.library_page = CircuitLibraryPage()
        self.library_page.circuit_requested.connect(self.open_library_circuit)
        self.content_pages.addWidget(self.library_page)
        self.page_navigation.idClicked.connect(self.change_workspace_page)
        self.content_pages.setObjectName("workspaceFrame")

        right_column = QVBoxLayout()
        right_column.setContentsMargins(0, 0, 0, 0)
        self.component_details = ComponentDetailsPanel()
        self.component_details.current_display = self.current_display
        self.component_details.component_list = self.component_legend
        self.component_details.node_requested.connect(self.select_node_details)
        self.canvas.component_clicked.connect(self.select_component_details)
        self.canvas.node_clicked.connect(self.select_node_details)
        self.canvas.selection_cleared.connect(self.clear_component_selection)
        self.component_details.clear_requested.connect(self.clear_component_selection)
        # A nested main window keeps dockable panels inside the application header.
        self.workspace = QMainWindow()
        self.workspace.setDockNestingEnabled(True)
        self.workspace.setCentralWidget(self.content_pages)
        self.workspace.setStyleSheet("QMainWindow::separator { width: 4px; height: 4px; background: transparent; } QDockWidget { font-size: 14px; font-weight: bold; } QDockWidget::title { background: #edf4f2; padding: 8px; }")
        self.navigation_dock = QDockWidget("Navigation", self.workspace)
        self.navigation_dock.setFeatures(QDockWidget.DockWidgetFeature.NoDockWidgetFeatures)
        navigation_title = QWidget()
        navigation_title.setFixedHeight(0)
        self.navigation_dock.setTitleBarWidget(navigation_title)
        navigation_container = QWidget()
        navigation_container.setObjectName("navigationShadowWrapper")
        navigation_container.setStyleSheet("QWidget#navigationShadowWrapper { background: transparent; }")
        navigation_container_layout = QVBoxLayout(navigation_container)
        navigation_container_layout.setContentsMargins(10, 10, 10, 10)
        navigation_container_layout.addWidget(navigation_frame)
        self.navigation_dock.setWidget(navigation_container)
        self.navigation_dock.setMaximumWidth(280)
        self.workspace.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.navigation_dock)
        self.status_dock = QDockWidget("Circuit Status", self.workspace)
        self.status_dock.setObjectName("circuitStatusDock")
        def shadow_wrapper(panel, name):
            wrapper = QWidget()
            wrapper.setObjectName(name)
            wrapper.setStyleSheet(f"QWidget#{name} {{ background: transparent; }}")
            wrapper_layout = QVBoxLayout(wrapper)
            wrapper_layout.setContentsMargins(10, 10, 10, 10)
            wrapper_layout.setSpacing(0)
            wrapper_layout.addWidget(panel)
            return wrapper
        self.status_dock.setWidget(shadow_wrapper(self.connection_section_frame, "statusShadowWrapper"))
        information_header.show()
        self.overview_dock = QDockWidget("Circuit Overview", self.workspace)
        self.overview_dock.setObjectName("circuitOverviewDock")
        self.overview_dock.setWidget(shadow_wrapper(self.component_details, "overviewShadowWrapper"))
        for dock in (self.status_dock, self.overview_dock):
            dock.setFeatures(QDockWidget.DockWidgetFeature.NoDockWidgetFeatures)
            dock.setMinimumWidth(0)
            dock.setMaximumWidth(280)
            # Resize at the side edges; no floating handle or duplicate title bar.
            handle = QWidget(dock)
            handle.setFixedHeight(0)
            dock.setTitleBarWidget(handle)
        self.workspace.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.status_dock)
        self.workspace.splitDockWidget(self.navigation_dock, self.status_dock, Qt.Orientation.Vertical)
        self.workspace.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.overview_dock)
        self.workspace.resizeDocks([self.navigation_dock, self.overview_dock], [280, 280], Qt.Orientation.Horizontal)
        self.workspace.resizeDocks([self.navigation_dock, self.status_dock], [200, 600], Qt.Orientation.Vertical)
        body.addWidget(self.workspace, 1)
        self.panel_visibility = [True, True]
        self.views_button = IconTextButton("")
        self.views_button.setAccessibleName("Views")
        views_path = Path(__file__).resolve().parent / "assets" / "images" / "columns-2.svg"
        views_renderer = QSvgRenderer(views_path.read_bytes().replace(b"currentColor", b"#000000"))
        views_icon = QPixmap(72, 72)
        views_icon.setDevicePixelRatio(3)
        views_icon.fill(Qt.GlobalColor.transparent)
        views_painter = QPainter(views_icon)
        views_renderer.render(views_painter, QRectF(0, 0, 24, 24))
        views_painter.end()
        self.views_button.setIcon(QIcon(views_icon))
        self.views_button.setIconSize(QSize(24, 24))
        self.views_button.setObjectName("headerActionButton")
        self.views_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.views_button.setFixedHeight(44)
        self.views_button.setStyleSheet(self.guide_button.styleSheet())
        self.views_menu = RoundedMenu(self.views_button)
        self.view_actions = []
        for index, title in enumerate(("Circuit Status", "Circuit Overview")):
            action = self.views_menu.addAction(title)
            action.setCheckable(True)
            action.setChecked(True)
            action.toggled.connect(lambda checked, panel=index: self.toggle_workspace_panel(panel, checked))
            self.view_actions.append(action)
        self.status_close_button.clicked.connect(lambda: self.view_actions[0].setChecked(False))
        self.component_details.panel_close_requested.connect(lambda: self.view_actions[1].setChecked(False))
        for icon_button in (self.settings_button, self.guide_button, self.views_button):
            icon_button.setFixedSize(44, 44)
        for icon_button in (self.settings_button, self.guide_button, self.views_button):
            icon_button.setStyleSheet("QPushButton#headerActionButton { background: transparent; color: black; border: none; padding: 10px; } QPushButton#headerActionButton:hover, QPushButton#headerActionButton:pressed { background: transparent; color: #555555; }")
        for action_button in (self.new_circuit_button, self.save_button, self.export_button):
            action_button.setStyleSheet(action_button.styleSheet() + "QPushButton#headerActionButton, QPushButton#headerActionButton:focus { border: none; }")
        for raised_control in (self.circuit_name, self.new_circuit_button,
                               self.save_button, self.export_button):
            header_shadow = QGraphicsDropShadowEffect(raised_control)
            header_shadow.setBlurRadius(18)
            header_shadow.setOffset(0, 0)
            header_shadow.setColor(QColor(26, 49, 55, 65))
            raised_control.setGraphicsEffect(header_shadow)
        for utility, asset in ((self.settings_button, "settings.svg"),
                               (self.guide_button, "circle-help.svg"),
                               (self.views_button, "columns-2.svg")):
            utility_icon = QIcon()
            svg = (Path(__file__).resolve().parent / "assets" / "images" / asset).read_bytes()
            for mode, colour in ((QIcon.Mode.Normal, b"#000000"), (QIcon.Mode.Active, b"#555555")):
                renderer = QSvgRenderer(svg.replace(b"currentColor", colour).replace(b"#222222", colour))
                pixmap = QPixmap(72, 72)
                pixmap.setDevicePixelRatio(3)
                pixmap.fill(Qt.GlobalColor.transparent)
                painter = QPainter(pixmap)
                renderer.render(painter, QRectF(0, 0, 24, 24))
                painter.end()
                utility_icon.addPixmap(pixmap, mode)
            utility.setIcon(utility_icon)
        self.views_button.setStyleSheet(self.views_button.styleSheet() + "QPushButton#headerActionButton::menu-indicator { image: none; width: 0px; height: 0px; }")
        self.views_button.setStyleSheet(self.views_button.styleSheet() + 'QPushButton#headerActionButton[menuOpen="true"] { background: #e7e3f3; border: none; border-radius: 12px; }')
        def mark_views_open(opened):
            self.views_button.setProperty("menuOpen", opened)
            self.views_button.style().unpolish(self.views_button)
            self.views_button.style().polish(self.views_button)
            self.views_button.update()
        self.views_menu.aboutToShow.connect(lambda: mark_views_open(True))
        self.views_menu.aboutToHide.connect(lambda: mark_views_open(False))
        self.views_button.setStyleSheet(self.views_button.styleSheet() + 'QPushButton#headerActionButton { padding: 0px; } QPushButton#headerActionButton:hover { background: #f1f1f1; border-radius: 12px; } QPushButton#headerActionButton[menuOpen="true"], QPushButton#headerActionButton[menuOpen="true"]:hover { background: #e7e3f3; border-radius: 12px; }')
        for utility_button in (self.settings_button, self.guide_button):
            utility_button.setStyleSheet(utility_button.styleSheet() + 'QPushButton#headerActionButton { padding: 0px; } QPushButton#headerActionButton:hover { background: #f1f1f1; border-radius: 12px; } QPushButton#headerActionButton[activeDialog="true"], QPushButton#headerActionButton[activeDialog="true"]:hover { background: #e7e3f3; border-radius: 12px; }')
        self.views_button.setMenu(self.views_menu)
        left_layout.insertWidget(left_layout.count() - 1, self.views_button)
        self.overview_toggle = OverviewToggle(self.centralWidget(), self.view_actions[1])
        self.status_toggle = StatusToggle(self.centralWidget(), self.view_actions[0])
        self.status_toggle.setAccessibleName("Toggle Circuit Status and navigation labels")

        self.setStyleSheet("""
            QFrame#schematicFrame { background: #ffffff; border: none; border-radius: 14px; }

            QFrame#navigationFrame { background: #fafcfb; border: none; border-radius: 14px; }
            QFrame#connectionSectionFrame { background: #fdfefe; border: none; border-radius: 14px; }
            QFrame#controlPanel { background: transparent; border: none; }
            QFrame#controlPanel, QFrame#controlPanel QWidget {
                font-family: "DM Sans"; font-size: 14px;
            }
            QFrame#controlPanel QHeaderView::section { font-weight: 500; }
            QFrame#controlPanel QPushButton#componentDisclosure:checked { font-weight: 500; }
            QFrame#sidebarCard { background: #e2ebe9; border: none; border-radius: 12px; }
            QPushButton#pageNavigation { font-family: "Space Grotesk"; font-weight: 500; text-align: left; padding: 12px; border: none; border-radius: 9px; background: transparent; }
            QPushButton#pageNavigation:hover { background: #f1f1f1; }
            QPushButton#pageNavigation:checked, QPushButton#pageNavigation:checked:hover { background: #e7e3f3; color: #42447a; border: none; border-radius: 12px; font-weight: 500; }

            QWidget {
                font-family: "DM Sans";
                background: #e3e9eb;
                color: #111111;
                font-size: 14px;
                font-weight: normal;
            }
            QFrame#header { background: transparent; border: none; }

            QLabel { background: transparent; }
            QPushButton, QToolButton, QCheckBox, QComboBox { font-family: "DM Sans"; font-weight: 500; }
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
            QScrollBar:vertical {
                background: transparent;
                width: 6px;
                margin: 0;
            }
            QScrollBar::handle:vertical {
                background: #b0b0b0;
                border-radius: 3px;
                min-height: 24px;
            }
            QScrollBar::handle:vertical:hover {
                background: #888888;
            }
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {
                height: 0;
                border: none;
                background: transparent;
            }
            QScrollBar::add-page:vertical,
            QScrollBar::sub-page:vertical {
                background: transparent;
            }
            QScrollBar:horizontal { background: transparent; height: 6px; margin: 0; }
            QScrollBar::handle:horizontal { background: #b0b0b0; border-radius: 3px; min-width: 24px; }
            QScrollBar::handle:horizontal:hover { background: #888888; }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; border: none; background: transparent; }
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background: transparent; }
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
                font-family: "Space Grotesk";                background: #ffffff;
                color: #000000;
                border: none;
                border-radius: 12px;
                font-size: 16px;
                font-weight: 600;
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
            QPushButton:disabled { color: #888888; background: #e4e4e4; border: 1px solid #b8b8b8; }
            QPushButton:hover { background: #f1f1f1; }
            QPushButton:pressed { background: #cccccc; }
            QPushButton:focus { border: 2px solid #777777; }
            QGraphicsView#schematicCanvas {
                background: #fafafa;
                border: none;
            }
        """)
        # Measure after the final font, padding and borders have been applied.
        navigation_frame.ensurePolished()
        for button in self.navigation_buttons:
            button.ensurePolished()
        navigation_layout.invalidate()
        navigation_layout.activate()
        for button in self.navigation_buttons:
            button.setFixedHeight(button.sizeHint().height())
        navigation_height = sum(button.height() for button in self.navigation_buttons) + 32 + 2 * navigation_layout.spacing()
        navigation_frame.setFixedHeight(navigation_height)
        self.navigation_dock.setFixedHeight(navigation_height + 20)
        # Both sidebar columns stop at the same minimum width.
        sidebar_minimum = max(self.navigation_dock.minimumSizeHint().width(),
                              self.status_dock.minimumSizeHint().width())
        self.status_dock.setMinimumWidth(sidebar_minimum)
        self.overview_dock.setMinimumWidth(sidebar_minimum)


    def resize_circuit_title(self, text):
        self.circuit_name.ensurePolished()
        width = self.circuit_name.fontMetrics().horizontalAdvance(text) + 64
        self.circuit_name.setFixedWidth(max(200, width))

    def workspace_document(self):
        data = copy.deepcopy(getattr(self, "circuit_document", None))
        if data is None:
            data = {"schema_version": 1, "name": self.draft_circuit_name or "Untitled", "ground_node": None, "components": [], "nets": []}
        data["name"] = self.circuit_name.text().strip()
        return data

    def has_unsaved_circuit(self):
        current = self.workspace_document()
        if self.saved_document is not None:
            return current != self.saved_document
        if self.circuit is not None:
            return True
        return self.blank_original_name is not None and current["name"] != self.blank_original_name

    def remember_saved_workspace(self, data):
        self.saved_record_name = None
        self.saved_document = None
        if self.database is not None:
            try:
                if data["name"] in self.database.list_names(origin="user") and self.database.load(data["name"]) == data:
                    self.saved_record_name = data["name"]
                    self.saved_document = copy.deepcopy(data)
            except (KeyError, OSError, sqlite3.Error, ValueError):
                pass

    def new_circuit(self):
        existing = getattr(self, "name_dialog", None)
        if existing is not None:
            existing.raise_()
            existing.activateWindow()
            return
        if self.has_unsaved_circuit():
            choice = QMessageBox.question(
                self, "Unsaved circuit", "Save the current circuit before starting a new one?",
                QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if choice == QMessageBox.StandardButton.Cancel:
                return
            if choice == QMessageBox.StandardButton.Save:
                if not self.save_circuit_title():
                    return
        self.create_blank_circuit()

    def create_blank_circuit(self, name=None, document=None):
        """Start an empty workspace without modifying saved records or firmware."""
        if name is None:
            if self.database is None:
                self.database = CircuitDatabase()
            names = set(self.database.list_names(origin="user"))
            untitled_names = {name for name in names
                              if name.startswith("Untitled ") and name[9:].isdigit()}
            number = len(untitled_names) + 1
            while f"Untitled {number}" in names:
                number += 1
            name = f"Untitled {number}"
        self.circuit = None
        self.circuit_document = copy.deepcopy(document) if document is not None else {
            "schema_version": 1, "name": name, "ground_node": None, "components": [], "nets": []}
        self.saved_record_name = None
        self.saved_document = None
        self.blank_original_name = name
        self.simulation_result = SimulationResult("empty", "Waiting for circuit topology")
        self.topology_valid = False
        self.hardware_topology_revision = None
        self.power_granted = False
        self.request_issues = ()
        self.selected_safety_issue = None
        self.focused_short_issue = None
        self.rc_preview_result = None
        self.rc_preview_position = None
        self.rc_preview_timing = None
        self.rc_endpoints = None
        self.rlc_model = None
        self.canvas.rc_controls.hide()
        self.safety_report = SafetyReport((SafetyIssue("no_circuit", "Waiting for circuit topology."),))
        self.power_protection.update_report(self.safety_report, topology_changed=True)
        self.component_details.overview_circuit = None
        self.component_details.rc_preview_position = None
        self.component_legend.setRowCount(0)
        self.component_details.clear_selection()
        self.scene.clear()
        self.canvas.resetTransform()
        self.scene.setSceneRect(QRectF(-200, -150, 400, 300))
        message = self.scene.addText("Waiting for circuit topology", QApplication.font())
        message.setDefaultTextColor(QColor("#687b77"))
        message.setPos(-message.boundingRect().width()/2, -message.boundingRect().height()/2)
        message.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.canvas.centerOn(0, 0)
        self.canvas.update_zoom_percentage()
        self.canvas.position_rc_controls()
        self.draft_circuit_name = name
        self.circuit_name.setText(self.draft_circuit_name)
        self.circuit_name.setToolTip("Rename this workspace; click Save to keep changes")
        self.circuit_name.setModified(False)
        self.last_uploaded_label.setText("Last uploaded: —")
        self.last_synced_label.setText("Last synced: —")
        self.refresh_safety_status(redraw=False)
        self.navigation_buttons[0].setChecked(True)
        self.change_workspace_page(0)
        self.view_actions[1].setChecked(False)
        self.toggle_workspace_panel(1, False)
        self.save_button.setEnabled(True)
        self.export_button.setEnabled(False)
        self.statusBar().clearMessage()

    def edit_circuit_title(self):
        existing = getattr(self, "name_dialog", None)
        if existing is not None:
            existing.raise_()
            existing.activateWindow()
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Rename circuit")
        dialog.setObjectName("renameCircuitDialog")
        dialog.setStyleSheet("QDialog#renameCircuitDialog QPushButton { padding: 8px 16px; min-height: 20px; border: none; border-radius: 8px; background: #e7e3f3; color: #222222; } QDialog#renameCircuitDialog QPushButton:hover { background: #dcd5ed; }")
        dialog.setMinimumWidth(420)
        dialog.resize(420, 240)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)
        layout.addWidget(QLabel("Circuit name"))
        name_field = QLineEdit(self.circuit_name.text())
        name_field.setObjectName("savedCircuitName")
        name_field.setAccessibleName("Circuit name")
        name_field.setStyleSheet("background: white; border: none; border-radius: 8px; padding: 10px;")
        layout.addWidget(name_field)
        hint = QLabel("Renaming changes this workspace only. Click Save in the header to keep the changes.")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        error = QLabel()
        error.setObjectName("nameSaveError")
        error.setWordWrap(True)
        error.setStyleSheet("color: #b53e2b;")
        error.hide()
        layout.addWidget(error)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("Rename")
        for button in buttons.buttons():
            button.ensurePolished()
            button.setMinimumWidth(button.fontMetrics().horizontalAdvance(button.text().replace("&", "")) + 40)
            button.setMinimumHeight(button.fontMetrics().height() + 20)
        layout.addWidget(buttons)
        def save_name():
            old_text = self.circuit_name.text()
            self.circuit_name.setText(name_field.text())
            if self.rename_circuit_title():
                dialog.accept()
            else:
                error.setText(self.circuit_name.toolTip())
                error.show()
                self.circuit_name.setText(old_text)
                name_field.setFocus()
        buttons.accepted.connect(save_name)
        buttons.rejected.connect(dialog.reject)
        name_field.returnPressed.connect(save_name)
        def closed(result):
            self.name_dialog = None
            dialog.deleteLater()
        dialog.finished.connect(closed)
        self.name_dialog = dialog
        dialog.open()
        name_field.setFocus()
        name_field.selectAll()

    def rename_circuit_title(self):
        name = self.circuit_name.text().strip()
        if not name:
            self.circuit_name.setText(self.circuit.name if self.circuit is not None else self.draft_circuit_name or "Untitled")
            self.circuit_name.setToolTip("Circuit name cannot be empty")
            return False
        self.draft_circuit_name = name
        if self.circuit is not None:
            self.circuit = replace(self.circuit, name=name)
        if self.circuit_document is not None:
            self.circuit_document = dict(self.circuit_document, name=name)
        self.circuit_name.setText(name)
        self.circuit_name.setModified(False)
        self.circuit_name.setToolTip("Renamed in this workspace; click Save to keep changes")
        self.circuit_name.clearFocus()
        return True

    def save_circuit_title(self):
        data = self.workspace_document()
        if not data["name"]:
            self.rename_circuit_title()
            return False
        try:
            if self.database is None:
                self.database = CircuitDatabase()
            self.database.save_workspace(data, previous_name=self.saved_record_name)
        except (OSError, sqlite3.Error, ValueError) as error:
            message = f"Could not save circuit: {error}"
            self.circuit_name.setToolTip(message)
            self.statusBar().showMessage(message, 6000)
            return False
        self.rename_circuit_title()
        self.circuit_document = copy.deepcopy(data)
        self.saved_record_name = data["name"]
        self.saved_document = copy.deepcopy(data)
        self.refresh_my_circuits()
        self.circuit_name.setToolTip("Saved; rename changes take effect in the database only when Save is clicked")
        self.statusBar().showMessage(f'Saved “{data["name"]}”.', 6000)
        return True

    def load_topology(self, data, hardware_revision=None):
        """Load controller JSON/dict; invalid input preserves the current circuit."""
        try:
            circuit = parse_topology(data)
        except TopologyError as error:
            self.topology_valid = False
            self.hardware_topology_revision = None
            self.safety_report = SafetyReport((SafetyIssue("invalid_topology", str(error)),))
            self.power_protection.update_report(self.safety_report)
            self.refresh_safety_status()
            return False
        document = copy.deepcopy(json.loads(data) if isinstance(data, (str, bytes)) else data)
        if not circuit.components and not circuit.nets:
            self.create_blank_circuit(name=circuit.name, document=document)
            self.remember_saved_workspace(document)
            return True
        self.circuit_document = document
        self.blank_original_name = None
        self.remember_saved_workspace(document)
        return self.display_circuit(circuit, hardware_revision=hardware_revision)

    def display_circuit(self, circuit, preserve_view=False, measurement_update=False, hardware_revision=None):
        center = self.canvas.mapToScene(self.canvas.viewport().rect().center())
        transform = self.canvas.transform()
        analysis_circuit = self.circuit_with_measured_voltage(circuit)
        self.simulation_result = solve_dc(analysis_circuit)
        if not measurement_update:
            self.power_granted = False
            if self.safety_panel is not None:
                self.safety_panel.reset_position()
            self.request_issues = ()
            self.topology_valid = True
            self.hardware_topology_revision = hardware_revision
        if self.topology_valid:
            self.safety_report = assess_circuit(analysis_circuit, self.safety_limits, self.simulation_result)
        self.power_protection.update_report(self.safety_report, topology_changed=not measurement_update,
                                            revision=self.hardware_topology_revision)
        self.refresh_safety_status(redraw=False)
        display_circuit = (replace(analysis_circuit, ground_node=self.simulation_result.ground_node)
                           if self.simulation_result.ground_node is not None else analysis_circuit)
        render_circuit(self.scene, display_circuit, self.simulation_result, self.current_safety_issues)
        # DC solver status messages are temporarily hidden.
        # self.statusBar().showMessage(
        #     "" if self.simulation_result.status == "solved" else self.simulation_result.message
        # )
        self.statusBar().clearMessage()
        self.statusBar().setToolTip("V = V1 − V2. Current displays magnitude; arrows indicate conventional current direction.")
        self.circuit = circuit
        self.save_button.setEnabled(True)
        self.export_button.setEnabled(self.content_pages.currentIndex() == 0)
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
        self.component_legend.setRowCount(2 * len(circuit.components))
        for index, component in enumerate(circuit.components):
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
            toggle = ComponentRowButton()
            toggle.setObjectName("detectedComponentRow")
            toggle.setCheckable(True)
            toggle.setAccessibleName(f"About {component.id} {names[component.type]}")
            toggle.setStyleSheet(OVERVIEW_ROW_STYLE)
            add_list_row_shadow(toggle)
            row_layout = QHBoxLayout(toggle)
            row_layout.setContentsMargins(8, 8, 8, 8)
            row_layout.setSpacing(8)
            icon_label = QLabel()
            icon_label.setPixmap(pixmap.scaled(QSize(round(60 * pixel_ratio), round(40 * pixel_ratio)), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            icon_label.setFixedSize(60, 44)
            icon_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            row_layout.addWidget(icon_label)
            from html import escape
            value = nominal_label(component)
            for prefix in (component.id + " = ", component.id + ": "):
                if value.startswith(prefix):
                    value = value[len(prefix):]
                    break
            if component.type == "voltage_source":
                value += " (DC)"
            text = QLabel(f'<span style="font-weight: 500;">{escape(component.id)} · {escape(names[component.type])}</span><br><span style="color: #111111;">{escape(value)}</span>')
            text.setWordWrap(True)
            text.setMinimumWidth(0)
            text.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
            text.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            row_layout.addWidget(text, 1)
            description = QLabel(COMPONENT_DESCRIPTIONS[component.type])
            description.setWordWrap(True)
            description.setContentsMargins(12, 10, 12, 12)
            description.setStyleSheet("background: #f5f5f5;")
            self.component_legend.setSpan(row, 0, 1, 2)
            self.component_legend.setCellWidget(row, 0, toggle)
            self.component_legend.setSpan(row + 1, 0, 1, 2)
            self.component_legend.setCellWidget(row + 1, 0, description)
            self.component_legend.setRowHeight(row, 72)
            self.component_legend.setRowHidden(row, False)
            self.component_legend.setRowHidden(row + 1, True)
            toggle.toggled.connect(
                lambda expanded, cid=component.id: self.select_component_details(cid, expanded)
            )
        self.component_details.overview_circuit = circuit
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
        self.canvas.update_zoom_percentage()
        self.configure_rc_preview(analysis_circuit)
        self.refresh_component_details()
        return True

    def configure_rc_preview(self, circuit):
        self.rc_preview_result = None
        self.rc_preview_position = None
        self.rc_preview_timing = None
        self.rc_endpoints = None
        self.rlc_model = None
        self.canvas.rc_controls.hide()
        if self.current_safety_issues or self.simulation_result.status != "solved":
            return
        storage = [c for c in circuit.components if c.type in ("capacitor", "inductor")]
        if len(storage) == 2 and {c.type for c in storage} == {"capacitor", "inductor"}:
            model, reason = series_rlc(circuit)
            if model is None:
                return
            self.rlc_model = model
            self.preview_kind = "RLC"
            self.rc_preview_timing, self.rc_endpoints = model, model
            self.canvas.rc_slider.blockSignals(True)
            self.canvas.rc_slider.setValue(0)
            self.canvas.rc_slider.blockSignals(False)
            self.canvas.rc_time_label.setText(f"RLC response · Settled DC · Drag to inspect 0–{model.duration_s:.4g} s")
            self.canvas.rc_controls.show()
            self.canvas.position_rc_controls()
            return
        if len(storage) != 1:
            return
        device = storage[0]
        self.preview_kind = "RL" if device.type == "inductor" else "RC"
        timing, reason = (rl_timing if device.type == "inductor" else rc_timing)(circuit, device.id)
        if timing is None:
            return
        endpoints = (rl_step_endpoints(circuit, device.id, timing, self.simulation_result)
                     if device.type == "inductor" else rc_step_endpoints(circuit, device.id, self.simulation_result))
        if endpoints is None:
            return
        self.rc_preview_timing, self.rc_endpoints = timing, endpoints
        self.canvas.rc_slider.blockSignals(True)
        self.canvas.rc_slider.setValue(0)
        self.canvas.rc_slider.blockSignals(False)
        self.canvas.rc_time_label.setText(f"{getattr(self, 'preview_kind', 'RC')} response · Settled DC · Drag to inspect 0–5τ")
        self.canvas.rc_controls.show()
        self.canvas.position_rc_controls()

    def preview_rc_time(self, position):
        if self.rc_preview_timing is None or self.current_safety_issues or self.rc_endpoints is None:
            return
        self.rc_preview_position = position
        time = position / 100 * self.rc_preview_timing.tau_s
        if getattr(self, "rlc_model", None) is not None:
            self.rc_preview_result = self.rlc_model.snapshot(time, self.simulation_result)
            self.canvas.rc_time_label.setText(f"Predicted RLC response · t = {time:.4g} s · {self.rlc_model.regime}")
            self.redraw_rc_preview()
            return
        self.rc_preview_result = rc_step_snapshot(self.rc_preview_timing, self.rc_endpoints, time)
        storage = next(c for c in self.circuit.components if c.type in ("capacitor", "inductor"))
        settled = self.simulation_result.components[storage.id]
        is_rl = storage.type == "inductor"
        phase = rc_response_phase(storage.parameters.get("initial_current_a" if is_rl else "initial_voltage_v", 0.0),
                                  settled.current_a if is_rl else settled.voltage_v)
        if is_rl:
            phase = {"charging": "current rise", "discharging": "current decay"}.get(phase, phase)
        progress = 100 * (1 - math.exp(-position / 100))
        status = "steady" if phase == "steady" else f"{progress:.1f}% {phase}"
        self.canvas.rc_time_label.setText(f"Predicted {self.preview_kind} response · t = {time:.4g} s ({status})")
        self.redraw_rc_preview()

    def restore_settled_dc(self):
        self.rc_preview_result = None
        self.rc_preview_position = None
        if getattr(self, "rlc_model", None) is not None:
            self.canvas.rc_time_label.setText(f"RLC response · Settled DC · Drag to inspect 0–{self.rlc_model.duration_s:.4g} s")
        else:
            self.canvas.rc_time_label.setText(f"{getattr(self, 'preview_kind', 'RC')} response · Settled DC · Drag to inspect 0–5τ")
        self.redraw_rc_preview()

    def redraw_rc_preview(self):
        if self.circuit is None:
            return
        center = self.canvas.mapToScene(self.canvas.viewport().rect().center())
        displayed = replace(self.circuit_with_measured_voltage(self.circuit), ground_node=self.simulation_result.ground_node)
        render_circuit(self.scene, displayed, self.rc_preview_result or self.simulation_result, self.current_safety_issues)
        self.canvas.centerOn(center)
        self.refresh_component_details()
        self.canvas.position_rc_controls()

    def select_component_details(self, component_id, selected=True):
        overview_was_hidden = self.overview_dock.isHidden()
        self.view_actions[1].setChecked(True)
        self.toggle_workspace_panel(1, True)
        self.selected_safety_issue = None
        self.focused_short_issue = None
        self.circuit_name.deselect()
        self.canvas.setFocus(Qt.FocusReason.MouseFocusReason)
        if self.component_details.component_id == component_id and not overview_was_hidden:
            self.clear_component_selection()
            return
        self.highlight_details_node(None)
        self.component_details.node_id = None
        self.component_details.component_id = component_id
        for row in range(0, self.component_legend.rowCount(), 2):
            button = self.component_legend.cellWidget(row, 0)
            if button is not None:
                button.blockSignals(True)
                button.setChecked(component_id in button.accessibleName().split())
                button.blockSignals(False)
        self.refresh_component_details()

    def clear_component_selection(self):
        self.selected_safety_issue = None
        self.focused_short_issue = None
        self.circuit_name.deselect()
        self.canvas.setFocus(Qt.FocusReason.MouseFocusReason)
        self.component_details.clear_selection()
        self.highlight_details_component(None)
        self.highlight_details_node(None)
        for row in range(0, self.component_legend.rowCount(), 2):
            button = self.component_legend.cellWidget(row, 0)
            if button is not None:
                button.blockSignals(True)
                button.setChecked(False)
                button.blockSignals(False)

    def highlight_details_component(self, component_id):
        for item in self.scene.items():
            if isinstance(item, ComponentSymbol):
                item.pinned = False
                related = [issue for issue in self.current_safety_issues
                           if item.component.id in issue.component_ids and not issue.terminal_refs]
                item.diagnostic_severity = ("error" if any(i.severity == "error" for i in related) else "warning") if related else None
                focused_short = getattr(self, "focused_short_issue", None)
                short_ids = focused_short.component_ids if focused_short in self.current_safety_issues else ()
                item.details_selected = item.component.id == component_id or item.component.id in short_ids
                if item.result_box is not None:
                    item.result_box.highlight(False)
                else:
                    item.set_highlight(False)

    def highlight_details_node(self, node_id):
        for item in self.scene.items():
            if isinstance(item, NetWire):
                nodes = self.circuit.terminal_nodes() if self.circuit else {}
                related = [issue for issue in self.current_safety_issues
                           if any(nodes.get(ref) == item.net_id for ref in issue.terminal_refs)]
                item.diagnostic_severity = ("error" if any(i.severity == "error" for i in related) else "warning") if related else None
                item.pinned = item.net_id == node_id
                item.highlight(False)

    def select_node_details(self, node_id, selected=True):
        self.circuit_name.deselect()
        self.canvas.setFocus(Qt.FocusReason.MouseFocusReason)
        if not selected:
            if self.component_details.node_id == node_id:
                self.clear_component_selection()
            return
        self.view_actions[1].setChecked(True)
        self.toggle_workspace_panel(1, True)
        self.clear_component_selection()
        self.component_details.node_id = node_id
        self.refresh_component_details()

    def refresh_component_details(self):
        readings = self.rc_preview_result or self.simulation_result
        self.component_details.rc_preview_position = self.rc_preview_position
        self.component_details.rc_time_requested = self.canvas.rc_slider.setValue
        self.component_details.rc_final_voltage = None
        self.component_details.rl_final_current = None
        node_id = self.component_details.node_id
        if node_id is not None:
            net = next((n for n in self.circuit.nets if n.id == node_id), None) if self.circuit else None
            if net is None:
                self.clear_component_selection()
                return
            voltage = (readings.node_voltages.get(node_id)
                       if not self.current_safety_issues and self.simulation_result.status == "solved" else None)
            self.highlight_details_node(node_id)
            self.component_details.set_node_content(net, voltage, self.simulation_result.ground_node)
            self.highlight_details_component(None)
            return
        cid = self.component_details.component_id
        component = next((c for c in self.circuit.components if c.id == cid), None) if self.circuit else None
        if component is None:
            self.component_details.clear_selection()
            return
        result = None
        if not self.current_safety_issues and self.simulation_result.status == "solved":
            result = readings.components.get(cid)
            dc_result = self.simulation_result.components.get(cid)
            self.component_details.rc_final_voltage = dc_result.voltage_v if dc_result else None
            self.component_details.rl_final_current = dc_result.current_a if dc_result else None
        self.component_details.set_content(component, result)
        self.highlight_details_component(cid)

    def set_navigation_compact(self, compact):
        if not hasattr(self, "navigation_frame"):
            return
        for button in self.navigation_buttons:
            if not hasattr(button, "navigation_label"):
                button.navigation_label = button.text()
            button.setText("" if compact else button.navigation_label)
            button.setAccessibleName(button.navigation_label)
            button.align_left = not compact
            button.setFixedHeight(44 if compact else button.sizeHint().height())
        margin = 10 if compact else 16
        self.navigation_layout.setContentsMargins(margin, margin, margin, margin)
        height = sum(button.height() for button in self.navigation_buttons) + 2 * margin + 2 * self.navigation_layout.spacing()
        self.navigation_frame.setFixedHeight(height)
        self.navigation_dock.setFixedHeight(height + 20)
        if compact:
            self.navigation_dock.setMinimumWidth(64)
            self.navigation_dock.setMaximumWidth(84)
            self.workspace.resizeDocks([self.navigation_dock], [84], Qt.Orientation.Horizontal)
        else:
            self.navigation_dock.setMaximumWidth(280)
            self.navigation_dock.setMinimumWidth(self.status_dock.minimumWidth())
            self.workspace.resizeDocks([self.navigation_dock], [280], Qt.Orientation.Horizontal)

    def toggle_workspace_panel(self, index, visible):
        self.panel_visibility[index] = visible
        if index == 0:
            self.set_navigation_compact(not visible)
        dock = (self.status_dock, self.overview_dock)[index]
        dock.setVisible(visible and self.content_pages.currentIndex() == 0)
        if hasattr(self, "overview_toggle"):
            self.overview_toggle.reposition()

    def set_workspace_panels(self, visible):
        if hasattr(self, "overview_toggle"):
            self.overview_toggle.setVisible(visible)
            self.overview_toggle.reposition()
        if hasattr(self, "status_toggle"):
            self.status_toggle.setVisible(visible)
            self.status_toggle.reposition()
        docks = (self.status_dock, self.overview_dock)
        for dock, wanted in zip(docks, self.panel_visibility):
            dock.setVisible(visible and wanted)

    def change_workspace_page(self, index):
        self.set_workspace_panels(index == 0)
        self.content_pages.setCurrentIndex(index)
        self.export_button.setEnabled(index == 0 and self.circuit is not None)
        if index == 1:
            self.show_my_circuits()
        elif index == 2:
            self.show_examples()

    def resize_component_legend(self):
        self.component_legend.setFixedHeight(
            (0 if self.component_legend.horizontalHeader().isHidden() else self.component_legend.horizontalHeader().height())
            + sum(self.component_legend.rowHeight(row)
                  for row in range(self.component_legend.rowCount())
                  if not self.component_legend.isRowHidden(row)) + 2
        )

    def toggle_component_description(self, row, label, button, name, expanded):
        for column in range(2):
            cell = self.component_legend.cellWidget(row - 1, column)
            if cell is None:
                continue
            cell.setProperty("expanded", expanded)
            cell.style().unpolish(cell)
            cell.style().polish(cell)
            cell.update()
        # Row stays free of disclosure arrows.
        width = max(100, self.component_legend.viewport().width())
        self.component_legend.setRowHeight(row, max(40, label.heightForWidth(width)))
        self.component_legend.setRowHidden(row, not expanded)
        self.resize_component_legend()

    def circuit_with_measured_voltage(self, circuit):
        guard = self.power_protection
        fresh = guard.last_sample is not None and 0 <= guard.clock() - guard.last_sample <= guard.timeout_s
        sources = [c for c in circuit.components if c.type == "voltage_source"]
        if guard.transport is None or not fresh or len(sources) != 1:
            return circuit
        return replace(circuit, components=tuple(
            replace(c, parameters={**c.parameters, "voltage_v": guard.voltage_v})
            if c.type == "voltage_source" else c for c in circuit.components))

    def refresh_safety_status(self, extra_issues=None, redraw=True):
        if extra_issues is not None:
            self.request_issues = tuple(extra_issues)
        guard = self.power_protection
        issues = tuple(self.safety_report.issues) + guard.runtime_issues + self.request_issues
        issues = tuple({(i.code, i.message): i for i in issues if i.code != "no_circuit"}.values())
        if issues or guard.transport is None or not self.topology_valid:
            self.power_granted = False
        self.current_safety_issues = issues
        if issues:
            self.rc_preview_result = None
            self.rc_preview_position = None
            self.canvas.rc_controls.hide()
            text = "Validation required — " + issues[0].message
        elif not self.topology_valid:
            text = "Waiting for a circuit"
        elif guard.transport is None:
            text = "Circuit checks passed — board not connected"
        else:
            text = "Circuit checks passed — waiting for the board’s enable request"
        self.safety_status_text = text
        checks_passed = self.topology_valid and not issues
        if issues:
            errors = sum(i.severity == "error" and i.code not in ("unknown_current", "unresolved_circuit") for i in issues)
            warnings = sum(i.severity == "warning" and i.code not in ("unknown_current", "unresolved_circuit") for i in issues)
            self.status_summary.setText(f"{errors} error{'s' if errors != 1 else ''} · {warnings} warning{'s' if warnings != 1 else ''}")
        else:
            self.status_summary.setText("Circuit checks passed" if checks_passed else "Waiting for a circuit")
        key = (checks_passed, tuple((i.code, i.severity, i.message) for i in issues))
        if key != self.safety_alert_key:
            self.safety_alert_key = key
            if issues or checks_passed:
                self.safety_panel.set_issues(issues, checks_passed=checks_passed)
                self.safety_panel.show()
            elif self.safety_panel is not None:
                self.safety_panel.set_issues(())
            if redraw and self.circuit is not None:
                displayed = replace(self.circuit_with_measured_voltage(self.circuit),
                                    ground_node=self.simulation_result.ground_node)
                render_circuit(self.scene, displayed, self.simulation_result, issues)
                self.refresh_component_details()

    def inspect_safety_issue(self, issue):
        if getattr(self, "selected_safety_issue", None) == issue:
            self.clear_component_selection()
            return
        target = None
        if self.circuit is None:
            return
        if issue.terminal_refs:
            node_id = self.circuit.terminal_nodes().get(issue.terminal_refs[0])
            if node_id is not None:
                self.select_node_details(node_id)
        elif issue.component_ids:
            component_id = (issue.component_ids[1] if issue.code == "supply_short" and len(issue.component_ids) > 1
                            else issue.component_ids[0])
            if self.component_details.component_id != component_id:
                self.select_component_details(component_id)
            else:
                self.refresh_component_details()
        if issue.code == "supply_short":
            self.focused_short_issue = issue
            self.highlight_details_component(self.component_details.component_id)
        for item in self.scene.items():
            if issue in getattr(item, "issues", ()):
                target = item
                break
        if target is None:
            for item in self.scene.items():
                if isinstance(item, ComponentSymbol) and item.component.id in issue.component_ids:
                    target = item
                    break
        if issue.component_ids or issue.terminal_refs:
            self.selected_safety_issue = issue
        if target is not None:
            self.canvas.ensureVisible(target, 32, 32)

    def attach_power_transport(self, sender):
        """Future firmware adapter: sender receives PowerDecision responses only."""
        self.power_protection.attach_transport(sender)
        self.request_issues = ()
        self.hardware_topology_revision = None
        self.refresh_safety_status()

    def disconnect_power_transport(self):
        self.power_protection.disconnect()
        self.request_issues = ()
        self.hardware_topology_revision = None
        if self.circuit is not None:
            self.display_circuit(self.circuit, preserve_view=True, measurement_update=True)
        self.refresh_safety_status()

    def receive_hardware_topology(self, data, revision):
        """Firmware snapshots need an increasing revision within each connection."""
        if self.power_protection.transport is None:
            return False
        if type(revision) is not int or revision <= self.power_protection.highest_revision:
            self.topology_valid = False
            self.hardware_topology_revision = None
            self.safety_report = SafetyReport((SafetyIssue("stale_topology", "Board topology revision is stale or invalid."),))
            self.power_protection.update_report(self.safety_report)
            self.refresh_safety_status()
            return False
        return self.load_topology(data, hardware_revision=revision)

    def handle_enable_request(self, request_id, topology_revision):
        """Validate the latest board snapshot and reply; firmware decides whether to power it."""
        if self.circuit is not None:
            self.display_circuit(self.circuit, preserve_view=True, measurement_update=True)
        decision = self.power_protection.handle_enable_request(request_id, topology_revision)
        self.power_granted = decision.granted
        if not decision.granted and self.safety_panel is not None and not self.safety_panel.isVisible():
            self.safety_alert_key = ()
        self.refresh_safety_status(decision.issues)
        return decision

    def receive_supply_measurement(self, voltage_v, current_a):
        """Call on the UI thread with fresh upstream voltage and load current."""
        guard = self.power_protection
        if guard.transport is None:
            return False
        valid = guard.observe(voltage_v, current_a)
        if self.circuit is not None and guard.voltage_v is not None:
            self.display_circuit(self.circuit, preserve_view=True, measurement_update=True)
        self.refresh_safety_status()
        return valid

    def receive_firmware_fault(self, message):
        """Firmware reports its own latched fault, or None after it clears it."""
        self.power_protection.report_firmware_fault(message)
        self.refresh_safety_status()

    def poll_power_protection(self):
        self.refresh_safety_status()

    def closeEvent(self, event):
        self.protection_timer.stop()
        self.power_protection.disconnect()
        super().closeEvent(event)

    def mark_utility_active(self, button, active):
        button.setProperty("activeDialog", active)
        button.style().unpolish(button)
        button.style().polish(button)
        button.update()

    def show_guide(self):
        existing = getattr(self, "guide_dialog", None)
        if existing is not None:
            existing.show()
            existing.raise_()
            existing.activateWindow()
            return
        dialog = CircuitGuideDialog(self)
        self.guide_dialog = dialog
        self.mark_utility_active(self.guide_button, True)
        def closed(result):
            self.mark_utility_active(self.guide_button, False)
            self.guide_dialog = None
            dialog.deleteLater()
        dialog.finished.connect(closed)
        dialog.show()

    def show_settings(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Settings")
        dialog.setMinimumWidth(520)
        dialog.setObjectName("settingsDialog")
        dialog.setStyleSheet("""
            QDialog#settingsDialog { background: #edf4f2; }
            QFrame#settingsSection { background: #ffffff; border: none; border-radius: 12px; }
            QLabel { background: transparent; }
            QPushButton, QToolButton, QCheckBox, QComboBox { font-family: "DM Sans"; font-weight: 500; }
            QLabel#settingsHeading { font-family: "DM Sans"; font-size: 14px; font-weight: 600; color: #42447a; }
            QComboBox { background: #f7faf9; border: 1px solid #cbd7d4; border-radius: 8px; padding: 8px 28px 8px 12px; }
            QComboBox::drop-down { background: transparent; border: none; width: 24px; border-top-right-radius: 8px; border-bottom-right-radius: 8px; }
            QComboBox QAbstractItemView { background: #edf4f2; border: 1px solid #cbd7d4; border-radius: 8px; padding: 6px; outline: none; selection-background-color: #fafffe; selection-color: #222222; }
            QComboBox QAbstractItemView::item { padding: 8px; border-radius: 6px; }
            QPushButton { background: #ffffff; border: none; border-radius: 8px; padding: 8px 14px; }
            QPushButton:hover { background: #dcefeb; }
        """)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)
        def section(title):
            frame = QFrame()
            frame.setObjectName("settingsSection")
            column = QVBoxLayout(frame)
            column.setContentsMargins(16, 16, 16, 16)
            column.setSpacing(12)
            heading = QLabel(title)
            heading.setObjectName("settingsHeading")
            column.addWidget(heading)
            layout.addWidget(frame)
            return column
        colour_section = section("Highlight colours")
        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(24)
        form.setVerticalSpacing(12)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        colour_section.addLayout(form)
        draft = dict(self.highlight_colors)
        swatches = {}

        def update_swatch(role):
            button = swatches[role]
            color = QColor(draft[role])
            foreground = "#111111" if color.lightness() > 140 else "#ffffff"
            button.setText(color.name())
            button.setStyleSheet(f"background: {color.name()}; color: {foreground}; border: none; border-radius: 8px; padding: 8px 16px;")

        def choose(role):
            color = QColorDialog.getColor(QColor(draft[role]), dialog, "Choose highlight colour")
            if color.isValid():
                draft[role] = color.name()
                update_swatch(role)

        for role, title in (("component", "Selection"), ("current", "Current arrows")):
            button = QPushButton()
            button.setAccessibleName(title + " colour")
            button.clicked.connect(lambda checked=False, role=role: choose(role))
            swatches[role] = button
            update_swatch(role)
            form.addRow(title, button)
        display_section = section("Schematic display")
        display_section.addWidget(QLabel("Current display"))
        current_mode = QComboBox()
        current_mode.setAccessibleName("Current display mode")
        chevron_path = (Path(__file__).resolve().parent / "assets" / "images" / "chevron-down.svg").as_posix()
        current_mode.setStyleSheet("""
            QComboBox::drop-down { background: transparent; border: none; width: 28px; }
            QComboBox::down-arrow { image: url("CHEVRON_PATH"); width: 16px; height: 16px; }
        """.replace("CHEVRON_PATH", chevron_path))
        current_mode.view().viewport().setStyleSheet("background: transparent;")
        current_mode.view().window().setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        current_mode.view().window().setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        current_mode.addItem("Current Magnitude with Arrows in Conventional Current", "arrows")
        current_mode.addItem("Signed Current with No Arrows", "signed")
        current_mode.setCurrentIndex(current_mode.findData(self.current_display))
        display_section.addWidget(current_mode)
        grid_toggle = QCheckBox("Show schematic grid")
        checkmark_path = (Path(__file__).resolve().parent / "assets" / "images" / "checkmark.svg").as_posix()
        grid_toggle.setStyleSheet("""
            QCheckBox { background: transparent; spacing: 8px; padding: 4px 0px; }
            QCheckBox::indicator { width: 16px; height: 16px; border: 1px solid #9bada9; border-radius: 2px; background: #ffffff; }
            QCheckBox::indicator:checked { background: #dcefeb; border-color: #729b94; image: url("CHECKMARK_PATH"); }
            QCheckBox::indicator:hover { border-color: #527f85; }
        """.replace("CHECKMARK_PATH", checkmark_path))
        grid_toggle.setChecked(self.canvas.grid_visible)
        display_section.addWidget(grid_toggle)
        reset = QPushButton("Restore defaults")
        def restore():
            draft.update(DEFAULT_HIGHLIGHT_COLORS)
            current_mode.setCurrentIndex(0)
            grid_toggle.setChecked(True)
            for role in swatches:
                update_swatch(role)
        reset.clicked.connect(restore)
        footer = QHBoxLayout()
        footer.setSpacing(8)
        footer.addWidget(reset)
        footer.addStretch()
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save |
                                   QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        footer.addWidget(buttons)
        layout.addLayout(footer)
        self.mark_utility_active(self.settings_button, True)
        dialog.finished.connect(lambda result: self.mark_utility_active(self.settings_button, False))
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.canvas.grid_visible = grid_toggle.isChecked()
            self.preferences.setValue("display/grid", self.canvas.grid_visible)
            self.canvas.viewport().update()
            self.apply_current_display(current_mode.currentData(), redraw=False)
            self.apply_highlight_colors(draft)

    def apply_current_display(self, mode, redraw=True):
        if mode not in ("arrows", "signed"):
            raise ValueError("Unknown current display mode")
        self.current_display = mode
        self.preferences.setValue("display/current", mode)
        self.scene.setProperty("currentDisplay", mode)
        self.canvas.update_current_reference()
        self.component_details.current_display = mode
        if redraw and self.circuit is not None:
            displayed = replace(self.circuit_with_measured_voltage(self.circuit),
                                ground_node=self.simulation_result.ground_node)
            render_circuit(self.scene, displayed, self.rc_preview_result or self.simulation_result, self.current_safety_issues)
            self.refresh_component_details()

    def apply_highlight_colors(self, colors):
        colors = dict(colors)
        selection = colors.get("component", colors.get("node", DEFAULT_HIGHLIGHT_COLORS["node"]))
        colors["component"] = colors["node"] = selection
        self.preferences.setValue("highlights/selection", selection)
        self.highlight_colors = colors
        self.scene.setProperty("highlightColors", self.highlight_colors)
        for role, color in colors.items():
            self.preferences.setValue("highlights/" + role, color)
        if self.circuit is not None:
            displayed = replace(self.circuit_with_measured_voltage(self.circuit),
                                ground_node=self.simulation_result.ground_node)
            render_circuit(self.scene, displayed, self.rc_preview_result or self.simulation_result, self.current_safety_issues)
            self.refresh_component_details()
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
        if not QDesktopServices.openUrl(QUrl(url)):
            self.statusBar().showMessage("Could not open the browser. Use falstad.py --output to save circuit text.")

    def bundled_circuits(self):
        return [json.loads(path.read_bytes()) for path in sorted(
            (Path(__file__).resolve().parent / "examples").rglob("*.json"))]

    def show_examples(self):
        """Read-only bundled examples; browsing never seeds or writes user storage."""
        try:
            records = self.bundled_circuits()
        except (OSError, ValueError, KeyError) as error:
            QMessageBox.warning(self, "Cannot open circuit library", str(error))
            return
        self.library_page.set_records(records)
        self.navigation_buttons[2].setChecked(True)
        self.set_workspace_panels(False)
        self.content_pages.setCurrentIndex(2)
        self.export_button.setEnabled(False)

    def refresh_my_circuits(self):
        if self.database is None:
            self.database = CircuitDatabase()
        records = [self.database.load(name) for name in self.database.list_names(origin="user")]
        self.my_circuits_page.set_records(records)

    def show_my_circuits(self):
        try:
            self.refresh_my_circuits()
        except (OSError, sqlite3.Error, ValueError, KeyError) as error:
            QMessageBox.warning(self, "Cannot open My Circuits", str(error))
            return
        self.navigation_buttons[1].setChecked(True)
        self.set_workspace_panels(False)
        self.content_pages.setCurrentIndex(1)
        self.export_button.setEnabled(False)

    def open_library_circuit(self, name):
        try:
            data = next(record for record in self.bundled_circuits() if record["name"] == name)
        except (StopIteration, OSError, ValueError, KeyError) as error:
            QMessageBox.warning(self, "Cannot load example", str(error))
            return
        self.clear_component_selection()
        if self.load_topology(data):
            # An example is a clean read-only baseline, never a personal record identity.
            self.saved_record_name = None
            self.saved_document = copy.deepcopy(data)
            self.navigation_buttons[0].setChecked(True)
            self.change_workspace_page(0)

    def open_saved_circuit(self, name):
        try:
            if self.database is None or name not in self.database.list_names(origin="user"):
                raise KeyError(name)
            data = self.database.load(name)
        except (OSError, sqlite3.Error, ValueError, KeyError) as error:
            QMessageBox.warning(self, "Cannot load saved circuit", str(error))
            return
        self.clear_component_selection()
        if self.load_topology(data):
            self.navigation_buttons[0].setChecked(True)
            self.change_workspace_page(0)

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
    for filename in ("DM_Sans/DMSans-VariableFont_opsz,wght.ttf",
                     "Space_Grotesk/SpaceGrotesk-VariableFont_wght.ttf"):
        font_path = font_dir / filename
        font_id = QFontDatabase.addApplicationFont(str(font_path))
        if not QFontDatabase.applicationFontFamilies(font_id):
            raise RuntimeError(f"Could not load the application font: {font_path}")
    font = QFont("DM Sans")
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
