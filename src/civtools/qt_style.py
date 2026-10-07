"""Visual tokens and native Qt widget styling."""
STYLE = """
QWidget { font-family: 'Poppins'; font-size: 13px; color: #213C33; }
QMainWindow, QWidget#workspace, QStackedWidget { background: #F5F7F5; }
QFrame#sidebar { background: #143D32; border: none; }
QLabel#brand { color: white; font-size: 29px; font-weight: 700; }
QLabel#sidebarCaption { color: #A9C3B6; font-size: 10px; letter-spacing: 1px; }
QLabel#sidebarFoot { color: #A9C3B6; font-size: 12px; }
QPushButton#nav { background: transparent; color: #C5D9CE; border: none; text-align: left; padding: 13px 18px; border-radius: 8px; font-size: 14px; }
QPushButton#nav:hover { background: #214B3D; color: white; }
QPushButton#nav:checked { background: #2B5948; color: white; font-weight: 600; }
QLabel#eyebrow { color: #52776A; font-size: 11px; font-weight: 700; letter-spacing: 2px; }
QLabel#title { font-size: 24px; font-weight: 700; color: #193D2E; }
QLabel#subtitle { color: #536A5E; font-size: 12px; }
QLabel#sectionTitle { font-size: 17px; font-weight: 600; }
QLabel#muted { color: #536A5E; }
QLabel#badge { color: #176B50; background: #E8F2EB; border-radius: 5px; padding: 5px 9px; font-size: 11px; font-weight: 600; }
QLabel#hint { background: #EBF2ED; color: #4F6F5E; border: 1px solid #DAE7DD; border-radius: 8px; padding: 8px; }
QLabel#error { color: #AD3D3D; background: #FBEFEC; border: 1px solid #F0D9D3; border-radius: 8px; padding: 8px; }
QLabel#success { color: #176B50; background: #E8F2EB; border: 1px solid #CDE2D3; border-radius: 8px; padding: 8px; }
QFrame#panel, QFrame#toolCard { background: white; border: 1px solid #DFE8E0; border-radius: 12px; }
QFrame#toolCard:hover { border: 1px solid #8DB59D; background: #FCFEFC; }
QFrame#hero { background: #E7EEE4; border: 1px solid #D9E4D5; border-radius: 14px; }
QLabel#heroTitle { font-size: 27px; font-weight: 700; color: #1B4430; }
QLabel#cardTitle { font-size: 15px; font-weight: 600; }
QLabel#cardDescription { color: #536A5E; font-size: 12px; }
QLabel#cardCategory { color: #52776A; font-size: 10px; font-weight: 600; }
QPushButton[cardAction="true"] { padding: 6px 12px; }
QLabel#cardNumber { color: #92A79A; font-size: 11px; }
QPushButton { background: #176B50; color: white; border: 1px solid #176B50; border-radius: 7px; padding: 10px 17px; font-weight: 600; }
QPushButton:hover { background: #10553E; border-color: #10553E; }
QPushButton:pressed { background: #0D4633; }
QPushButton:focus { border: 2px solid #87B69C; }
QPushButton:disabled { background: #DDE7E0; border-color: #DDE7E0; color: #8DA396; }
QPushButton#secondary { background: white; color: #315B44; border: 1px solid #D6E2D9; }
QPushButton#secondary:hover { background: #EFF5EF; border-color: #9FBEA8; }
QPushButton#secondary:disabled { background: #F0F4F0; color: #98A99D; border-color: #E5ECE5; }
QPushButton#chip { background: transparent; color: #6D8174; border: 1px solid #DFE8E0; border-radius: 16px; padding: 6px 14px; font-weight: 400; }
QPushButton#chip:checked { background: #E4F0E7; color: #1B694C; border-color: #BDD8C4; font-weight: 600; }
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox { background: #FFFFFF; border: 1px solid #D6E2D9; border-radius: 7px; padding: 7px 10px; min-height: 19px; selection-background-color: #C6DFCD; selection-color: #1A4430; }
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus { border: 1px solid #398460; background: #FCFEFC; }
QLineEdit:disabled, QComboBox:disabled { background: #F0F4F0; color: #95A49A; }
QComboBox::drop-down { border: none; width: 25px; }
QComboBox QAbstractItemView { background: white; border: 1px solid #D6E2D9; selection-background-color: #E0EEE3; selection-color: #193D2E; padding: 6px; }
QCheckBox { spacing: 10px; padding: 8px 0px; }
QCheckBox::indicator { width: 18px; height: 18px; border-radius: 4px; border: 1px solid #B6CCBD; background: white; }
QCheckBox::indicator:checked { background: #176B50; border: 3px solid #B4D5BE; }
QPlainTextEdit { border: 1px solid #E0E8E1; background: #F9FBF8; border-radius: 8px; padding: 10px; font-family: 'Cascadia Code', 'Consolas'; font-size: 12px; color: #5B7161; }
QScrollArea { border: none; background: transparent; }
QScrollArea > QWidget > QWidget { background: transparent; }
QScrollBar:vertical { background: transparent; width: 8px; margin: 2px; }
QScrollBar::handle:vertical { background: #C0D2C4; border-radius: 3px; min-height: 30px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QProgressBar { background: #E6EEE7; border: none; border-radius: 3px; height: 6px; max-height: 6px; }
QProgressBar::chunk { background: #2E865C; border-radius: 3px; }
QTableView { background: white; alternate-background-color: #F6F9F5; border: 1px solid #E0E8E1; border-radius: 8px; gridline-color: #EDF2EC; selection-background-color: #E3F0E5; selection-color: #1D5738; }
QTableView::item { padding: 8px; border: none; }
QHeaderView::section { background: #F2F6EF; border: none; border-bottom: 1px solid #E0E8E1; padding: 12px; color: #607868; font-weight: 600; }
QStatusBar { background: #F5F7F5; color: #71857A; border-top: 1px solid #E1E9E1; }
QToolTip { background: #163D30; color: white; border: none; padding: 8px; }
QSplitter::handle { background: transparent; width: 12px; }
"""

STYLE += """
QLabel#warning { color: #795210; background: #FFF5DA; border: 1px solid #E3CF9A; border-radius: 7px; padding: 8px; }
QLineEdit[invalid="true"], QDoubleSpinBox[invalid="true"] { border: 2px solid #AD3D3D; }
QCheckBox:focus { background: #E4EEE7; border-radius: 4px; }
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus { border: 2px solid #398460; }
"""


def style_for_scale(percent):
    import re
    factor = percent / 100
    return re.sub(r"font-size: (\d+)px", lambda match: f"font-size: {round(int(match[1]) * factor)}px", STYLE)
