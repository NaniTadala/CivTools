import os, sys, tempfile
os.environ['QT_QPA_PLATFORM']='offscreen'; os.environ['CIVTOOLS_CONFIG_DIR']=tempfile.mkdtemp(prefix='civtools-palette-'); sys.path.insert(0,'src')
from PySide6.QtWidgets import QApplication
from civtools.qt_app import CivToolsApp
from civtools.qt_style import STYLE
app=QApplication([]); app.setStyle('Fusion'); app.setStyleSheet(STYLE)
window=CivToolsApp(); window.navigate('productivity'); app.processEvents(); palette=window.pages['productivity']; window.utility_windows['productivity'].grab().save('artifacts/staad-tools-palette.png'); palette.open_feature('select'); app.processEvents(); palette.children_windows['select'].grab().save('artifacts/staad-select-workflow.png'); palette.open_feature('parameters'); app.processEvents(); palette.children_windows['parameters'].grab().save('artifacts/staad-design-parameters.png'); window.close(); app.processEvents()
