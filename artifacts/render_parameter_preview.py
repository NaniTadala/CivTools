"""Exercise completed command preview with a long model path, without STAAD."""
import os
from pathlib import Path
import sys
import tempfile
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from PySide6.QtWidgets import QApplication
from civtools.qt_app import CivToolsApp
from civtools.qt_style import STYLE
from civtools.jobs import GeneratedParameterCommands

app = QApplication([])
app.setStyle('Fusion')
app.setStyleSheet(STYLE)
with tempfile.TemporaryDirectory() as folder:
    os.environ['CIVTOOLS_CONFIG_DIR'] = folder
    window = CivToolsApp()
    window.navigate('productivity')
    suite = window.pages['productivity']
    page = suite.open_feature('parameters')
    host = window.utility_windows['productivity']
    path = r'C:\Users\asus\Downloads\RHCD-PP-L5Z-027_Rev-0\Reference STAAD\410-PR-01 Stretch- F.STD'
    commands = 'START CONCRETE DESIGN\nCODE INDIAN\n' + ''.join(
        f'FC 30 MEMB {i} TO {i+19}\nFYMAIN 500 MEMB {i} TO {i+19}\n' for i in range(1, 2400, 20)) + 'END CONCRETE DESIGN\n'
    page.on_event('target', path)
    page.on_success(GeneratedParameterCommands('concrete', commands, path, 2417, 0))
    for width, height in ((420, 480), (520, 600), (360, 480)):
        host.resize(width, height)
        app.processEvents()
        app.processEvents()
        assert page.output.height() >= 110, page.output.size()
        assert not page.target.isVisible()
        assert page.output.toPlainText() == commands
        assert page.feedback.text() == 'Commands ready'
        host.grab().save(str(Path(__file__).parent / f'parameter-preview-{width}-{os.environ.get("QT_SCALE_FACTOR", "1")}.png'))
        print(width, 'preview:', page.output.width(), page.output.height())
    window.close()
