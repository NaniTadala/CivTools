"""Render the floating suite offline without connecting to STAAD."""
import os
from pathlib import Path
import sys
import tempfile
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from PySide6.QtWidgets import QApplication
from civtools.qt_app import CivToolsApp
from civtools.qt_style import STYLE
from civtools.core.staad_productivity import ModelSnapshot
app = QApplication([])
app.setStyle('Fusion')
app.setStyleSheet(STYLE)
with tempfile.TemporaryDirectory() as folder:
    os.environ['CIVTOOLS_CONFIG_DIR'] = folder
    window = CivToolsApp()
    window.navigate('productivity')
    suite = window.pages['productivity']
    host = window.utility_windows['productivity']
    model = ModelSnapshot('Example_Shed.std', 'Metric',
        {1: (0, 0, 0), 2: (0, 6, 0), 3: (10, 6, 0), 4: (10, 0, 0)},
        {101: (1, 2), 102: (2, 3), 103: (3, 4)}, [1, 4], [1, 2], primary_cases=[1])
    suite.open_feature('select').set_snapshot(model)
    for key in ('select', 'renumber', 'groups', 'releases', 'parameters', 'rack', 'pebA', 'tables', 'combinations', 'girders'):
        page = suite.open_feature(key)
        app.processEvents()
        print(key, host.width(), host.height(), host.minimumSizeHint().width())
        host.grab().save(str(Path(__file__).parent / ('floating-' + key + '.png')))
    window.close()
    app.processEvents()
