"""Render the STAAD workbench with illustrative offline data; never calls COM."""
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
from civtools.core.productivity_model_tools import selected_release_plan, release_plan_commands
from civtools.qt_productivity_tools import PreparedAction


def main():
    app = QApplication([])
    app.setStyle('Fusion')
    app.setStyleSheet(STYLE)
    with tempfile.TemporaryDirectory(prefix='civtools-workbench-') as folder:
        os.environ['CIVTOOLS_CONFIG_DIR'] = folder
        window = CivToolsApp()
        window.navigate('productivity')
        suite = window.pages['productivity']
        model = ModelSnapshot('Illustrative_Shed.std', 'Metric',
            {1: (0, 0, 0), 2: (0, 6, 0), 3: (10, 6, 0), 4: (10, 0, 0)},
            {101: (1, 2), 102: (2, 3), 103: (3, 4)}, [1, 4], [1, 2], primary_cases=[1])
        suite.open_feature('select').set_snapshot(model)
        utility = window.utility_windows['productivity']
        utility.resize(1140, 760)
        app.processEvents()
        destination = Path(__file__).resolve().parent
        utility.grab().save(str(destination / 'staad-workbench-select.png'))
        parameters = suite.open_feature('parameters')
        parameters.tabs.setCurrentIndex(1)
        app.processEvents()
        utility.grab().save(str(destination / 'staad-workbench-parameters.png'))
        page = suite.open_feature('releases')
        plan = selected_release_plan(model, [101, 102], 'BOTH', ('MZ',))
        page.on_success(PreparedAction(model, 'releases',
            {'plan': plan, 'end': 'BOTH', 'dofs': ('MZ',)}, release_plan_commands(plan), plan.summary))
        app.processEvents()
        utility.grab().save(str(destination / 'staad-workbench-releases.png'))
        suite.show_compact()
        app.processEvents()
        suite.compact_window.grab().save(str(destination / 'staad-compact-palette.png'))
        window.close()
        app.processEvents()


if __name__ == '__main__':
    main()
