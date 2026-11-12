"""Draggable validation cards contained within the schematic viewport."""
from html import escape
import re

from PySide6.QtCore import Qt, QEvent, QPoint
from PySide6.QtWidgets import (QVBoxLayout, QFrame, QLabel)


class DragHandle(QLabel):
    def __init__(self, text, panel, parent):
        super().__init__(text, parent)
        self.panel = panel

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            panel = self.panel
            panel.drag_offset = event.globalPosition().toPoint() - panel.mapToGlobal(QPoint())
            panel.raise_()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        panel = self.panel
        if panel.drag_offset is not None:
            position = panel.parentWidget().mapFromGlobal(event.globalPosition().toPoint() - panel.drag_offset)
            panel.user_positioned = True
            panel.move_within_parent(position)
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.panel.drag_offset = None
            event.accept()
        else:
            super().mouseReleaseEvent(event)


class SafetyAlertsPanel(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("safetyAlertsPanel")
        self.setStyleSheet("QFrame#safetyAlertsPanel { background: transparent; border: none; }")
        self.resize(320, 300)
        self.drag_offset = None
        self.user_positioned = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.handle = None
        if parent is not None:
            parent.installEventFilter(self)
        self.cards = layout
        self.cards.setSpacing(18)

    def reset_position(self):
        self.user_positioned = False
        self.fit_within_parent()

    def move_within_parent(self, position):
        parent = self.parentWidget()
        if parent is not None:
            vertical_space = parent.height() - self.height()
            self.move(max(0, min(position.x(), parent.width() - self.width())),
                      max(min(0, vertical_space), min(position.y(), max(0, vertical_space))))

    def fit_within_parent(self):
        parent = self.parentWidget()
        width = min(320, max(1, parent.width() - 16)) if parent is not None else 320
        height = self.cards.totalHeightForWidth(width)
        if height < 0:
            height = self.cards.sizeHint().height()
        self.resize(width, max(1, height + 2))
        if parent is not None:
            position = self.pos() if self.user_positioned else QPoint(8, 8)
            self.move_within_parent(position)

    def eventFilter(self, watched, event):
        if watched is self.parentWidget() and event.type() == QEvent.Type.Resize:
            self.fit_within_parent()
        return super().eventFilter(watched, event)

    def showEvent(self, event):
        super().showEvent(event)
        self.fit_within_parent()
        self.raise_()

    def set_issues(self, issues, checks_passed=False):
        while self.cards.count():
            item = self.cards.takeAt(0)
            if item.widget() is not None:
                item.widget().hide()
                item.widget().deleteLater()
        self.issues = tuple(issues)
        self.user_positioned = False
        self.handle = None
        if not issues and not checks_passed:
            self.hide()
            return
        for severity, title, colour in (("error", "Error!", "#c94b00"),
                                        ("warning", "Warning!", "#d2ac20"),
                                        ("passed", "Circuit checks passed", "#51843c")):
            related = [i for i in issues if i.severity == severity]
            messages = list(dict.fromkeys(i.message for i in related))
            if severity == "passed":
                if not checks_passed:
                    continue
                content = "Power has been granted to circuit."
            elif messages:
                rows = []
                for message in messages:
                    # Only identifier prefixes become locations, not explanatory colons.
                    match = re.match(r"^([A-Za-z][A-Za-z0-9_]*):\s*(.*)$", message, re.DOTALL)
                    if match:
                        message = f"At {match[1]}, {match[2]}"
                    identifiers = {cid for issue in related for cid in issue.component_ids}
                    identifiers.update(ref for ref in re.findall(r"\bn[A-Za-z0-9_]*\b", message)
                                       if ref == "n" or ref.startswith("n_") or any(c.isdigit() for c in ref))
                    if match:
                        identifiers.add(match[1])
                    pattern = r"\b(" + "|".join(re.escape(i) for i in sorted(identifiers, key=len, reverse=True)) + r")\b"
                    parts = re.split(pattern, message) if identifiers else [message]
                    formatted = "".join(f"<b>{escape(part)}</b>" if part in identifiers else escape(part)
                                        for part in parts)
                    rows.append(f'<tr><td valign="top">•&nbsp;&nbsp;</td><td style="padding-bottom: 8px;">{formatted}</td></tr>')
                content = ('Power has not been granted.<br>'
                           '<table border="0" cellspacing="0" cellpadding="0">'
                           + "".join(rows) + '</table>')
            else:
                continue
            card = QFrame()
            card.setObjectName("safetyCard")
            card.setStyleSheet("QFrame#safetyCard { background: #e9e9e9; border: 1px solid #a8a8a8; }")
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(0, 0, 0, 0)
            card_layout.setSpacing(0)
            header = DragHandle(title, self, card)
            header.setCursor(Qt.CursorShape.SizeAllCursor)
            header.setToolTip("Drag to move")
            if self.handle is None:
                self.handle = header
            header.setAlignment(Qt.AlignmentFlag.AlignCenter)
            header.setStyleSheet(f"background: {colour}; color: white; font-size: 14px; font-weight: bold; padding: 12px;")
            card_layout.addWidget(header)
            body = QLabel(content)
            body.setTextFormat(Qt.TextFormat.RichText)
            body.setWordWrap(True)
            body.setContentsMargins(16, 16, 16, 20)
            body.setStyleSheet("background: transparent; color: #111111; font-size: 14px;")
            card_layout.addWidget(body)
            self.cards.addWidget(card)
            card.show()
        self.cards.invalidate()
        self.fit_within_parent()
