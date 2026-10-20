"""Original vector symbols for the compact STAAD tools palette."""
from functools import lru_cache
from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QPixmap, QPainter, QPen, QColor, QFont, QIcon


@lru_cache(maxsize=20)
def link_icon(key):
    pixmap = QPixmap(160, 84)
    pixmap.setDevicePixelRatio(2)
    pixmap.fill(Qt.GlobalColor.transparent)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QPen(QColor('#327B68'), 1.5))
    p.setBrush(Qt.BrushStyle.NoBrush)
    def line(a, b):
        p.drawLine(QPointF(*a), QPointF(*b))
    if key.startswith('peb') or key in ('rack', 'select'):
        variant = key[-1] if key.startswith('peb') else None
        for offset in ((11, -7), (0, 0)):
            dx, dy = offset
            pts = [(12+dx, 36+dy), (12+dx, 17+dy)]
            if variant != 'D':
                pts += [(36+dx, 7+dy)] if variant else [(36+dx, 17+dy)]
            pts += [(60+dx, 17+dy), (60+dx, 36+dy)]
            for a, b in zip(pts, pts[1:]):
                line(a, b)
            if variant == 'B':
                line((36+dx, 7+dy), (36+dx, 36+dy))
            if variant == 'C':
                for x in (24, 48):
                    line((x+dx, 12+dy), (x+dx, 36+dy))
        for x, y in ((12, 17), (36, 7 if variant and variant != 'D' else 17), (60, 17)):
            line((x, y), (x+11, y-7))
        if key == 'rack':
            line((12, 27), (60, 27))
            for x in (23, 35, 47):
                p.drawEllipse(QPointF(x, 14), 3, 3)
    elif key == 'renumber':
        p.setFont(QFont('Poppins', 11, QFont.Weight.DemiBold))
        p.drawText(QRectF(0, 3, 80, 35), Qt.AlignmentFlag.AlignCenter, '5,9 > 1,2')
    elif key == 'groups':
        p.drawRoundedRect(QRectF(9, 6, 27, 29), 3, 3)
        p.drawRoundedRect(QRectF(43, 6, 27, 29), 3, 3)
        for x,y in ((16,15),(27,12),(23,27),(14,29)):
            p.drawEllipse(QPointF(x,y), 1.6, 1.6)
        for x in (48,55,62):
            line((x,28),(x+4,13))
    elif key in ('releases', 'parameters'):
        for a,b in (((12,34),(12,9)),((12,9),(67,9)),((67,9),(67,34))):
            line(a,b)
        if key == 'releases':
            line((12,34),(67,9))
            p.setBrush(QColor('white'))
            for x in (17,62):
                p.drawEllipse(QPointF(x,9), 3, 3)
        else:
            line((18,24),(61,24))
            for x in (18,61):
                line((x,21),(x,27))
            p.setFont(QFont('Poppins',8))
            p.drawText(QRectF(19,22,42,20), Qt.AlignmentFlag.AlignCenter, 'Ly / Lz')
    elif key == 'tables':
        p.drawRect(QRectF(10,5,60,32))
        for x in (25,40,55):
            line((x,5),(x,37))
        for y in (13,21,29):
            line((10,y),(70,y))
    elif key == 'combinations':
        p.setFont(QFont('Poppins',10,QFont.Weight.DemiBold))
        p.drawText(QRectF(0,0,80,42), Qt.AlignmentFlag.AlignCenter, 'DL + LL\n+ WL')
    elif key == 'girders':
        for x in (23,55):
            line((x,7),(x,35))
            line((x-9,7),(x+9,7))
            line((x-9,35),(x+9,35))
            line((x+2,7),(x+2,35))
    p.end()
    return QIcon(pixmap)
