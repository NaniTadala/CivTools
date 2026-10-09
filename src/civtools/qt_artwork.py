"""Cached, high-DPI integration marks and original engineering illustrations."""
from functools import lru_cache
from PySide6.QtCore import Qt, QPointF, QRectF, QSize
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QWidget

ACCENTS = {
    "quantities": ("#E8F1FB", "#39719C"), "mapper": ("#FBECE9", "#C94438"),
    "dj": ("#EAF0FB", "#456CA5"), "rack": ("#F0ECFA", "#7963AB"),
    "library": ("#FBF2E1", "#A77C31"), "excel": ("#E7F3EA", "#217346"),
}


@lru_cache(maxsize=8)
def illustration(kind):
    """Draw compact original spot illustrations once; no file decoding or network."""
    pixmap = QPixmap(320, 224)
    pixmap.setDevicePixelRatio(2)
    pixmap.fill(Qt.GlobalColor.transparent)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    background, accent = ACCENTS[kind]
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(background))
    p.drawEllipse(QRectF(15, 9, 133, 92))
    p.setPen(QPen(QColor(accent), 1.8, Qt.PenStyle.SolidLine,
                  Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    p.setBrush(QColor("#FFFFFF"))
    if kind in ("quantities", "mapper"):
        p.drawRoundedRect(QRectF(15, 20, 53, 65), 5, 5)
        p.drawLine(25, 32, 56, 32)
        if kind == "quantities":
            p.drawRect(QRectF(25, 41, 31, 31))
            p.drawLine(25, 52, 56, 52); p.drawLine(25, 62, 56, 62)
            p.drawLine(38, 41, 38, 72)
        else:
            for y in (44, 54, 64, 74):
                p.drawLine(25, y, 56, y)
            p.drawLine(40, 44, 40, 74)
        p.drawLine(74, 52, 89, 52)
        p.drawLine(84, 47, 89, 52); p.drawLine(84, 57, 89, 52)
        if kind == "quantities":
            product_icon("excel", 52).paint(p, 95, 34, 52, 52)
        else:
            p.drawRoundedRect(QRectF(95, 20, 53, 65), 5, 5)
            p.drawLine(104, 68, 138, 68); p.drawLine(110, 77, 110, 38)
            p.drawRect(QRectF(116, 40, 20, 22))
            p.setBrush(QColor(accent))
            p.drawEllipse(QPointF(126, 51), 2.5, 2.5)
            product_icon("mapper", 25).paint(p, 123, 73, 25, 25)
    elif kind in ("rack", "dj"):
        if kind == "rack":
            points = [(32, 49), (65, 62), (117, 38), (84, 25)]
            for a, b in zip(points, points[1:] + points[:1]):
                p.drawLine(QPointF(*a), QPointF(*b))
                p.drawLine(QPointF(a[0], a[1] + 24), QPointF(b[0], b[1] + 24))
            for x, y in points:
                p.drawLine(x, y, x, y + 44)
                p.drawLine(x - 4, y + 44, x + 4, y + 44)
            p.drawLine(65, 86, 91, 74); p.drawLine(91, 74, 117, 62)
            p.drawLine(65, 62, 91, 74); p.drawLine(91, 74, 117, 38)
            product_icon("rack", 27).paint(p, 119, 76, 27, 27)
        else:
            p.drawLine(37, 82, 37, 27); p.drawLine(37, 27, 120, 27); p.drawLine(120, 27, 120, 82)
            p.drawLine(37, 53, 120, 53)
            p.setBrush(QColor("#FFFFFF"))
            for x, y in ((37, 27), (120, 27), (37, 53), (120, 53)):
                p.drawEllipse(QPointF(x, y), 4, 4)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(accent))
            for x, caption in ((18, "DJ1"), (105, "DJ2")):
                p.drawRoundedRect(QRectF(x, 76, 38, 19), 5, 5)
                p.setPen(QColor("#FFFFFF"))
                p.setFont(QFont("Poppins", 8, QFont.Weight.DemiBold))
                p.drawText(QRectF(x, 76, 38, 19), Qt.AlignmentFlag.AlignCenter, caption)
                p.setPen(Qt.PenStyle.NoPen)
    else:
        p.drawRoundedRect(QRectF(56, 15, 63, 76), 5, 5)
        p.drawRoundedRect(QRectF(45, 24, 63, 76), 5, 5)
        p.drawRoundedRect(QRectF(33, 32, 63, 76), 5, 5)
        p.drawLine(46, 47, 82, 47)
        p.drawRect(QRectF(47, 57, 25, 19))
        p.drawLine(47, 85, 81, 85); p.drawLine(47, 93, 70, 93)
        product_icon("library", 32).paint(p, 103, 71, 32, 32)
    p.end()
    return pixmap


@lru_cache(maxsize=32)
def product_icon(kind, size=48):
    """Distinct integration and file-type marks, rendered sharply at 2× resolution."""
    background, accent = ACCENTS.get(kind, ACCENTS["quantities"])
    pixmap = QPixmap(size * 2, size * 2)
    pixmap.setDevicePixelRatio(2)
    pixmap.fill(Qt.GlobalColor.transparent)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.scale(size / 48, size / 48)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(background))
    p.drawRoundedRect(QRectF(0, 0, 48, 48), 11, 11)
    p.setPen(QPen(QColor(accent), 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    p.setBrush(Qt.BrushStyle.NoBrush)
    if kind == "mapper":
        # AutoCAD's familiar red A, treated as an integration identifier.
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(accent))
        path = QPainterPath()
        path.moveTo(10, 36); path.lineTo(20, 11); path.lineTo(28, 11)
        path.lineTo(38, 36); path.lineTo(30, 36); path.lineTo(27.5, 29)
        path.lineTo(19, 29); path.lineTo(16.5, 36); path.closeSubpath()
        hole = QPainterPath()
        hole.moveTo(21, 23); hole.lineTo(24, 16); hole.lineTo(26, 23); hole.closeSubpath()
        p.drawPath(path.subtracted(hole))
    elif kind in ("dj", "rack"):
        for x in (12, 24, 36):
            p.drawLine(x, 13, x, 35)
        for y in (14, 25, 35):
            p.drawLine(12, y, 36, y)
        p.drawLine(12, 25, 24, 14)
        p.drawLine(24, 25, 36, 14)
        if kind == "dj":
            p.setBrush(QColor(accent))
            for x, y in ((12, 14), (24, 25), (36, 35)):
                p.drawEllipse(QPointF(x, y), 2.6, 2.6)
        else:
            p.drawLine(12, 35, 24, 25)
            p.drawLine(24, 35, 36, 25)
    elif kind == "excel":
        p.drawRoundedRect(QRectF(20, 12, 18, 25), 2, 2)
        for y in (19, 25, 31):
            p.drawLine(21, y, 37, y)
        p.drawLine(29, 13, 29, 36)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(accent))
        p.drawRoundedRect(QRectF(9, 17, 19, 20), 3, 3)
        p.setPen(QPen(QColor("#FFFFFF"), 2.4))
        p.drawLine(14, 22, 23, 32)
        p.drawLine(23, 22, 14, 32)
    elif kind == "library":
        p.drawRoundedRect(QRectF(15, 9, 21, 27), 2, 2)
        p.drawLine(10, 14, 10, 39)
        p.drawLine(10, 39, 31, 39)
        for y in (17, 23, 29):
            p.drawLine(21, y, 30, y)
    else:
        p.drawRoundedRect(QRectF(10, 8, 22, 29), 2, 2)
        p.drawLine(15, 16, 26, 16)
        p.drawRect(15, 21, 11, 10)
        p.drawLine(20, 21, 20, 31)
        p.drawLine(15, 26, 26, 26)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#217346"))
        p.drawRoundedRect(QRectF(25, 27, 16, 15), 3, 3)
        p.setPen(QPen(QColor("#FFFFFF"), 1.8))
        p.drawLine(30, 31, 36, 38)
        p.drawLine(36, 31, 30, 38)
    p.end()
    return QIcon(pixmap)


