"""Compact launcher with independent, state-preserving utility windows."""
import os
from pathlib import Path
import sys

from PySide6.QtCore import Qt, QThreadPool, QTimer, QUrl, QSettings, QEvent
from PySide6.QtGui import QFont, QFontDatabase, QIcon, QKeySequence, QShortcut, QDesktopServices
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QFrame, QVBoxLayout,
    QHBoxLayout, QGridLayout, QStackedWidget, QScrollArea, QLineEdit, QComboBox, QMessageBox, QSizePolicy)
from .qt_style import STYLE, style_for_scale
from .qt_widgets import label, button, tool_icon, ComboBox, CheckBox as QCheckBox
from .qt_artwork import IntegrationStrip
from .jobs import PdfProcess, Job

TOOLS = (
    ("quantities", "DXF quantity extractor", "Quantities", "Extract drawing quantities and consolidate them in Excel.", "DXF / EXCEL"),
    ("dj", "DJ parameter assigner", "Modeling", "Assign DJ parameters to physical members in STAAD.Pro.", "STAAD.PRO"),
    ("rack", "Pipe rack modeler", "Modeling", "Configure grids, tiers and bracing for a STAAD model.", "STAAD.PRO"),
    ("mapper", "AutoCAD smart mapper", "Drawings", "Plot spreadsheet coordinates and labels in AutoCAD.", "EXCEL / CAD"),
    ("library", "EIL standards library", "Documents", "Find, preview and open engineering standards.", "PDF LIBRARY"),
)

def get_resource_path(relative_path):
    if getattr(sys, "frozen", False):
        adjacent = Path(sys.executable).parent / relative_path
        return str(adjacent if adjacent.exists() else Path(sys._MEIPASS) / relative_path)
    return str(Path(__file__).resolve().parents[2] / relative_path)


class ToolCard(QFrame):
    def __init__(self, tool, callback):
        super().__init__()
        self.tool = tool
        self.setObjectName("toolCard")
        self.setMinimumWidth(210)
        self.setMinimumHeight(204)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        row = QVBoxLayout(self)
        row.setContentsMargins(14, 12, 14, 12)
        row.setSpacing(7)
        heading = QHBoxLayout()
        icon = label("")
        icon.setPixmap(tool_icon(tool[0], 36).pixmap(36, 36))
        icon.setToolTip(tool[4])
        heading.addWidget(icon)
        heading.addStretch()
        heading.addWidget(label(tool[2], "cardCategory"))
        row.addLayout(heading)
        row.addWidget(label(tool[1], "cardTitle", True))
        row.addWidget(label(tool[3], "cardDescription", True), 1)
        self.open_button = button("Open", callback, True)
        self.open_button.setProperty("cardAction", True)
        self.open_button.setAccessibleName(f"Open {tool[1]}")
        row.addWidget(self.open_button)

    def adjust_height(self):
        if self.layout():
            required = max(204, self.layout().totalHeightForWidth(self.width()))
            if required != self.minimumHeight():
                self.setMinimumHeight(required)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.adjust_height()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() in (QEvent.Type.FontChange, QEvent.Type.StyleChange):
            QTimer.singleShot(0, self.adjust_height)


