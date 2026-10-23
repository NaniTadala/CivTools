"""Render grouped PEB section states without CAD access or user settings."""
import argparse
import os
from pathlib import Path
import sys
import tempfile
parser=argparse.ArgumentParser()
parser.add_argument('--native',action='store_true')
args=parser.parse_args()
if not args.native:os.environ['QT_QPA_PLATFORM']='offscreen'
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from PySide6.QtCore import Qt,QTimer,QPoint
from PySide6.QtGui import QColor,QPalette,QFont
from PySide6.QtWidgets import QApplication,QPushButton
from civtools.qt_app import CivToolsApp
from civtools.qt_style import STYLE
app=QApplication([])
app.setStyle('Fusion');app.setFont(QFont('Poppins',10));app.setStyleSheet(STYLE)
dark=QPalette(app.palette())
for role in (QPalette.ColorRole.Window,QPalette.ColorRole.Base,QPalette.ColorRole.Button):dark.setColor(role,QColor('#202020'))
app.setPalette(dark)
folder=tempfile.TemporaryDirectory()
os.environ['CIVTOOLS_CONFIG_DIR']=folder.name
window=CivToolsApp();window.show();window.navigate('productivity')
suite=window.pages['productivity'];host=window.utility_windows['productivity']
output=Path(__file__).parent/'peb-family'/ (('native-' if args.native else '')+os.environ.get('QT_SCALE_FACTOR','1'))
output.mkdir(parents=True,exist_ok=True)
issues=[]
def capture(name,widget=host):
 app.processEvents()
 shot=widget.screen().grabWindow(int(widget.winId())) if args.native else widget.grab()
 shot.save(str(output/(name+'.png')))
 for field in widget.findChildren(QPushButton):
  if field.isVisibleTo(widget) and field.width()<field.fontMetrics().horizontalAdvance(field.text())+14:
   issues.append((name,field.text(),'caption too narrow'))
for variant in 'ABCD':
 suite.open_feature('peb'+variant)
 capture('frame-'+variant)
 page=suite.children_windows['peb'+variant].page
 page.content_scroll.verticalScrollBar().setValue(page.content_scroll.verticalScrollBar().maximum())
 capture('frame-'+variant+'-bottom')
 page.content_scroll.verticalScrollBar().setValue(0)
page=suite.open_feature('pebC')
page.geometry_preview_toggle.setChecked(True)
app.processEvents()
capture('geometry-preview')
page.geometry_preview_toggle.setChecked(False)
suite.tool_picker.showPopup();capture('tool-picker',suite.tool_picker.view().window());suite.tool_picker.hidePopup()
suite.toggle_expanded();capture('expanded');suite.show_compact()
host.resize(360,480);capture('minimum-width');host.resize(420,480)
suite.open_feature('select');capture('other-tool')
# Let the native compositor finish drawing before saving its final window capture.
def native_capture():
 suite.open_feature('pebC');host.pin.setChecked(True);host.show();host.raise_();host.activateWindow()
 QTimer.singleShot(300,finish)
def finish():
 if not args.native:suite.open_feature('pebC')
 capture('pinned-native' if args.native else 'grouped-section')
 window.close();app.quit()
if args.native:QTimer.singleShot(100,native_capture)
else:QTimer.singleShot(0,finish)
app.exec();folder.cleanup()
print(str(output),'issues:',issues)
raise SystemExit(1 if issues else 0)