class ToolIllustration(QWidget):
    """A small spot illustration that adds character without taking form space."""
    def __init__(self, kind, parent=None):
        super().__init__(parent)
        self.kind = kind
        self.setFixedSize(86, 64)
        self.setAccessibleName(f"{kind} engineering illustration")
        self.setToolTip({"mapper": "Excel coordinates → AutoCAD geometry", "dj": "STAAD.Pro concrete and steel design parameters",
                         "rack": "STAAD.Pro pipe rack modeling", "quantities": "DXF drawings → Excel quantities",
                         "library": "EIL engineering standards"}[kind])

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        background, accent = ACCENTS[self.kind]
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(background))
        p.drawRoundedRect(QRectF(0, 0, 86, 64), 12, 12)
        p.drawPixmap(QRectF(0, 2, 86, 60), illustration(self.kind), QRectF(0, 0, 320, 224))
        p.end()


class IntegrationStrip(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(157, 49)
        self.setAccessibleName("Works with AutoCAD, STAAD.Pro and Excel")
        self.setToolTip("AutoCAD · STAAD.Pro · Excel")

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setFont(QFont("Poppins", 7))
        for i, (key, caption) in enumerate((("mapper", "AutoCAD"), ("dj", "STAAD.Pro"), ("excel", "Excel"))):
            product_icon(key, 28).paint(p, i * 53 + 12, 0, 28, 28)
            p.setPen(QColor("#637C70"))
            p.drawText(QRectF(i * 53, 31, 53, 18), Qt.AlignmentFlag.AlignCenter, caption)
        p.end()


@lru_cache(maxsize=24)
def action_icon(kind, secondary=False):
    """Tiny icons for commands, matching button contrast and the toolkit's stroke."""
    pixmap = QPixmap(32, 32)
    pixmap.setDevicePixelRatio(2)
    pixmap.fill(Qt.GlobalColor.transparent)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QPen(QColor("#315B44" if secondary else "#FFFFFF"), 1.4,
                  Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    if kind == "add":
        p.drawLine(8, 3, 8, 13); p.drawLine(3, 8, 13, 8)
    elif kind in ("remove", "clear"):
        p.drawLine(4, 5, 12, 5); p.drawLine(6, 3, 10, 3)
        p.drawRoundedRect(QRectF(5, 6, 6, 7), 1, 1)
    elif kind == "refresh":
        p.drawArc(QRectF(3, 3, 10, 10), 40 * 16, 285 * 16)
        p.drawLine(12, 3, 12, 7); p.drawLine(12, 7, 8, 7)
    elif kind == "folder":
        path = QPainterPath()
        path.moveTo(2, 5); path.lineTo(2, 3); path.lineTo(6, 3); path.lineTo(8, 5)
        path.lineTo(14, 5); path.lineTo(14, 12); path.lineTo(2, 12); path.closeSubpath()
        p.drawPath(path)
    elif kind == "save":
        p.drawRoundedRect(QRectF(3, 2, 10, 12), 1, 1)
        p.drawRect(5, 3, 6, 3); p.drawRect(5, 9, 6, 4)
    elif kind == "activity":
        for y in (4, 8, 12):
            p.drawPoint(3, y); p.drawLine(6, y, 13, y)
    elif kind == "home":
        p.drawRect(3, 3, 4, 4); p.drawRect(10, 3, 4, 4)
        p.drawRect(3, 10, 4, 4); p.drawRect(10, 10, 4, 4)
    elif kind == "tutorials":
        p.drawRoundedRect(QRectF(2, 3, 12, 10), 2, 2)
        path = QPainterPath(); path.moveTo(6, 5); path.lineTo(10, 8); path.lineTo(6, 11); path.closeSubpath()
        p.drawPath(path)
    p.end()
    return QIcon(pixmap)