class Dashboard(QWidget):
    def __init__(self, window):
        super().__init__()
        self.window = window
        self.category = "All tools"
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 18, 22, 16)
        layout.setSpacing(12)
        top = QHBoxLayout()
        copy = QVBoxLayout()
        copy.setSpacing(0)
        copy.addWidget(label("CivTools", "title"))
        copy.addWidget(label("Pick a tool. Keep your workspace.", "muted"))
        top.addLayout(copy)
        top.addStretch()
        top.addWidget(IntegrationStrip())
        layout.addLayout(top)
        search_row = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Find a tool…  Ctrl+F")
        self.search.setClearButtonEnabled(True)
        self.search.setAccessibleName("Search engineering tools")
        self.search.textChanged.connect(self.filter_cards)
        search_row.addWidget(self.search, 1)
        self.categories = ComboBox()
        self.categories.addItems(["All tools", "Modeling", "Quantities", "Drawings", "Documents"])
        self.categories.currentTextChanged.connect(self.set_category)
        search_row.addWidget(self.categories)
        layout.addLayout(search_row)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.surface = QWidget()
        rows = self.grid = QGridLayout(self.surface)
        rows.setContentsMargins(0, 0, 0, 0)
        rows.setSpacing(12)
        rows.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.cards = [ToolCard(tool, lambda t=tool: window.navigate(t[0])) for tool in TOOLS]
        self.empty = label("No matching tools. Clear the search or choose All tools.", "muted", True)
        scroll.setWidget(self.surface)
        layout.addWidget(scroll, 1)
        footer = QHBoxLayout()
        self.count = label("5 tools", "muted")
        footer.addWidget(self.count)
        footer.addStretch()
        footer.addWidget(label("Text size", "muted"))
        self.text_size = ComboBox()
        self.text_size.addItems(["100%", "115%", "130%"])
        self.text_size.setAccessibleName("Interface text size")
        self.text_size.setCurrentText(str(window.settings.value("text_size", "100%")))
        self.text_size.currentTextChanged.connect(window.set_text_size)
        footer.addWidget(self.text_size)
        footer.addWidget(button("Tutorials", window.open_tutorials, True))
        layout.addLayout(footer)
        self.filter_cards()

    def set_category(self, category):
        self.category = category
        self.filter_cards()

    def filter_cards(self, *args):
        query = self.search.text().strip().casefold()
        count = 0
        for card in self.cards:
            visible = (self.category == "All tools" or card.tool[2] == self.category) and query in " ".join(card.tool[1:]).casefold()
            card.setVisible(visible)
            count += visible
        self.empty.setVisible(count == 0)
        self.count.setText(f"{count} {'tool' if count == 1 else 'tools'}")
        self.arrange_cards()

    def arrange_cards(self):
        scale = getattr(self.window, "text_scale", 100) / 100
        columns = 3 if self.width() >= 720 * scale else 2 if self.width() >= 480 * scale else 1
        visible = [card for card in self.cards if not card.isHidden()]
        signature = (columns, tuple(card.tool[0] for card in visible))
        if getattr(self, "_arrangement", None) == signature:
            return
        self._arrangement = signature
        while self.grid.count():
            self.grid.takeAt(0)
        for column in range(3):
            self.grid.setColumnStretch(column, 1 if column < columns else 0)
        for index, card in enumerate(visible):
            self.grid.addWidget(card, index // columns, index % columns)
        self.grid.addWidget(self.empty, (len(visible) + columns - 1) // columns, 0, 1, columns)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "cards"):
            self.arrange_cards()


class UtilityWindow(QMainWindow):
    def __init__(self, launcher, key, page):
        # Unowned native windows remain usable when the launcher is minimized.
        super().__init__()
        self.launcher, self.key, self.page = launcher, key, page
        title = next(t[1] for t in TOOLS if t[0] == key)
        self.setWindowTitle(f"{title} · CivTools")
        self.setWindowIcon(tool_icon(key, 64))
        width, height = {"quantities": (640, 680), "dj": (580, 660), "rack": (720, 700),
                         "mapper": (580, 620), "library": (850, 680)}[key]
        self.resize(width, height)
        self.setMinimumSize(480, 460)
        central = QWidget()
        central.setObjectName("workspace")
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(18, 10, 18, 0)
        toolbar.addWidget(button("All tools", lambda: launcher.navigate("home"), True))
        toolbar.addStretch()
        self.pin = QCheckBox("Keep on top")
        self.pin.setToolTip("Keep this utility visible beside your CAD application")
        self.pin.toggled.connect(self.set_pinned)
        toolbar.addWidget(self.pin)
        layout.addLayout(toolbar)
        layout.addWidget(page, 1)
        self.setCentralWidget(central)
        geometry = launcher.settings.value(f"windows/{key}")
        if geometry:
            self.restoreGeometry(geometry)
        self.pin.setChecked(launcher.settings.value(f"pinned/{key}", False, type=bool))
        self.shortcuts = []
        for keys, handler in (("Alt+Home", lambda: launcher.navigate("home")), ("Ctrl+F", self.focus_search), ("Escape", self.clear_search)):
            shortcut = QShortcut(QKeySequence(keys), self)
            shortcut.activated.connect(handler)
            self.shortcuts.append(shortcut)

    def set_pinned(self, pinned):
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, pinned)
        self.show()

    def focus_search(self):
        if hasattr(self.page, "search"):
            self.page.search.setFocus()
            self.page.search.selectAll()

    def clear_search(self):
        if hasattr(self.page, "search"):
            self.page.search.clear()

    def closeEvent(self, event):
        # Keep inputs and active workers alive; closing a utility is reversible.
        event.ignore()
        self.save_state()
        self.hide()
        self.launcher.update_status()
        if self.page.busy:
            self.launcher.navigate("home")

    def save_state(self):
        self.launcher.settings.setValue(f"windows/{self.key}", self.saveGeometry())
        self.launcher.settings.setValue(f"pinned/{self.key}", self.pin.isChecked())
        self.page.save_state()


class CivToolsApp(QMainWindow):
    def __init__(self):
        super().__init__()
        from .qt_pages import config_root
        root = config_root()
        root.mkdir(parents=True, exist_ok=True)
        self.settings = QSettings(str(root / "workspace.ini"), QSettings.Format.IniFormat)
        for name in ("Regular", "SemiBold", "Bold"):
            QFontDatabase.addApplicationFont(get_resource_path(f"fonts/Poppins/Poppins-{name}.ttf"))
        self.setWindowTitle("CivTools · Toolkit")
        self.resize(780, 700)
        self.setMinimumSize(520, 500)
        self.setWindowIcon(QIcon(get_resource_path("assets/icons/logo.ico")))
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(3)
        self.cad_pool = QThreadPool(self)
        self.cad_pool.setMaxThreadCount(1)
        self.pdf = PdfProcess()
        self.pages, self.utility_windows = {}, {}
        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)
        self.dashboard = Dashboard(self)
        self.stack.addWidget(self.dashboard)
        self.pages["home"] = self.dashboard
        self.shortcuts = []
        for keys, handler in (("Ctrl+F", self.focus_search), ("Escape", lambda: self.dashboard.search.clear())):
            shortcut = QShortcut(QKeySequence(keys), self)
            shortcut.activated.connect(handler)
            self.shortcuts.append(shortcut)
        self.update_status()
        geometry = self.settings.value("windows/home")
        if geometry:
            self.restoreGeometry(geometry)
        self.set_text_size(self.dashboard.text_size.currentText())

    def set_text_size(self, value):
        percent = int(value.rstrip("%")) if value in ("100%", "115%", "130%") else 100
        self.text_scale = percent
        self.dashboard.text_size.blockSignals(True)
        self.dashboard.text_size.setCurrentText(f"{percent}%")
        self.dashboard.text_size.blockSignals(False)
        QApplication.instance().setStyleSheet(style_for_scale(percent))
        self.settings.setValue("text_size", f"{percent}%")
        self.dashboard.arrange_cards()

    def navigate(self, key):
        if key == "home":
            self.showNormal() if self.isMinimized() else self.show()
            self.raise_()
            self.activateWindow()
            return
        if key not in self.pages:
            from .qt_pages import QuantityPage, MapperPage, RackPage, DJPage, LibraryPage
            factory = {"quantities": QuantityPage, "mapper": MapperPage, "rack": RackPage, "dj": DJPage, "library": LibraryPage}
            page = factory[key](self)
            page.restore_state(key)
            utility = UtilityWindow(self, key, page)
            self.pages[key] = page
            self.utility_windows[key] = utility
        window = self.utility_windows[key]
        window.showNormal() if window.isMinimized() else window.show()
        window.raise_()
        window.activateWindow()
        self.update_status()

    def focus_search(self):
        self.dashboard.search.setFocus()
        self.dashboard.search.selectAll()

    def update_status(self):
        active = sum(getattr(page, "busy", False) for page in self.pages.values())
        self.statusBar().showMessage(f"{active} operation{'s' if active != 1 else ''} running · Reopen a tool to view progress" if active else "Tools open in their own windows · Inputs stay when you close them")
        for card in self.dashboard.cards:
            page = self.pages.get(card.tool[0])
            card.open_button.setText("Running…" if getattr(page, "busy", False) else "Resume" if page else "Open")

    def open_tutorials(self):
        path = os.environ.get("CIVTOOLS_TUTORIALS_PATH")
        if not path or not Path(path).is_dir():
            QMessageBox.information(self, "Video tutorials", "Set CIVTOOLS_TUTORIALS_PATH to your local tutorials folder.")
        elif not QDesktopServices.openUrl(QUrl.fromLocalFile(path)):
            QMessageBox.warning(self, "Video tutorials", "The tutorials folder could not be opened.")

    def closeEvent(self, event):
        if any(getattr(page, "busy", False) for page in self.pages.values()):
            QMessageBox.information(self, "Operation in progress", "Let the running operations finish before exiting CivTools. You can minimize the toolkit while they run.")
            event.ignore()
            return
        if self.pool.activeThreadCount() or self.cad_pool.activeThreadCount():
            event.ignore()
            QTimer.singleShot(100, self.close)
            return
        for window in self.utility_windows.values():
            window.save_state()
            window.hide()
        self.settings.setValue("windows/home", self.saveGeometry())
        self.settings.sync()
        self.pdf.close()
        event.accept()


