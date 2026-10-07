"""Reusable Qt surfaces, icons and a live structural preview."""
import math
from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap, QPainterPath
from PySide6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QWidget, QComboBox, QCheckBox, QStyleOptionButton, QStyle
from .core.geometry import build_rack_plan
from .qt_artwork import product_icon, action_icon


class CheckBox(QCheckBox):
    def paintEvent(self, event):
        super().paintEvent(event)
        if self.isChecked():
            option = QStyleOptionButton()
            self.initStyleOption(option)
            rect = self.style().subElementRect(QStyle.SubElement.SE_CheckBoxIndicator, option, self)
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setPen(QPen(QColor("white"), 2))
            x, y = rect.center().x(), rect.center().y()
            painter.drawLine(QPointF(x - 4, y), QPointF(x - 1, y + 3))
            painter.drawLine(QPointF(x - 1, y + 3), QPointF(x + 5, y - 4))
            painter.end()


class ComboBox(QComboBox):
    """Keep the dropdown affordance visible across native and styled Qt themes."""
    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor("#526F5C" if self.isEnabled() else "#A4B3A9"), 1.5))
        x, y = self.width() - 15, self.height() / 2
        painter.drawLine(QPointF(x - 4, y - 2), QPointF(x, y + 2))
        painter.drawLine(QPointF(x, y + 2), QPointF(x + 4, y - 2))
        painter.end()


def label(text, name=None, wrap=False):
    result = QLabel(text)
    if name:
        result.setObjectName(name)
    result.setWordWrap(wrap)
    result.setTextFormat(Qt.TextFormat.PlainText)
    return result


def button(text, callback, secondary=False):
    arrow = "→" in text or "↗" in text
    result = QPushButton(text.replace("→", "").replace("↗", "").strip())
    if arrow:
        pixmap = QPixmap(16, 16)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor("#315B44" if secondary else "#FFFFFF"), 1.5))
        painter.drawLine(2, 8, 13, 8)
        painter.drawLine(9, 4, 13, 8)
        painter.drawLine(9, 12, 13, 8)
        painter.end()
        result.setIcon(QIcon(pixmap))
        result.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
    if secondary:
        result.setObjectName("secondary")
    if not arrow:
        caption = text.casefold()
        kind = next((key for prefix, key in (("add ", "add"), ("remove", "remove"), ("clear", "clear"),
                    ("browse", "folder"), ("choose folder", "folder"), ("refresh", "refresh"),
                    ("save", "save"), ("delete", "remove"), ("activity", "activity"),
                    ("all tools", "home"), ("tutorials", "tutorials")) if caption.startswith(prefix)), None)
        if kind:
            result.setIcon(action_icon(kind, secondary))
    result.setCursor(Qt.CursorShape.PointingHandCursor)
    # clicked(bool) must not replace default arguments captured by callbacks.
    result.clicked.connect(lambda checked=False: callback())
    return result


def panel(title, description=None):
    frame = QFrame()
    frame.setObjectName("panel")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(12, 10, 12, 12)
    layout.setSpacing(7)
    layout.addWidget(label(title, "sectionTitle"))
    if description:
        layout.addWidget(label(description, "muted", True))
    return frame, layout


def tool_icon(kind, size=46, dark=False):
    if kind in ("quantities", "mapper", "dj", "rack", "library", "excel"):
        return product_icon(kind, size)
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.scale(size / 48, size / 48)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor("#2B5846" if dark else "#EBF3E9"))
    painter.drawRoundedRect(QRectF(0, 0, 48, 48), 10, 10)
    painter.setPen(QPen(QColor("#BCD5C4" if dark else "#4C805C"), 1.8))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    if kind in ("rack", "dj"):
        for x in (13, 25, 35):
            painter.drawLine(x, 12, x, 36)
        for y in (16, 26, 35):
            painter.drawLine(13, y, 35, y)
        painter.drawLine(13, 26, 25, 16)
        painter.drawLine(25, 26, 35, 16)
    elif kind == "mapper":
        painter.drawRect(13, 13, 22, 22)
        painter.drawLine(24, 8, 24, 40)
        painter.drawLine(8, 24, 40, 24)
        painter.drawEllipse(QPointF(24, 24), 3, 3)
    elif kind == "library":
        painter.drawRoundedRect(QRectF(12, 10, 24, 28), 2, 2)
        for y in (18, 24, 30):
            painter.drawLine(18, y, 30, y)
    else:
        painter.drawRoundedRect(QRectF(12, 10, 24, 28), 2, 2)
        for y in (19, 26):
            painter.drawLine(12, y, 36, y)
        painter.drawLine(23, 19, 23, 38)
    painter.end()
    return QIcon(pixmap)


class RackPreview(QWidget):
    """Vector illustration; the modeler uses the same view to reflect form edits."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(260, 200)
        self.setAccessibleName("Pipe rack geometry preview")
        self.config = None
        self.plan = None

    def set_config(self, config):
        self.config = config
        self.plan = build_rack_plan(config) if config else None
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        p.setPen(QPen(QColor("#D5E2D0"), 1))
        for x in range(0, w, 24):
            p.drawLine(x, 0, x, h)
        for y in range(0, h, 24):
            p.drawLine(0, y, w, y)
        if self.plan is None:
            p.setPen(QColor("#AD3D3D"))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Correct the highlighted inputs to preview")
            p.end()
            return
        nodes = self.plan.nodes
        # One scale preserves the actual aspect ratio of the planned geometry.
        projected = [(x + .65 * z, -y - .28 * z + .12 * x) for x, y, z in nodes]
        xmin, xmax = min(x for x, y in projected), max(x for x, y in projected)
        ymin, ymax = min(y for x, y in projected), max(y for x, y in projected)
        scale = min((w - 36) / max(xmax - xmin, .001), (h - 36) / max(ymax - ymin, .001))
        points = [QPointF((w - (xmax - xmin) * scale) / 2 + (x - xmin) * scale,
                         (h - (ymax - ymin) * scale) / 2 + (y - ymin) * scale) for x, y in projected]
        for a, b, kind in self.plan.beams:
            p.setPen(QPen(QColor("#83A57F" if kind == "brace" else "#49745A"), 1.4 if kind == "brace" else 2))
            p.drawLine(points[a], points[b])
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#426B48"))
        for index in self.plan.foundations:
            p.drawEllipse(points[index], 3, 2)
        p.end()
