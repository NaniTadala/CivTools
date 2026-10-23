"""Visual tokens and native Qt widget styling."""
def staad_palette():
    """Give native surfaces the same light colours as the suite's styled controls."""
    from PySide6.QtGui import QPalette, QColor
    palette = QPalette()
    colours = {'Window': '#F5F8FA', 'WindowText': '#233B4A', 'Base': '#FFFFFF',
               'AlternateBase': '#F6F9FB', 'Text': '#233B4A', 'Button': '#FFFFFF',
               'ButtonText': '#245B7A', 'Highlight': '#DDEFFA', 'HighlightedText': '#193E58',
               'ToolTipBase': '#193E58', 'ToolTipText': '#FFFFFF', 'PlaceholderText': '#7D929F',
               'Light': '#FFFFFF', 'Midlight': '#EDF3F7', 'Mid': '#D5E4EC',
               'Dark': '#9CB2C0', 'Shadow': '#D5E4EC'}
    for role, colour in colours.items():
        palette.setColor(getattr(QPalette.ColorRole, role), QColor(colour))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor('#899EAC'))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, QColor('#899EAC'))
    return palette

STAAD_WORKBENCH_STYLE = """
QWidget#staadWorkbench { background: #F5F8FA; }
QWidget#staadWorkbench QLabel#workbenchTitle { font-size: 21px; font-weight: 600; color: #193E58; }
QWidget#staadWorkbench QLabel#title { font-size: 22px; font-weight: 600; color: #193E58; }
QWidget#staadWorkbench QLabel#modelStatus { padding: 0 5px; color: #536C7B; }
QWidget#staadWorkbench QFrame#toolNavigator { background: #FFFFFF; border: 1px solid #DEE8EE; border-radius: 6px; }
QWidget#staadWorkbench QLabel#navHeading { font-size: 10px; font-weight: 600; color: #527A94; padding: 10px 3px 4px; }
QWidget#staadWorkbench QPushButton { border-radius: 4px; padding: 7px 11px; }
QWidget#staadWorkbench QPushButton#workbenchNav { background: transparent; color: #233B4A; text-align: left; border: 1px solid transparent; border-left: 3px solid transparent; padding: 7px 8px; font-weight: 400; }
QWidget#staadWorkbench QPushButton#workbenchNav:hover { background: #F2F7FA; }
QWidget#staadWorkbench QPushButton#workbenchNav:checked { background: #E6F3FA; color: #176B9F; border-left-color: #1682BC; font-weight: 600; }
QWidget#staadWorkbench QPushButton#workbenchNav:focus { border-top-color: #88C5E4; border-right-color: #88C5E4; border-bottom-color: #88C5E4; }
QWidget#staadWorkbench QLineEdit, QWidget#staadWorkbench QComboBox, QWidget#staadWorkbench QAbstractSpinBox { border-radius: 4px; padding: 7px; }
QWidget#staadWorkbench QTableView { border-radius: 4px; }
QWidget#staadWorkbench QHeaderView::section { padding: 8px; }
QWidget#staadWorkbench QToolButton { background: white; color: #245B7A; border: 1px solid #D5E4EC; border-radius: 4px; padding: 7px 12px; }
QWidget#staadWorkbench QMenu { background: white; color: #233B4A; border: 1px solid #D5E4EC; padding: 4px; }
QWidget#staadWorkbench QMenu::item { padding: 7px 16px; }
QWidget#staadWorkbench QMenu::item:selected { background: #E6F3FA; color: #176B9F; }
QWidget#staadWorkbench QLabel#hint, QWidget#staadWorkbench QLabel#success,
QWidget#staadWorkbench QLabel#error, QWidget#staadWorkbench QLabel#warning { border: none; border-radius: 3px; padding: 3px 5px; }
QWidget#staadWorkbench QCheckBox { padding: 4px 0; }
QWidget#staadWorkbench QCheckBox:disabled { color: #899EAC; }
QWidget#staadWorkbench QLabel#scopeSummary { background: #EBF5FA; border: 1px solid #D7E8F1; padding: 9px; border-radius: 4px; color: #4F6F83; }
QWidget#staadWorkbench { font-size: 12px; }
QWidget#staadWorkbench QPushButton, QWidget#staadWorkbench QToolButton { padding: 5px 7px; }
QWidget#staadWorkbench QLineEdit, QWidget#staadWorkbench QComboBox, QWidget#staadWorkbench QAbstractSpinBox { padding: 4px 6px; min-height: 19px; }
QWidget#staadWorkbench QAbstractSpinBox QLineEdit { padding: 0; min-height: 0; border: none; }
QWidget#staadWorkbench QCheckBox { padding: 2px 0; spacing: 5px; }
QWidget#staadWorkbench QCheckBox::indicator { width: 15px; height: 15px; }
QWidget#staadWorkbench QLabel#navHeading { padding: 3px 0; font-size: 9px; }
QWidget#staadWorkbench QLabel#scopeSummary { padding: 5px; }
QWidget#staadWorkbench QPushButton#favouriteTool { background: white; color: #245B7A; border: 1px solid #D5E4EC; font-weight: 400; }
QWidget#staadWorkbench QPushButton#favouriteTool:checked { background: #E6F3FA; color: #176B9F; border-color: #1682BC; }
QWidget#staadWorkbench QTabBar::tab { padding: 5px 7px; margin-right: 1px; font-size: 11px; }
QWidget#staadWorkbench QWidget { font-family: 'Segoe UI'; font-size: 12px; }
QWidget#staadWorkbench QMainWindow, QWidget#staadWorkbench QStackedWidget,
QWidget#staadWorkbench QTabWidget > QWidget { background: #F5F8FA; }
QWidget#staadWorkbench QPushButton, QWidget#staadWorkbench QToolButton { min-height: 18px; padding: 5px 9px; }
QWidget#staadWorkbench QToolButton { padding-right: 19px; }
QWidget#staadWorkbench QToolButton::menu-indicator { subcontrol-origin: padding; subcontrol-position: right center; right: 5px; }
QWidget#staadWorkbench QComboBox QLineEdit { border: none; background: transparent; padding: 0; min-height: 0; }
QWidget#staadWorkbench QAbstractSpinBox QLineEdit { padding: 0; border: none; min-height: 0; }
QWidget#staadWorkbench QTableView::item { padding: 3px 6px; }
QWidget#staadWorkbench QHeaderView::section { padding: 7px 6px; font-weight: 600; }
QWidget#staadWorkbench QTabWidget::pane { border: 1px solid #D5E4EC; border-radius: 5px; background: white; }
QWidget#staadWorkbench QTabBar::tab { font-size: 12px; padding: 6px 12px; margin-right: 3px; }
QWidget#staadWorkbench QLabel#parameterContext { color: #536C7B; padding: 5px 7px; background: #EBF5FA; border-radius: 4px; }
QWidget#staadWorkbench QScrollBar:horizontal { background: #EDF3F7; height: 9px; margin: 0; }
QWidget#staadWorkbench QScrollBar::handle:horizontal { background: #BCD0DE; min-width: 30px; border-radius: 4px; }
QWidget#staadWorkbench QScrollBar::add-line:horizontal, QWidget#staadWorkbench QScrollBar::sub-line:horizontal { width: 0; }
QWidget#staadWorkbench QScrollBar::add-page:horizontal, QWidget#staadWorkbench QScrollBar::sub-page:horizontal { background: transparent; }
QWidget#staadWorkbench QTableCornerButton::section { background: #F2F7FA; border: none; }
QWidget#staadWorkbench QWidget#parameterForm, QWidget#staadWorkbench QTabBar { background: #F5F8FA; }
QWidget#staadWorkbench QFrame#pebFamily { background: #EAF2F7; border: 1px solid #D5E4EC; border-radius: 6px; }
QWidget#staadWorkbench QPushButton#pebVariant { background: white; color: #245B7A; border: 1px solid #D5E4EC; border-radius: 4px; font-weight: 400; }
QWidget#staadWorkbench QPushButton#pebVariant:hover { background: #E6F3FA; border-color: #88C5E4; }
QWidget#staadWorkbench QPushButton#pebVariant:checked { background: #1682BC; color: white; border-color: #1682BC; font-weight: 600; }
"""
STYLE = """
QWidget { font-family: 'Poppins'; font-size: 13px; color: #233B4A; }
QMainWindow, QWidget#workspace, QStackedWidget { background: #F5F8FA; }
QDialog, QMessageBox { background: #F5F8FA; color: #233B4A; }
QDialog QLabel, QMessageBox QLabel { color: #233B4A; background: transparent; }
QDialog QCheckBox { color: #233B4A; background: transparent; }
QDialog QCheckBox:disabled { color: #899EAC; }
QDialog QDialogButtonBox { background: transparent; }
QListWidget { background: white; color: #233B4A; border: 1px solid #D5E4EC; border-radius: 7px; selection-background-color: #E3F1F8; selection-color: #194865; }
QListWidget::item { padding: 6px; }
QFrame#sidebar { background: #153B55; border: none; }
QLabel#brand { color: white; font-size: 29px; font-weight: 700; }
QLabel#sidebarCaption { color: #A9C6D8; font-size: 10px; letter-spacing: 1px; }
QLabel#sidebarFoot { color: #A9C6D8; font-size: 12px; }
QPushButton#nav { background: transparent; color: #C5DCE9; border: none; text-align: left; padding: 13px 18px; border-radius: 8px; font-size: 14px; }
QPushButton#nav:hover { background: #214E6B; color: white; }
QPushButton#nav:checked { background: #286486; color: white; font-weight: 600; }
QLabel#eyebrow { color: #527A94; font-size: 11px; font-weight: 700; letter-spacing: 2px; }
QLabel#title { font-size: 24px; font-weight: 700; color: #193E58; }
QLabel#subtitle { color: #536C7B; font-size: 12px; }
QLabel#sectionTitle { font-size: 17px; font-weight: 600; }
QLabel#muted { color: #536C7B; }
QLabel#badge { color: #176FA5; background: #E6F3FA; border-radius: 5px; padding: 5px 9px; font-size: 11px; font-weight: 600; }
QLabel#hint { background: #EBF5FA; color: #4F6F83; border: 1px solid #D7E8F1; border-radius: 8px; padding: 8px; }
QLabel#error { color: #AD3D3D; background: #FBEFEC; border: 1px solid #F0D9D3; border-radius: 8px; padding: 8px; }
QLabel#success { color: #176B50; background: #E8F2EB; border: 1px solid #CDE2D3; border-radius: 8px; padding: 8px; }
QFrame#panel, QFrame#toolCard { background: white; border: 1px solid #DEE8EE; border-radius: 12px; }
QFrame#toolCard:hover { border: 1px solid #8ABBD5; background: #FCFEFF; }
QFrame#hero { background: #E8F3FA; border: 1px solid #D5E7F1; border-radius: 14px; }
QLabel#heroTitle { font-size: 27px; font-weight: 700; color: #194865; }
QLabel#cardTitle { font-size: 15px; font-weight: 600; }
QLabel#cardDescription { color: #536C7B; font-size: 12px; }
QLabel#cardCategory { color: #527A94; font-size: 10px; font-weight: 600; }
QPushButton[cardAction="true"] { padding: 6px 12px; }
QLabel#cardNumber { color: #91A7B4; font-size: 11px; }
QPushButton { background: #1682BC; color: white; border: 1px solid #1682BC; border-radius: 7px; padding: 10px 17px; font-weight: 600; }
QPushButton:hover { background: #116A9B; border-color: #116A9B; }
QPushButton:pressed { background: #0E557F; }
QPushButton:focus { border: 2px solid #88C5E4; }
QPushButton:disabled { background: #DDE8EF; border-color: #DDE8EF; color: #899EAC; }
QPushButton#secondary { background: white; color: #245B7A; border: 1px solid #D5E4EC; }
QPushButton#secondary:hover { background: #EFF7FB; border-color: #9FC9DE; }
QPushButton#secondary:disabled { background: #F1F5F7; color: #98A8B1; border-color: #E5ECEF; }
QPushButton#chip { background: transparent; color: #6D818D; border: 1px solid #DEE8EE; border-radius: 16px; padding: 6px 14px; font-weight: 400; }
QPushButton#chip:checked { background: #E6F3FA; color: #176B9F; border-color: #B9D9E9; font-weight: 600; }
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox { background: #FFFFFF; border: 1px solid #D5E4EC; border-radius: 7px; padding: 7px 10px; min-height: 19px; selection-background-color: #C9E6F5; selection-color: #193E58; }
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus { border: 1px solid #1682BC; background: #FCFEFF; }
QLineEdit:disabled, QComboBox:disabled { background: #F1F5F7; color: #95A5AE; }
QComboBox::drop-down { border: none; width: 25px; }
QComboBox QAbstractItemView { background: white; border: 1px solid #D5E4EC; selection-background-color: #E4F2F9; selection-color: #193E58; padding: 6px; }
QCheckBox { spacing: 10px; padding: 8px 0px; }
QCheckBox::indicator { width: 18px; height: 18px; border-radius: 4px; border: 1px solid #B8CCD7; background: white; }
QCheckBox::indicator:checked { background: #1682BC; border: 3px solid #B7DBEC; }
QPlainTextEdit { border: 1px solid #E0E8ED; background: #F9FBFC; border-radius: 8px; padding: 10px; font-family: 'Cascadia Code', 'Consolas'; font-size: 12px; color: #586F7D; }
QScrollArea { border: none; background: transparent; }
QScrollArea > QWidget > QWidget { background: transparent; }
QScrollBar:vertical { background: transparent; width: 8px; margin: 2px; }
QScrollBar::handle:vertical { background: #C2D5E0; border-radius: 3px; min-height: 30px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QProgressBar { background: #E6EFF4; border: none; border-radius: 3px; height: 6px; max-height: 6px; }
QProgressBar::chunk { background: #1682BC; border-radius: 3px; }
QTableView { background: white; alternate-background-color: #F6F9FB; border: 1px solid #E0E8ED; border-radius: 8px; gridline-color: #EDF2F5; selection-background-color: #E3F1F8; selection-color: #194865; }
QTableView::item { padding: 8px; border: none; }
QHeaderView::section { background: #F2F7FA; border: none; border-bottom: 1px solid #E0E8ED; padding: 12px; color: #607785; font-weight: 600; }
QTabWidget::pane { background: white; border: 1px solid #DEE8EE; border-radius: 8px; top: -1px; }
QTabBar::tab { background: #E8F3F8; color: #245B7A; border: 1px solid #DEE8EE; border-bottom: none; border-top-left-radius: 7px; border-top-right-radius: 7px; padding: 8px 14px; margin-right: 4px; font-weight: 600; }
QTabBar::tab:selected { background: white; color: #176FA5; border-color: #DEE8EE; }
QTabBar::tab:hover:!selected { background: #DCECF5; color: #193E58; }
QStatusBar { background: #F5F8FA; color: #718592; border-top: 1px solid #E1E9EE; }
QToolTip { background: #173D57; color: white; border: none; padding: 8px; }
QSplitter::handle { background: transparent; width: 12px; }
"""

STYLE += """
QLabel#warning { color: #795210; background: #FFF5DA; border: 1px solid #E3CF9A; border-radius: 7px; padding: 8px; }
QLineEdit[invalid="true"], QDoubleSpinBox[invalid="true"] { border: 2px solid #AD3D3D; }
QCheckBox:focus { background: #E5F1F7; border-radius: 4px; }
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus { border: 2px solid #1682BC; }
"""


def style_for_scale(percent):
    import re
    factor = percent / 100
    return re.sub(r"font-size: (\d+)px", lambda match: f"font-size: {round(int(match[1]) * factor)}px", STYLE)
