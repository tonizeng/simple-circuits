"""Draggable validation cards contained within the schematic viewport."""
from component_details import DisclosureButton
from html import escape
import re

from PySide6.QtCore import Qt, QEvent, QPoint, Signal, QSize
from PySide6.QtWidgets import (QVBoxLayout, QHBoxLayout, QFrame, QLabel, QSizePolicy, QPushButton)


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


class IssueRow(QPushButton):
    def sizeHint(self):
        return self.layout().sizeHint() if self.layout() else super().sizeHint()

    def minimumSizeHint(self):
        return QSize(0, self.sizeHint().height())

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self.layout().totalHeightForWidth(width)


class IssueDisclosure(DisclosureButton):
    """Wrap long issue titles without squeezing the chevron or message."""
    def sizeHint(self):
        return self.layout().sizeHint()

    def minimumSizeHint(self):
        return QSize(0, self.fontMetrics().height())

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self.layout().totalHeightForWidth(width)


class SafetyAlertsPanel(QFrame):
    issue_selected = Signal(object)

    def __init__(self, parent=None, embedded=False):
        super().__init__(parent)
        self.embedded = embedded
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setObjectName("safetyAlertsPanel")
        self.setStyleSheet("QFrame#safetyAlertsPanel { background: transparent; border: none; }")
        self.resize(320, 300)
        self.drag_offset = None
        self.user_positioned = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.handle = None
        if parent is not None and not embedded:
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

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.embedded and hasattr(self, "cards"):
            self.fit_within_parent()

    def fit_within_parent(self):
        if self.embedded:
            height = self.cards.totalHeightForWidth(max(1, self.width()))
            if height < 0:
                height = self.cards.sizeHint().height()
            self.setFixedHeight(max(1, height + 2))
            return
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

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.embedded:
            self.fit_within_parent()

    def showEvent(self, event):
        super().showEvent(event)
        self.fit_within_parent()
        self.raise_()

    def set_compact_status(self, issues, checks_passed, power_approved=None, approval_reason=None):
        while self.cards.count():
            item = self.cards.takeAt(0)
            if item.widget() is not None:
                item.widget().hide()
                item.widget().deleteLater()
        self.issues = tuple(issues)
        self.cards.setSpacing(12)
        availability_codes = {"unknown_current", "unresolved_circuit"}
        specific_issues = [issue for issue in issues if issue.code not in availability_codes]
        unavailable = bool(issues)
        errors = sum(i.severity == "error" for i in specific_issues)
        warnings = sum(i.severity == "warning" for i in specific_issues)
        if errors:
            headline, colour, icon = "Errors Detected ⊗", "#b53e2b", "!"
        elif warnings:
            headline, colour, icon = "Review Required ⚠", "#947119", "⚠"
        elif issues:
            headline, colour, icon = "Checks Incomplete", "#666666", "○"
        elif checks_passed:
            headline, colour, icon = "Checks Passed ✓", "#51843c", "✓"
        else:
            headline, colour, icon = "Waiting for Circuit Upload", "#666666", "○"
        self.handle = QLabel(headline)
        self.handle.setStyleSheet(f"font-family: 'DM Sans'; background: transparent; color: {colour}; font-size: 14px; font-weight: 600;")
        summary = QFrame()
        summary.setObjectName("checksPowerSummary")
        summary.setStyleSheet("QFrame#checksPowerSummary { background: #ffffff; border: none; border-radius: 10px; }")
        summary_layout = QVBoxLayout(summary)
        summary_layout.setContentsMargins(12, 12, 12, 12)
        summary_layout.setSpacing(3)
        headline_row = QHBoxLayout()
        headline_row.setSpacing(6)
        self.handle.setWordWrap(True)
        headline_row.setContentsMargins(0, 0, 0, 0)
        headline_row.addWidget(self.handle, 1)
        summary_layout.addLayout(headline_row)
        if issues or checks_passed or power_approved is False:
            approved = checks_passed and not issues if power_approved is None else power_approved
            approval = QLabel("Power approved" if approved else "Power not approved")
            approval.setStyleSheet("font-family: 'DM Sans'; background: transparent; color: #596763; font-size: 14px; font-weight: 400;")
            approval.setWordWrap(True)
            approval.setContentsMargins(0, 0, 0, 0)
            summary_layout.addWidget(approval)
            if approval_reason:
                reason = QLabel(approval_reason)
                reason.setWordWrap(True)
                reason.setStyleSheet("background: transparent; color: #596763; font-size: 12px;")
                summary_layout.addWidget(reason)
        if specific_issues:
            count_parts = []
            count_labels = []
            if errors:
                label = f"{errors} error{'s' if errors != 1 else ''}"
                count_parts.append(f'<span style="color: #b53e2b;">{label}</span>')
                count_labels.append(label)
            if warnings:
                label = f"{warnings} warning{'s' if warnings != 1 else ''}"
                count_parts.append(f'<span style="color: #947119;">{label}</span>')
                count_labels.append(label)
            counts = QLabel(" &nbsp;&nbsp; ".join(count_parts))
            counts.setAccessibleName(", ".join(count_labels))
            counts.setWordWrap(True)
            counts.setStyleSheet("background: transparent; color: #606060; font-family: 'DM Sans'; font-size: 13px;")
            counts.setContentsMargins(0, 0, 0, 0)
            summary_layout.addWidget(counts)
        self.cards.addWidget(summary)
        titles = {
            "supply_short": "Supply short", "overvoltage": "Supply voltage too high",
            "predicted_overcurrent": "Current limit exceeded", "unconnected_terminal": "Disconnected terminal",
            "source_count": "Check voltage source", "unresolved_circuit": "Values unavailable",
            "unknown_current": "Supply current unavailable", "component_rating_exceeded": "Component rating exceeded",
            "invalid_rating": "Invalid component rating", "unknown_rating_check": "Component rating unchecked",
            "stale_telemetry": "Measurements out of date", "missing_telemetry": "Measurements needed",
            "topology_mismatch": "Circuit changed", "stale_topology": "Circuit data out of date",
            "firmware_fault": "Board fault", "invalid_topology": "Invalid circuit data",
        }
        titles = {code: title.title() for code, title in titles.items()}
        if not hasattr(self, "issue_expanded"):
            self.issue_expanded = {}
        ordered = sorted(specific_issues, key=lambda issue: issue.severity != "error")
        for issue in ordered:
            background = "#fff0ed" if issue.severity == "error" else "#fff8df"
            hover_background = "#ffe5df" if issue.severity == "error" else "#fff0bd"
            colour = "#b53e2b" if issue.severity == "error" else "#947119"
            row = IssueRow()
            row.setObjectName("issueRow")
            row.setProperty("issueCode", issue.code)
            row.setAccessibleName(titles.get(issue.code, "Circuit check") + ": " + issue.message)
            row.setCursor(Qt.CursorShape.PointingHandCursor)
            row.setStyleSheet(f"QPushButton#issueRow {{ text-align: left; background: {background}; border: none; border-left: 3px solid {colour}; border-radius: 8px; padding: 0px; }} QPushButton#issueRow:hover {{ background: {hover_background}; }} QPushButton#issueRow:focus {{ border: none; border-left: 3px solid {colour}; }}")
            policy = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            policy.setHeightForWidth(True)
            row.setSizePolicy(policy)
            row_layout = QVBoxLayout(row)
            row_layout.setContentsMargins(10, 8, 8, 8)
            row_layout.setSpacing(4)
            title = IssueDisclosure()
            title_layout = QVBoxLayout(title)
            title_layout.setContentsMargins(0, 0, 24, 0)
            title_label = QLabel(titles.get(issue.code, "Circuit check"))
            title_label.setWordWrap(True)
            title_label.setMinimumWidth(0)
            title_label.setStyleSheet("background: transparent; color: #222222; font-size: 14px; font-weight: 500;")
            title_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            title_layout.addWidget(title_label)
            title_policy = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            title_policy.setHeightForWidth(True)
            title.setSizePolicy(title_policy)
            title.setAccessibleName("Expand " + titles.get(issue.code, "Circuit check"))
            title.setStyleSheet("QPushButton { background: transparent; color: #222222; font-size: 14px; font-weight: 500; text-align: left; border: none; padding: 0px; }")
            key = (issue.code, issue.message)
            title.setChecked(self.issue_expanded.get(key, True))
            row_layout.addWidget(title)
            message = issue.message
            prefix = re.match(r"^([A-Za-z][A-Za-z0-9_]*):\s*(.*)$", message, re.DOTALL)
            message = f"At {prefix[1]}, {prefix[2]}" if prefix else message
            formatted = escape(message)
            if prefix:
                formatted = formatted.replace(escape(prefix[1]), "<b>" + escape(prefix[1]) + "</b>", 1)
            body = QLabel(formatted)
            body.setTextFormat(Qt.TextFormat.RichText)
            body.setWordWrap(True)
            body.setStyleSheet("background: transparent; color: #555555; font-size: 13px;")
            body.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            row_layout.addWidget(body)
            body.setVisible(title.isChecked())
            def expand_issue(expanded, label=body, issue_key=key, issue_row=row):
                self.issue_expanded[issue_key] = expanded
                label.setVisible(expanded)
                issue_row.updateGeometry()
                self.cards.invalidate()
                self.fit_within_parent()
            title.toggled.connect(expand_issue)
            row.clicked.connect(lambda checked=False, selected=issue: self.issue_selected.emit(selected))
            self.cards.addWidget(row)
            row.show()
        summary.show()
        self.cards.invalidate()
        self.fit_within_parent()
        self.show()

    def set_issues(self, issues, checks_passed=False, power_approved=None, approval_reason=None):
        if self.embedded:
            self.set_compact_status(issues, checks_passed, power_approved, approval_reason)
            return
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
            header = QLabel(title, card) if self.embedded else DragHandle(title, self, card)
            if not self.embedded:
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