def main():
    smoke_test = "--smoke-test" in sys.argv
    if smoke_test:
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
    app = QApplication(sys.argv)
    app.setApplicationName("CivTools")
    app.setOrganizationName("CivTools")
    app.setStyle("Fusion")
    app.setFont(QFont("Poppins", 10))
    app.setStyleSheet(STYLE)
    window = CivToolsApp()
    window.show()
    if smoke_test:
        failures = []
        pdf_checked = []
        sys.excepthook = lambda kind, value, traceback: failures.append(str(value))
        for card in window.dashboard.cards:
            card.open_button.click()
        pdf_check = Job(lambda report: window.pdf.call("selftest", report))
        pdf_check.signals.succeeded.connect(lambda result: pdf_checked.append(result.startswith(b"\x89PNG")))
        pdf_check.signals.failed.connect(failures.append)
        window.pool.start(pdf_check)
        def smoke_complete():
            if window.pool.activeThreadCount() or window.cad_pool.activeThreadCount() or any(getattr(p, "busy", False) for p in window.pages.values()):
                return
            valid = not failures and pdf_checked == [True] and all(
                key in window.utility_windows and window.utility_windows[key].isVisible()
                for key, *_ in TOOLS)
            window.pdf.close()
            report_path = os.environ.get("CIVTOOLS_SMOKE_REPORT")
            if report_path:
                import json
                Path(report_path).write_text(json.dumps({"passed": valid, "failures": failures, "pdf_rendered": pdf_checked == [True], "tools": list(window.utility_windows)}, indent=2), encoding="utf-8")
            app.exit(0 if valid else 1)
        deadline = QTimer(window)
        deadline.setSingleShot(True)
        deadline.timeout.connect(lambda: app.exit(1))
        deadline.start(30000)
        timer = QTimer(window)
        timer.timeout.connect(smoke_complete)
        timer.start(50)
    sys.exit(app.exec())
