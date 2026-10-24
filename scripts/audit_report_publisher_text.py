"""Measure visible control text and capture publisher layouts at supported text sizes."""
import json
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))


def main():
    os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
    output=ROOT/'artifacts'/'publisher-text-audit'
    output.mkdir(exist_ok=True,parents=True)
    os.environ['CIVTOOLS_CONFIG_DIR']=str(output/'config')
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import (QApplication,QPushButton,QCheckBox,QComboBox,QLabel,QWidget,QToolButton,
        QStyle,QStyleOptionButton,QStyleOptionComboBox)
    from civtools.qt_app import CivToolsApp
    from civtools.qt_report_workspace import StatusLabel
    app=QApplication([])
    window=CivToolsApp()
    window.navigate('reports')
    page=window.pages['reports']
    page.records.clear()
    page.prepared.clear()
    page.rebuild()
    utility=window.utility_windows['reports']
    failures=[]
    def inspect(parent,state):
        app.processEvents()
        for widget in parent.findChildren(QWidget):
            if not widget.isVisible():
                continue
            text=''
            if isinstance(widget,QToolButton):
                if widget.width()<widget.sizeHint().width():
                    failures.append(dict(state=state,text=widget.text() or widget.accessibleName(),required=widget.sizeHint().width(),available=widget.width()))
                continue
            if isinstance(widget,(QPushButton,QCheckBox)):
                text=widget.text().replace('&','')
                option=QStyleOptionButton()
                widget.initStyleOption(option)
                element=QStyle.SubElement.SE_CheckBoxContents if isinstance(widget,QCheckBox) else QStyle.SubElement.SE_PushButtonContents
                available=widget.style().subElementRect(element,option,widget).width()
                if not widget.icon().isNull():
                    available-=widget.iconSize().width()+5
            elif isinstance(widget,QComboBox):
                text=widget.currentText()
                option=QStyleOptionComboBox()
                widget.initStyleOption(option)
                available=widget.style().subControlRect(QStyle.ComplexControl.CC_ComboBox,option,QStyle.SubControl.SC_ComboBoxEditField,widget).width()-3
            elif isinstance(widget,QLabel) and not isinstance(widget,StatusLabel) and not widget.wordWrap():
                text=widget.text()
                available=widget.contentsRect().width()
            else:
                continue
            required=widget.fontMetrics().horizontalAdvance(text)
            if text and required>available+1:
                failures.append(dict(state=state,text=text,required=required,available=available))
    for percent in ('100%','115%','130%'):
        window.set_text_size(percent)
        page.records={}
        page.rebuild()
        page.preview.setText('')
        for width,height in [(760,500),(1000,700)]:
            utility.resize(width,height)
            app.processEvents()
            name=f'workspace-{percent[:-1]}-{width}'
            inspect(page,name)
            utility.grab().save(str(output/(name+'.png')))
        source='Foundation calculation with a deliberately long report filename.xlsx'
        page.records={source:dict(source=source,relative=source,status='Not prepared',overrides={},included=True,
            sheets=[dict(name='Calculation summary and governing design checks',visible=True,empty=False,included=True,overrides={})])}
        page.rebuild()
        page.preview_name.setText('Calculation summary and governing design checks')
        page.feedback.setText('A deliberately long operation message that should elide gracefully and remain available in the tooltip')
        page.output.setText('C:/Project/Issued reports/A deliberately long output folder name for calculation reports')
        from PySide6.QtGui import QPixmap
        illustration=QPixmap(400,560)
        illustration.fill(Qt.GlobalColor.white)
        page.preview.setPixmap(illustration)
        page.preview_nav.show()
        utility.resize(760,500)
        inspect(page,f'preview-{percent[:-1]}')
        utility.grab().save(str(output/f'preview-{percent[:-1]}.png'))
        page.settings_dialog.show()
        for index,name in enumerate(('layout','export','advanced')):
            page.editor.setCurrentIndex(index)
            state=f'{name}-{percent[:-1]}'
            inspect(page.settings_dialog,state)
            page.settings_dialog.grab().save(str(output/(state+'.png')))
        page.settings_dialog.hide()
    (output/'text-fit.json').write_text(json.dumps(failures,indent=2),encoding='utf-8')
    print(json.dumps(failures,indent=2))
    window.close()
    return bool(failures)


if __name__=='__main__':
    raise SystemExit(main())
