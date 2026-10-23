"""Compare widget snapshots with real Windows window captures for parameter backgrounds."""
import argparse
import os
from pathlib import Path
import sys
import tempfile
parser=argparse.ArgumentParser()
parser.add_argument('--style', default='Fusion')
args=parser.parse_args()
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from PySide6.QtCore import QTimer,Qt,QPoint
from PySide6.QtGui import QPalette,QColor,QFont
from PySide6.QtWidgets import QApplication,QStyleFactory
from civtools.qt_app import CivToolsApp
from civtools.qt_style import STYLE
app=QApplication([])
print('Styles:',QStyleFactory.keys(),flush=True)
app.setStyle(args.style)
app.setFont(QFont('Poppins',10))
app.setStyleSheet(STYLE)
dark=QPalette(app.palette())
for group in (QPalette.ColorGroup.Active,QPalette.ColorGroup.Inactive,QPalette.ColorGroup.Disabled):
 for role in (QPalette.ColorRole.Window,QPalette.ColorRole.Base,QPalette.ColorRole.Button):
  dark.setColor(group,role,QColor('#202020'))
app.setPalette(dark)
folder=tempfile.TemporaryDirectory()
os.environ['CIVTOOLS_CONFIG_DIR']=folder.name
window=CivToolsApp()
window.show()
window.navigate('productivity')
suite=window.pages['productivity']
host=window.utility_windows['productivity']
suite.favourites=['select','groups','releases','parameters']
for key,action in suite.buttons.items():action.setVisible(key in suite.favourites)
page=suite.open_feature('parameters')
host.pin.setChecked(True)
host.show();host.raise_();host.activateWindow()
output=Path(__file__).parent/'background-probe'
output.mkdir(exist_ok=True)
def capture(name):
 app.processEvents()
 widget=host.grab()
 screen=host.screen().grabWindow(int(host.winId()))
 widget.save(str(output/(args.style+'-'+name+'-widget.png')))
 screen.save(str(output/(args.style+'-'+name+'-screen.png')))
 point=page.form.mapTo(host,QPoint(1,1))
 ratio=screen.devicePixelRatio()
 pixel=screen.toImage().pixelColor(round(point.x()*ratio),round(point.y()*ratio)).name() if not screen.isNull() else 'no capture'
 print(name,'form window:',page.form.palette().color(QPalette.ColorRole.Window).name(),'autoFill:',page.form.autoFillBackground(),'styled:',page.form.testAttribute(Qt.WidgetAttribute.WA_StyledBackground),'screen background:',pixel,flush=True)
def first():
 capture('initial')
 app.setPalette(dark)
 host.pin.setChecked(False)
 host.pin.setChecked(True)
 QTimer.singleShot(300,second)
def second():
 capture('after-theme-and-pin')
 window.close()
 app.quit()
QTimer.singleShot(500,first)
app.exec()
folder.cleanup()
