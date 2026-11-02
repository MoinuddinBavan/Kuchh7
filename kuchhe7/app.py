from __future__ import annotations

import os
import sys

from PySide6.QtCore import QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from .platform_support import ui_font_family
from .ui.main_window import MainWindow


STYLE = """
QMainWindow, QWidget {
    background: #F7F9FB;
    color: #172A3C;
    font-family: 'Segoe UI';
    font-size: 9pt;
}
QMenuBar { background: #172A3C; color: #FFFFFF; padding: 3px 7px; spacing: 4px; }
QMenuBar::item { padding: 6px 10px; border-radius: 3px; }
QMenuBar::item:selected { background: #147D83; }
QMenu { background: #FFFFFF; color: #172A3C; border: 1px solid #BFCBD4; padding: 5px; }
QMenu::item { padding: 7px 28px 7px 22px; border-radius: 2px; }
QMenu::item:selected { background: #DCEFF0; color: #0E6267; }
QMenu::separator { height: 1px; background: #DDE4E9; margin: 4px 8px; }
QToolBar { background: #FFFFFF; border: none; border-bottom: 1px solid #C9D3DB; spacing: 3px; padding: 5px 8px; }
QToolBar::separator { width: 1px; background: #D7E0E6; margin: 5px 8px; }
QToolButton { color: #172A3C; padding: 5px 9px; min-width: 54px; border: 1px solid transparent; border-radius: 4px; }
QToolButton:hover { background: #E3F1F2; border-color: #B4D5D7; }
QToolButton:checked { background: #147D83; color: #FFFFFF; border-color: #0F686D; }
#ribbonGroupLabel { color: #71808C; font-size: 7pt; font-weight: 700; padding: 0 5px; }
QDockWidget { border: 1px solid #CDD7DE; titlebar-close-icon: none; titlebar-normal-icon: none; }
QDockWidget::title { background: #E9EFF3; color: #172A3C; font-size: 8pt; font-weight: 700; padding: 8px 10px; }
QGroupBox { background: #FFFFFF; border: 1px solid #D5DEE4; border-radius: 5px; margin-top: 11px; padding: 12px 8px 8px 8px; }
QGroupBox::title { subcontrol-origin: margin; left: 9px; color: #172A3C; font-weight: 700; padding: 0 5px; }
QLabel { background: transparent; }
QSpinBox, QComboBox, QLineEdit { background: #FFFFFF; border: 1px solid #B8C5CE; border-radius: 4px; padding: 5px 7px; min-height: 24px; selection-background-color: #147D83; }
QSpinBox:hover, QComboBox:hover, QLineEdit:hover { border-color: #77939F; }
QSpinBox:focus, QComboBox:focus, QLineEdit:focus { border: 1px solid #147D83; }
QTreeWidget, QTableWidget { background: #FFFFFF; border: none; alternate-background-color: #F3F7F9; selection-background-color: #D7ECEE; selection-color: #172A3C; }
QListWidget { background: #FFFFFF; border: 1px solid #D5DEE4; border-radius: 4px; alternate-background-color: #F7F9FB; }
QListWidget::item { padding: 4px 7px; border-bottom: 1px solid #E7ECEF; }
QListWidget::item:hover { background: #F2F6F7; }
QListWidget::item:selected { background: #DCEBED; color: #173C47; border: 1px solid #8DB3B6; font-weight: 600; }
QTabWidget::pane { border: none; background: #F7F9FB; }
QTabBar::tab { background: #E9EFF3; color: #526571; padding: 7px 13px; border: 1px solid #D5DEE4; }
QTabBar::tab:selected { background: #FFFFFF; color: #147D83; border-bottom-color: #FFFFFF; font-weight: 700; }
#workspaceTabs > QTabBar::tab { min-width: 150px; padding: 8px 18px; }
QPushButton { background: #FFFFFF; color: #172A3C; border: 1px solid #AEBCC6; border-radius: 4px; padding: 7px 10px; }
QPushButton:hover { border-color: #147D83; background: #EEF7F7; }
QPushButton#primaryButton { background: #147D83; color: #FFFFFF; border-color: #106A6F; font-weight: 700; }
QPushButton#primaryButton:disabled { background: #9BB8BA; border-color: #9BB8BA; }
QTreeWidget::item { min-height: 29px; padding: 2px 5px; border-bottom: 1px solid #F0F3F5; }
QTreeWidget::item:hover { background: #EDF5F6; }
QHeaderView::section { background: #172A3C; color: #FFFFFF; font-weight: 600; padding: 7px 8px; border: none; border-right: 1px solid #30465A; }
QTableWidget::item { padding: 5px 8px; border-bottom: 1px solid #E8EDF0; }
QScrollBar:vertical { background: #EDF1F4; width: 11px; margin: 0; }
QScrollBar:horizontal { background: #EDF1F4; height: 11px; margin: 0; }
QScrollBar::handle { background: #9AAAB5; border-radius: 5px; min-height: 28px; min-width: 28px; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
#canvasPanel { background: #FFFFFF; border: 1px solid #C9D4DC; border-radius: 5px; }
#canvasHeader { background: #FFFFFF; border-bottom: 1px solid #D9E1E6; }
#canvasTitle { color: #172A3C; font-size: 9pt; font-weight: 700; }
#canvasSubtitle { color: #6B7C88; font-size: 8pt; }
#canvasActionButton { min-width: 112px; padding: 5px 8px; background: #F7F9FB; border: 1px solid #C5D1D8; }
#canvasActionButton:hover { background: #E3F1F2; border-color: #147D83; }
#canvasActionButton:checked { background: #147D83; color: #FFFFFF; border-color: #0F686D; }
#workspaceSplitter::handle { background: #DCE4E9; }
#workspaceSplitter::handle:hover { background: #147D83; }
#propertiesScroll { background: #F7F9FB; }
QStatusBar { background: #172A3C; color: #FFFFFF; min-height: 25px; padding: 0 6px; }
QStatusBar::item { border: none; }
#statusContext { color: #DCE5EB; padding: 0 10px; }
#statusBadge { background: #147D83; color: #FFFFFF; font-size: 8pt; font-weight: 700; border-radius: 3px; padding: 3px 8px; margin: 2px 5px; }
#cabinetIdBadge { background: #147D83; color: #FFFFFF; font-weight: 700; border-radius: 3px; padding: 5px 9px; }
#placementWarning { color: #8A281F; background: #FCE8E6; border: 1px solid #E7B7B1; padding: 8px; border-radius: 4px; }
#warningLabel { color: #7B560D; background: #FFF4D8; border: 1px solid #E9D59B; padding: 8px; border-radius: 4px; }
#catalogueDetail { color: #526571; background: #FFFFFF; border: 1px solid #D5DEE4; border-radius: 4px; padding: 8px; }
#engineeringHeader { background: #FFFFFF; border: 1px solid #C9D4DC; border-radius: 5px; padding: 4px; }
#engineeringTitle { color: #172A3C; font-size: 12pt; font-weight: 700; }
#engineeringPanel { background: #FFFFFF; border: 1px solid #C9D4DC; border-radius: 5px; }
#sectionTitle { color: #172A3C; font-size: 8pt; font-weight: 700; padding: 2px 1px 5px 1px; }
#technicalDrawing, #drillingPreview { border: 1px solid #D5DEE4; background: #FFFFFF; }
#engineeringDisclaimer { color: #7B560D; background: #FFF4D8; border: 1px solid #E2C978; padding: 9px 12px; border-radius: 4px; font-weight: 700; }
#nestingHeader { background: #FFFFFF; border: 1px solid #C9D4DC; border-radius: 5px; padding: 4px; }
#nestingTitle { color: #172A3C; font-size: 12pt; font-weight: 700; }
#nestingPanel { background: #FFFFFF; border: 1px solid #C9D4DC; border-radius: 5px; }
#nestingSplitter::handle { background: #DCE4E9; width: 5px; }
#nestingSplitter::handle:hover { background: #147D83; }
#nestingSheetView { border: 1px solid #C9D4DC; background: #EEF2F4; }
#nestingSheetSummary { background: #EEF5F6; color: #274854; border: 1px solid #C9DCDD; border-radius: 4px; padding: 7px 9px; }
#nestingStatusBadge { background: #DCEFED; color: #0E6267; border-radius: 3px; padding: 6px 10px; font-weight: 700; }
#nestingStatusBadge[stale="true"] { background: #FFF0CF; color: #7B560D; }
#nestingCompletenessBadge { background: #DDEFE4; color: #28613C; border-radius: 3px; padding: 6px 10px; font-weight: 700; }
#nestingCompletenessBadge[incomplete="true"] { background: #FCE8E6; color: #8A281F; border: 1px solid #E7B7B1; }
#utilizationValue { color: #147D83; font-size: 13pt; font-weight: 700; }
#nestingDisclaimer { color: #7B560D; background: #FFF4D8; border: 1px solid #E2C978; padding: 9px 12px; border-radius: 4px; font-weight: 700; }
"""


def main() -> int:
    application = QApplication(sys.argv)
    application.setApplicationName("kuchhe7")
    application.setApplicationDisplayName("Küche7")
    application.setOrganizationName("AIZ INFOTECHS")
    application.setStyle("Fusion")
    font_family = ui_font_family()
    application.setFont(QFont(font_family, 9))
    application.setStyleSheet(STYLE.replace("'Segoe UI'", f"'{font_family}'"))
    window = MainWindow()
    window.show()
    release_smoke_directory = os.environ.get("KUCHHE7_RELEASE_SMOKE_DIR")
    if release_smoke_directory:
        from .release_smoke import run_release_smoke

        QTimer.singleShot(
            2400,
            lambda: run_release_smoke(window, application, release_smoke_directory),
        )
    auto_close = os.environ.get("KUCHHE7_AUTOCLOSE_MS")
    if auto_close and not release_smoke_directory:
        QTimer.singleShot(int(auto_close), application.quit)
    return application.exec()

