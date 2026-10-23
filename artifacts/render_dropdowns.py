"""Check popup surfaces with a dark system palette, without connecting to CAD."""
import os
from pathlib import Path
import sys
import tempfile
if '--native' not in sys.argv:
    os.environ['QT_QPA_PLATFORM'] = 'offscreen'
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from PySide6.QtGui import QPalette, QColor
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from civtools.qt_app import CivToolsApp
from civtools.qt_style import STYLE
from civtools.qt_widgets import ComboBox
app = QApplication([])
app.setStyle('Fusion')
dark = QPalette()
for role in (QPalette.ColorRole.Window, QPalette.ColorRole.Base, QPalette.ColorRole.Button):
    dark.setColor(role, QColor('#202020'))
app.setPalette(dark)
app.setStyleSheet(STYLE)
with tempfile.TemporaryDirectory() as folder:
    os.environ['CIVTOOLS_CONFIG_DIR'] = folder
    window = CivToolsApp()
    window.show()
    window.navigate('productivity')
    suite = window.pages['productivity']
    page = suite.open_feature('releases')
    app.processEvents()
    fields = page.findChildren(ComboBox)
    support = next(field for field in fields if field.findText('BOTH') >= 0)
    native = '--native' in sys.argv
    for name, field in [('release-end', support), ('tool-picker', suite.tool_picker)]:
        field.showPopup()
        QTest.qWait(250)
        popup = field.view().window()
        assert popup.palette().color(QPalette.ColorRole.Window).name() == '#ffffff'
        shot = popup.screen().grabWindow(int(popup.winId())) if native else popup.grab()
        filename = f'dropdown-{name}-' + ('native' if native else 'offscreen') + '.png'
        shot.save(str(Path(__file__).parent / filename))
        print(name, popup.size(), filename)
        field.hidePopup()
    support.setCurrentIndex(0)
    support.showPopup()
    QTest.keyClick(support.view(), Qt.Key.Key_Down)
    QTest.keyClick(support.view(), Qt.Key.Key_Return)
    assert support.currentText() == 'START', support.currentText()
    assert window.windowTitle() == 'CivTools | Toolkit'
    window.grab().save(str(Path(__file__).parent / 'launcher-title-fixed.png'))
    window.close()
