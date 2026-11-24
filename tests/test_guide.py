import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import unittest
from pathlib import Path
from PySide6.QtWidgets import QApplication, QLabel
from main import CircuitWindow

class GuideTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_guide_is_non_modal_reused_and_preserves_current_circuit(self):
        window = CircuitWindow()
        window.show()
        window.load_topology((Path(__file__).resolve().parents[1] / "examples/01_led_series.json").read_bytes())
        original = window.circuit
        window.select_component_details("R1")
        window.guide_button.click()
        guide = window.guide_dialog
        self.assertFalse(guide.isModal())
        self.assertEqual(guide.section_list.item(0).text(), "Getting Started")
        self.assertEqual(guide.section_list.item(1).text(), "Understanding the Circuit")
        self.assertEqual(guide.section_list.item(2).text(), "Navigation")
        self.assertEqual(guide.section_list.item(3).text(), "Terminology")
        text = "\n".join(label.text() for label in guide.findChildren(QLabel))
        for phrase in ("Voltage and Polarity", "Current Direction", "Ground Reference", "Unavailable Values", "Nominal", "Calculated", "Measured", "Open Circuit", "Short Circuit"):
            self.assertIn(phrase, text)
        window.guide_button.click()
        self.assertIs(window.guide_dialog, guide)
        window.change_workspace_page(1)
        self.assertTrue(window.guide_button.isEnabled())
        self.assertEqual(window.circuit, original)
        guide.close()
        self.assertIsNone(window.guide_dialog)
        window.close()
        window.deleteLater()
        self.app.processEvents()

    def test_formula_page_and_bottom_navigation(self):
        from guide_ui import CircuitGuideDialog
        from PySide6.QtSvgWidgets import QSvgWidget
        guide=CircuitGuideDialog()
        guide.show();self.app.processEvents()
        self.assertEqual(guide.width(),820)
        self.assertEqual(guide.section_list.count(),5)
        self.assertEqual(guide.section_list.width(),216)
        self.assertEqual(guide.section_list.item(4).text(),'Formulas')
        self.assertFalse(guide.previous_page.isEnabled())
        for expected in range(1,guide.pages.count()):
            guide.next_page.click()
            self.assertEqual(guide.pages.currentIndex(),expected)
        self.assertFalse(guide.next_page.isEnabled())
        self.assertTrue(guide.previous_page.isEnabled())
        equations=guide.pages.widget(4).findChildren(QSvgWidget)
        self.assertGreater(len(equations),10)
        self.assertTrue(all(e.renderer().isValid() for e in equations))
        text=' '.join(label.text() for label in guide.pages.widget(4).findChildren(QLabel))
        for phrase in ('Nodal Analysis','Resistors and Photoresistors','LED or Diode','Capacitor','Inductor'):
            self.assertIn(phrase,text)
        self.assertNotIn('Wires',text)
        self.assertNotIn('Fixed-drop junction',text)
        self.assertEqual(guide.section_list.currentRow(),4)
        guide.section_list.setCurrentRow(0)
        self.assertEqual(guide.pages.currentIndex(),0)
        self.assertFalse(guide.previous_page.isEnabled())
        guide.section_list.setCurrentRow(4)
        guide.previous_page.click()
        self.assertEqual(guide.pages.currentIndex(),3)
        guide.close();guide.deleteLater();self.app.processEvents()

    def test_component_link_opens_relevant_formula_section(self):
        from PySide6.QtWidgets import QPushButton
        window=CircuitWindow()
        window.show()
        window.load_topology((Path(__file__).resolve().parents[1]/'examples/01_led_series.json').read_bytes())
        original=window.circuit
        window.select_component_details('R1')
        link=window.component_details.scroll.widget().findChild(QPushButton,'solvingGuideLink')
        self.assertIsNotNone(link)
        link.click();self.app.processEvents()
        guide=window.guide_dialog
        self.assertEqual(guide.section_list.currentRow(),4)
        self.assertGreater(guide.formulas_scroll.verticalScrollBar().value(),0)
        self.assertEqual(window.circuit,original)
        window.select_component_details('LED1')
        window.component_details.scroll.widget().findChild(QPushButton,'solvingGuideLink').click()
        self.app.processEvents()
        self.assertIs(window.guide_dialog,guide)
        self.assertEqual(guide.section_list.currentRow(),4)
        self.assertEqual(window.circuit,original)
        guide.close();window.close();window.deleteLater();self.app.processEvents()
