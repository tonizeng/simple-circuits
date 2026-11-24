"""Save naming, copy/update choice and retry UI; storage is injected."""
import copy
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QLineEdit, QDialogButtonBox

class SaveCircuitDialog(QDialog):
    def __init__(self, document, existing_name, names, writer, parent=None):
        super().__init__(parent)
        self.document = copy.deepcopy(document)
        self.existing_name = existing_name
        self.names = set(names)
        self.writer = writer
        self.saved_data = None
        self.setWindowTitle('Save As')
        self.setObjectName('saveCircuitDialog')
        self.setWindowModality(Qt.WindowModality.WindowModal)
        self.setMinimumWidth(480)
        self.setStyleSheet("QDialog#saveCircuitDialog { background: #fafcfb; } QLabel { background: transparent; } QLineEdit, QComboBox { background: white; border: 1px solid #d7e3df; border-radius: 8px; padding: 8px; } QPushButton { background: #e7e3f3; border: none; border-radius: 8px; padding: 8px 16px; min-height: 24px; min-width: 90px; }")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20,20,20,20)
        layout.setSpacing(12)
        self.hint = QLabel('Saves a separate circuit in My Circuits. The original stays unchanged.' if not existing_name else 'Save changes to the current personal circuit.')
        self.hint.setWordWrap(True)
        self.hint.setStyleSheet("font-family: 'DM Sans'; color: #000000; font-size: 14px; background: transparent;")
        layout.addWidget(self.hint)
        layout.addWidget(QLabel('Circuit name'))
        self.name_field = QLineEdit()
        self.name_field.setObjectName('saveCircuitName')
        self.name_field.setAccessibleName('Circuit name')
        layout.addWidget(self.name_field)
        self.error = QLabel()
        self.error.setObjectName('saveCircuitError')
        self.error.setStyleSheet('color: #b53e2b; background: transparent;')
        self.error.setWordWrap(True)
        self.error.hide()
        layout.addWidget(self.error)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        self.primary_button = self.buttons.button(QDialogButtonBox.StandardButton.Save)
        self.primary_button.clicked.connect(self.save)
        self.buttons.rejected.connect(self.reject)
        for button in self.buttons.buttons():
            button.setAutoDefault(False)
        self.name_field.returnPressed.connect(self.primary_button.click)
        layout.addWidget(self.buttons)
        name = self.document.get('name','').strip() or 'Untitled'
        if not existing_name and name in self.names:
            name = self.copy_name(name)
        self.name_field.textChanged.connect(self.validate_name)
        self.name_field.setText(name)
        self.validate_name()

    def validate_name(self, text=None):
        name = self.name_field.text().strip()
        if not name:
            message = 'Enter a circuit name.'
        elif any(ord(char) < 32 for char in name):
            message = 'Circuit names cannot contain line breaks or control characters.'
        elif name in self.names and name != self.existing_name:
            message = 'That name already exists. Choose another name.'
        else:
            message = ''
        self.error.setText(message)
        self.error.setVisible(bool(message))
        self.primary_button.setEnabled(not message)
        self.primary_button.setText('Save')
        return not message

    def copy_name(self, name):
        base = name + ' (copy)'
        candidate, number = base, 2
        while candidate in self.names:
            candidate = f'{base} {number}'
            number += 1
        return candidate

    def save(self):
        if not self.validate_name():
            return
        updating = self.existing_name is not None
        name = self.name_field.text().strip()
        data = copy.deepcopy(self.document)
        data['name'] = name
        try:
            self.writer(data, self.existing_name if updating else None, not updating)
        except (OSError, ValueError, RuntimeError) as error:
            if isinstance(error, ValueError) and 'already exists' in str(error):
                self.names.add(name)
                self.validate_name()
                return
            self.error.setText(str(error))
            self.error.show()
            self.primary_button.setText('Retry Save')
            return
        self.saved_data = data
        self.accept()
