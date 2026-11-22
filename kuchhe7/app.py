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
    background: #F5F2EC;
    color: #293136;
    font-family: 'Segoe UI';
    font-size: 9pt;
}
QMenuBar { background: #22282B; color: #F5F2EC; padding: 2px 9px; spacing: 4px; }
QMenuBar::item { padding: 5px 10px; border-radius: 2px; }
QMenuBar::item:selected { background: #46504D; }
QMenu { background: #FFFFFF; color: #293136; border: 1px solid #D8D1C7; padding: 5px; }
QMenu::item { padding: 6px 28px 6px 20px; border-radius: 2px; }
QMenu::item:selected { background: #E9EEE9; color: #344B44; }
QMenu::separator { height: 1px; background: #E7E2D9; margin: 4px 8px; }
QToolBar { background: #F5F2EC; border: none; border-bottom: 1px solid #D9D2C8; spacing: 1px; padding: 2px 6px; }
QToolBar::separator { width: 1px; background: #CFC6BA; margin: 5px 5px; }
QToolButton { color: #293136; padding: 4px 7px; border: 1px solid transparent; border-radius: 3px; }
QToolButton:hover { background: #EDE9E0; border-color: #D8D0C5; }
QToolButton:checked { background: #E2EAE5; color: #3D5750; border-color: #B6C5BD; }
#mainRibbon QToolButton { background: transparent; color: #293136; font-size: 8pt; padding: 3px 5px; border: 1px solid transparent; border-radius: 3px; }
#mainRibbon QToolButton:hover { background: #ECE7DE; border-color: #D5CABD; }
#mainRibbon QToolButton:checked { background: #E2EAE5; color: #344B44; border-color: #B6C5BD; }
#mainRibbon QToolButton[primary="true"] { color: #34413D; background: #EAE1D4; border-color: #B49A77; font-weight: 700; }
QDockWidget { border: 0; titlebar-close-icon: none; titlebar-normal-icon: none; }
QDockWidget::title { background: #EEEAE3; color: #45504C; font-size: 8pt; font-weight: 700; padding: 7px 10px; }
QGroupBox { background: #FFFFFF; border: 1px solid #E2DCD2; border-radius: 5px; margin-top: 10px; padding: 8px 7px 7px 7px; }
QGroupBox::title { subcontrol-origin: margin; left: 9px; color: #48534F; font-weight: 700; padding: 0 5px; }
#selectedObjectGroup { border-top: 2px solid #B49A77; }
#inspectorObjectName { color: #293136; font-size: 10pt; font-weight: 700; }
#inspectorSection, #sidebarSectionTitle { color: #8A755C; font-size: 8pt; font-weight: 700; padding: 7px 2px 3px 2px; }
QLabel { background: transparent; }
QSpinBox, QComboBox, QLineEdit { background: #FFFFFF; border: 1px solid #CEC8BE; border-radius: 3px; padding: 4px 6px; min-height: 23px; selection-background-color: #60766F; }
QSpinBox:hover, QComboBox:hover, QLineEdit:hover { border-color: #A99F91; }
QSpinBox:focus, QComboBox:focus, QLineEdit:focus { border: 1px solid #60766F; }
QTreeWidget, QTableWidget { background: #FFFFFF; border: none; alternate-background-color: #FAF9F6; selection-background-color: #E7EDE8; selection-color: #293136; }
QTreeWidget::item:selected { background: #E7EDE8; color: #293136; border-left: 2px solid #60766F; }
QListWidget { background: #FFFFFF; border: 1px solid #E5E0D8; border-radius: 3px; alternate-background-color: #FBFAF7; }
QListWidget::item { padding: 5px 7px; margin: 2px 4px; border: 1px solid transparent; border-radius: 4px; }
QListWidget::item:hover { background: #F2F0EB; }
QListWidget::item:selected { background: #E8EEE9; color: #293136; border: 1px solid #A9B9AF; font-weight: 600; }
QTabWidget::pane { border: none; background: #F5F2EC; }
QTabBar::tab { background: #EEEAE3; color: #59635E; padding: 6px 10px; border: 1px solid #E2DCD2; }
QTabBar::tab:selected { background: #FFFFFF; color: #293136; border-bottom-color: #FFFFFF; border-top: 2px solid #B49A77; font-weight: 700; }
#workspaceTabs > QTabBar::tab { min-width: 0; padding: 7px 9px; font-size: 8pt; }
QPushButton { background: #FFFFFF; color: #293136; border: 1px solid #CEC8BE; border-radius: 3px; padding: 6px 9px; }
QPushButton:hover { border-color: #A99F91; background: #F5F2EC; }
QPushButton#primaryButton { background: #60766F; color: #FFFFFF; border-color: #52675F; font-weight: 700; }
QPushButton#primaryButton:disabled { background: #BBC5BF; border-color: #BBC5BF; }
QTreeWidget::item { min-height: 26px; padding: 2px 4px; border-bottom: 1px solid #F2F0EB; }
QTreeWidget::item:hover { background: #F1F3EF; }
QHeaderView::section { background: #3A4243; color: #FFFFFF; font-weight: 600; padding: 6px 8px; border: none; border-right: 1px solid #59615F; }
QTableWidget::item { padding: 4px 8px; border-bottom: 1px solid #EFEBE4; }
QScrollBar:vertical { background: #F1EEE8; width: 10px; margin: 0; }
QScrollBar:horizontal { background: #F1EEE8; height: 10px; margin: 0; }
QScrollBar::handle { background: #B9B4A9; border-radius: 5px; min-height: 28px; min-width: 28px; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
#canvasPanel { background: #FFFFFF; border: 1px solid #E4DED5; border-radius: 3px; }
#canvasHeader { background: #FBFAF7; border-bottom: 1px solid #E9E4DC; }
#canvasTitle { color: #293136; font-size: 9pt; font-weight: 700; }
#canvasSubtitle { color: #79817C; font-size: 8pt; }
#canvasActionButton { min-width: 100px; padding: 4px 7px; background: #FFFFFF; border: 1px solid #D8D1C7; }
#canvasActionButton:hover { background: #F0ECE5; border-color: #B49A77; }
#canvasActionButton:checked { background: #60766F; color: #FFFFFF; border-color: #52675F; }
#workspaceSplitter::handle { background: #E8E3DA; }
#workspaceSplitter::handle:hover { background: #B49A77; }
#propertiesScroll { background: #F5F2EC; }
#propertiesScroll QSpinBox, #propertiesScroll QComboBox { min-height: 20px; padding: 3px 5px; }
#bomDock QHeaderView::section { padding: 5px 8px; }
#bomDock QTableWidget::item { padding: 3px 7px; }
QStatusBar { background: #293136; color: #F5F2EC; min-height: 23px; padding: 0 6px; }
QStatusBar::item { border: none; }
#statusContext { color: #E3DED5; padding: 0 10px; }
#statusBadge { background: #60766F; color: #FFFFFF; font-size: 8pt; font-weight: 700; border-radius: 3px; padding: 3px 8px; margin: 2px 5px; }
#cabinetIdBadge { background: #60766F; color: #FFFFFF; font-weight: 700; border-radius: 3px; padding: 5px 9px; }
#placementWarning { color: #8A281F; background: #FCE8E6; border: 1px solid #E7B7B1; padding: 8px; border-radius: 4px; }
#warningLabel { color: #7B560D; background: #FFF4D8; border: 1px solid #E9D59B; padding: 8px; border-radius: 4px; }
#catalogueDetail { color: #5C6660; background: #FFFFFF; border: 1px solid #E2DCD2; border-radius: 4px; padding: 8px; }
#engineeringHeader { background: #FFFFFF; border: 1px solid #E2DCD2; border-radius: 5px; padding: 4px; }
#engineeringTitle { color: #293136; font-size: 12pt; font-weight: 700; }
#engineeringPanel { background: #FFFFFF; border: 1px solid #E2DCD2; border-radius: 5px; }
#sectionTitle { color: #293136; font-size: 8pt; font-weight: 700; padding: 2px 1px 5px 1px; }
#technicalDrawing, #drillingPreview { border: 1px solid #E2DCD2; background: #FFFFFF; }
#engineeringDisclaimer { color: #7B560D; background: #FFF4D8; border: 1px solid #E2C978; padding: 9px 12px; border-radius: 4px; font-weight: 700; }
#nestingHeader { background: #FFFFFF; border: 1px solid #E2DCD2; border-radius: 5px; padding: 4px; }
#nestingTitle { color: #293136; font-size: 12pt; font-weight: 700; }
#nestingPanel { background: #FFFFFF; border: 1px solid #E2DCD2; border-radius: 5px; }
#nestingSplitter::handle { background: #E8E3DA; width: 5px; }
#nestingSplitter::handle:hover { background: #B49A77; }
#nestingSheetView { border: 1px solid #E2DCD2; background: #F5F2EC; }
#nestingSheetSummary { background: #F1F3EE; color: #45564D; border: 1px solid #D5DED5; border-radius: 4px; padding: 7px 9px; }
#nestingStatusBadge { background: #E7EDE8; color: #405B50; border-radius: 3px; padding: 6px 10px; font-weight: 700; }
#nestingStatusBadge[stale="true"] { background: #FFF0CF; color: #7B560D; }
#nestingCompletenessBadge { background: #DDEFE4; color: #28613C; border-radius: 3px; padding: 6px 10px; font-weight: 700; }
#nestingCompletenessBadge[incomplete="true"] { background: #FCE8E6; color: #8A281F; border: 1px solid #E7B7B1; }
#utilizationValue { color: #60766F; font-size: 13pt; font-weight: 700; }
#nestingDisclaimer { color: #7B560D; background: #FFF4D8; border: 1px solid #E2C978; padding: 9px 12px; border-radius: 4px; font-weight: 700; }

/* Approved presentation-first Design Studio. Other workspaces retain their controls. */
#mainRibbon { background: #1F2825; border: none; padding: 0; spacing: 0; min-height: 66px; }
#premiumHeader { background: #1F2825; }
#brandBadge { background: #C2AA84; color: #1F2825; border-radius: 11px; font-size: 20pt; font-weight: 700; }
#brandTitle { color: #F7F5EF; font-size: 15pt; font-weight: 700; }
#brandCaption { color: #AEBBB2; font-size: 7pt; font-weight: 700; letter-spacing: 1px; }
#headerProjectTitle { color: #F7F5EF; font-size: 11pt; font-weight: 700; }
#headerProjectMeta { color: #B4C1B7; font-size: 8pt; }
#headerSaved { color: #B6CEBA; font-size: 9pt; padding-right: 8px; }
#mainRibbon #headerMenu, #mainRibbon #headerUtility, #mainRibbon #headerSave { color: #F6F7F2; background: #354139; border: none; border-radius: 8px; padding: 8px 13px; min-height: 23px; }
#mainRibbon #headerMenu:hover, #mainRibbon #headerUtility:hover, #mainRibbon #headerSave:hover { background: #46584C; }
#mainRibbon #headerUtility:disabled { color: #9BAAA0; background: #2C3831; }
#mainRibbon #headerExport { color: #222923; background: #C2AA84; border: none; border-radius: 8px; padding: 8px 17px; font-weight: 700; min-height: 23px; }
#mainRibbon #headerExport:hover { background: #D5BE98; }
#explorerContent, #projectSidebar, #sidebarHeading { background: #F9F9F6; }
#workspaceRail { background: #26312C; }
#railButton { background: transparent; border: none; border-radius: 9px; padding: 7px; }
#railButton:hover { background: #405147; }
#railButton[active="true"] { background: #566D61; }
#sidebarEyebrow { color: #78817C; font-size: 8pt; font-weight: 700; }
#sidebarProjectName { color: #232927; font-size: 11pt; font-weight: 700; }
#explorerTabs { background: #F9F9F6; }
#explorerTabs::pane { border: none; background: #F9F9F6; }
#explorerTabs QTabBar::tab { background: #ECEFEA; color: #6E7971; border: none; border-radius: 6px; margin: 2px; padding: 7px 9px; }
#explorerTabs QTabBar::tab:selected { background: #FFFFFF; color: #232927; border: none; font-weight: 700; }
#objectList { background: #F9F9F6; border: none; alternate-background-color: #F9F9F6; }
#objectList::item { background: transparent; color: #232927; border: 1px solid transparent; border-radius: 10px; margin: 2px 3px; padding: 5px 4px; }
#objectList::item:hover { background: #EFF2EC; }
#objectList::item:selected { background: #E6ECE5; color: #232927; border: 1px solid #BDCFC0; }
#objectSummary { color: #6D7770; font-size: 8pt; padding: 6px 4px; border-top: 1px solid #E2E6DF; }
#browseLibraryButton { background: #FFFFFF; border: 1px solid #D7DFD6; border-radius: 8px; color: #506B5A; font-weight: 700; min-height: 27px; }
#browseLibraryButton:hover { background: #E9F0E8; }
#designRoot { background: #F5F6F2; }
#designHeader { background: #F5F6F2; border-bottom: 1px solid #E2E5DE; min-height: 57px; }
#designTitle { color: #232927; font-size: 16pt; font-weight: 700; }
#designSubtitle { color: #78817C; font-size: 8pt; }
#designHeader QToolButton { background: #FFFFFF; border: 1px solid #DDE2DA; border-radius: 8px; color: #4A5B50; padding: 8px 12px; min-height: 20px; }
#designHeader QToolButton:hover { background: #EAF0E9; }
#designHeader QToolButton:checked { background: #E6ECE5; border-color: #B9CABC; color: #273E2E; font-weight: 700; }
#designStage { background: #E8EBE5; }
#floatingPlan { background: #FFFFFF; border: 1px solid #DEE5DC; border-radius: 11px; }
#floatingPlan #canvasHeader { background: #FFFFFF; border: none; border-bottom: 1px solid #E7EBE5; min-height: 30px; }
#floatingPlan #canvasTitle { color: #232927; font-size: 8pt; font-weight: 700; }
#planExpandButton { background: transparent; color: #56755E; border: none; font-size: 8pt; font-weight: 700; padding: 3px 5px; }
#live3dBadge { color: #F8FAF5; background: #27362C; border-radius: 8px; padding: 8px 13px; font-size: 8pt; font-weight: 700; }
#viewportControls { background: #F9FAF7; border: 1px solid #E0E6DD; border-radius: 8px; }
#viewportControls QToolButton { background: transparent; border: none; color: #29352D; padding: 6px 8px; font-size: 8pt; }
#viewportControls QToolButton:hover { background: #E8EEE7; }
#viewportSelection { background: #F9FAF7; border: 1px solid #DCE2D8; border-radius: 10px; }
#viewportSelectionTitle { color: #232927; font-size: 10pt; font-weight: 700; }
#viewportSelectionDetail { color: #69746C; font-size: 8pt; }
#propertiesScroll { background: #FBFBF9; }
#inspectorEyebrow { color: #78817C; font-size: 8pt; font-weight: 700; }
#inspectorTitle { color: #232927; font-size: 13pt; font-weight: 700; }
#inspectorSubtitle { color: #78817C; font-size: 8pt; }
#selectedObjectGroup { background: transparent; border: none; margin: 0; padding: 0; }
#inspectorIdentity { background: #F0F2ED; border: none; border-radius: 10px; }
#inspectorThumbnail { background: #E9E8DF; border-radius: 7px; }
#inspectorIdentity #cabinetIdBadge { background: #DDE8DE; color: #466351; border-radius: 13px; padding: 6px 9px; }
#inspectorCard { background: transparent; border: none; padding: 0; }
#inspectorSection { color: #77817B; font-size: 8pt; font-weight: 700; padding: 8px 0 1px 0; }
#inspectorFieldLabel { color: #6F7A73; font-size: 8pt; font-weight: 700; }
#propertiesScroll QSpinBox, #propertiesScroll QComboBox { background: #FFFFFF; color: #232927; border: 1px solid #DCE2DA; border-radius: 8px; min-height: 26px; padding: 5px 7px; }
#propertiesScroll QSpinBox:focus, #propertiesScroll QComboBox:focus { border-color: #60796C; }

/* Version 3 architectural presentation. The live Qt/VTK widgets remain in place. */
QMainWindow, QWidget { background: #F8F4EF; color: #272B27; }
QMenu { background: #FFFCF8; border: 1px solid #DDD3C8; border-radius: 8px; }
QMenu::item:selected { background: #EAE9DC; color: #42583A; }
#mainRibbon { background: #F9F2EF; border-bottom: 1px solid #E9E1DC; min-height: 65px; }
#premiumHeader { background: #F9F2EF; }
#brandBadge { background: transparent; border: none; }
#brandTitle { color: #191C1B; font-size: 20pt; font-weight: 700; letter-spacing: 2px; }
#brandCaption { color: #494139; font-size: 6pt; font-weight: 700; letter-spacing: 0.3px; }
#headerBrandDivider, #headerStatusDivider { background: #C8BDB4; border: none; }
#headerProjectTitle { color: #202220; font-size: 13pt; font-weight: 700; }
#headerProjectMeta { color: #373A35; font-size: 9.5pt; }
#headerSaved, #headerSavedIcon { background: transparent; color: #446449; font-size: 9pt; }
#headerSaved[dirty="true"] { color: #9A6237; }
#mainRibbon #headerMenu { background: #FDF9F6; border: 1px solid #E9DFD8; border-radius: 18px; padding: 6px; }
#mainRibbon #headerMenu:hover { background: #EEE6DD; }
#headerHistory { background: #FDF9F6; border: 1px solid #EAE1DA; border-radius: 13px; }
#mainRibbon QToolButton#headerUtility { color: #252A27; background: transparent; border: none; border-radius: 8px; padding: 4px; }
#mainRibbon QToolButton#headerUtility:hover { background: #E9E3DA; }
#mainRibbon QToolButton#headerUtility:disabled { color: #999F98; background: transparent; border: none; }
#mainRibbon #headerSave { color: #252A27; background: #FFFFFF; border: 1px solid #E5DCD3; border-radius: 12px; padding: 6px 10px; font-weight: 700; }
#mainRibbon #headerSave:hover { background: #F4EFE8; }
#mainRibbon #headerSave:pressed { background: #EDE5DB; }
#mainRibbon #headerExport { color: #FFFFFF; background: transparent; border: none; padding: 0; }
#workspaceRail { background: #F3EEE6; border-right: 1px solid #E4DCCF; }
#railButton { color: #383A34; background: transparent; border: 1px solid transparent; border-radius: 12px; padding: 4px 2px; font-size: 7.5pt; }
#railButton:hover { background: #E5E7DB; color: #34452E; }
#railButton[active="true"] { background: #526B46; color: #FFFFFF; border: 1px solid #465D3C; font-weight: 700; }
#explorerContent, #projectSidebar, #sidebarHeading { background: #FCFAF7; }
#projectSidebar { border-right: 1px solid #E9E1D8; }
#sidebarEyebrow { color: #8B7766; font-size: 8pt; font-weight: 700; }
#sidebarProjectName { color: #262923; font-size: 10pt; font-weight: 700; }
#sidebarSectionTitle { color: #242721; font-size: 10pt; font-weight: 700; padding: 3px 3px; }
#explorerTabs, #explorerTabs::pane { background: #FCFAF7; border: none; }
#explorerTabs QTabBar::tab { background: transparent; color: #5D615B; border: none; border-bottom: 2px solid transparent; border-radius: 0; padding: 7px 8px; margin: 0; }
#explorerTabs QTabBar::tab:selected { color: #9A592B; background: transparent; border-bottom: 2px solid #A76637; font-weight: 700; }
#objectList { background: #FCFAF7; border: none; alternate-background-color: #FCFAF7; }
#objectList::item { background: #FFFFFF; color: #282B27; border: 1px solid #ECE6DD; border-radius: 10px; margin: 2px 2px; padding: 4px; }
#objectList::item:hover { background: #F7F1E9; border-color: #D8C5AE; }
#objectList::item:selected { background: #FFF8EF; color: #272A24; border: 1px solid #A86935; font-weight: 700; }
#objectSummary { color: #756E65; font-size: 8pt; padding: 5px 3px; border-top: 1px solid #E8E1D8; }
#browseLibraryButton { color: #FFFFFF; background: #A86631; border: 1px solid #9C5A27; border-radius: 9px; min-height: 29px; font-weight: 700; }
#browseLibraryButton:hover { background: #8F542A; }
#workspaceRail { background: #F5F0E9; border-right: 1px solid #E7DED3; }
#railButton { color: #343A34; background: transparent; border: 1px solid transparent; border-radius: 13px; padding: 3px 2px; font-size: 8pt; }
#railButton[compactLabel="true"] { font-size: 7pt; }
#railButton:hover { background: #E9E8DF; color: #334531; }
#railButton[active="true"] { color: #FFFFFF; background: #526B46; border: 1px solid #465D3C; border-radius: 13px; font-weight: 700; }
#railFooterButton { color: #373B35; background: transparent; border: none; border-radius: 9px; padding: 2px; font-size: 7.5pt; }
#railFooterButton:hover { background: #E8E6DC; }
#explorerContent, #projectSidebar, #sidebarHeading { background: #FFFCF8; }
#projectSidebar { border-right: 1px solid #E8DED3; }
#sidebarHeading { border-bottom: 1px solid #EEE4DA; }
#sidebarEyebrow { color: #685B4E; font-size: 7.5pt; font-weight: 700; }
#sidebarProjectName { color: #252924; font-size: 9pt; font-weight: 700; }
#sidebarProjectMenu { color: #3F443A; background: transparent; border: none; padding: 2px 5px; font-size: 12pt; }
#sidebarProjectMenu:hover { background: #F0EAE2; border-radius: 5px; }
#sidebarSectionTitle { color: #222720; font-size: 10pt; font-weight: 700; padding: 0; }
#sidebarCollapseButton { color: #353C33; background: transparent; border: none; padding: 2px 5px; font-size: 12pt; }
#sidebarCollapseButton:hover { background: #F0EAE2; border-radius: 5px; }
#explorerTabs, #explorerTabs::pane { background: #FFFCF8; border: none; }
#explorerTabs QTabBar::tab { color: #42433C; background: transparent; border: none; border-bottom: 2px solid transparent; border-radius: 0; margin: 0; padding: 10px 7px; font-size: 8pt; }
#explorerTabs QTabBar::tab:hover { color: #8D572F; background: #F8F1E9; }
#explorerTabs QTabBar::tab:selected { color: #96572E; background: transparent; border-bottom: 2px solid #A76637; font-weight: 700; }
#objectList { background: #FFFCF8; border: none; alternate-background-color: #FFFCF8; }
#objectList::item, #objectList::item:selected, #objectList::item:hover { background: transparent; border: none; margin: 0; padding: 0; }
#browseLibraryButton { color: #FFFFFF; background: #A76637; border: 1px solid #995D31; border-radius: 9px; min-height: 34px; font-weight: 700; font-size: 8.5pt; }
#browseLibraryButton:hover { background: #90552D; }
#designRoot { background: #F8F4EF; }
#designHeader { background: #F8F2EE; border-bottom: 1px solid #EBE2D7; min-height: 68px; }
#designTitle { color: #40583A; font-size: 17pt; font-weight: 700; }
#designTitleUnderline { background: #A76637; border: none; border-radius: 1px; }
#designHeader QToolButton { background: #FFFCF9; color: #2F332D; border: 1px solid #EEE5DD; border-radius: 20px; padding: 7px 13px; min-height: 22px; font-weight: 700; }
#designHeader QToolButton:hover { background: #F2ECE3; }
#designHeader QToolButton:checked { background: #526543; color: #FFFFFF; border-color: #526543; }
#designHeader #presentationModeButton:checked { background: #FFFCF9; color: #8F542A; border-color: #CDA57F; }
#designTools { background: #FAF4F0; border-bottom: 1px solid #E8DED4; min-height: 73px; }
#designToolButton { background: transparent; color: #343731; border: none; border-radius: 9px; padding: 5px 7px; font-size: 8pt; }
#designToolButton:hover { background: #EEE9E0; }
#designToolButton[primary="true"] { background: #FBE5CB; color: #8A502B; }
#designToolButton:checked { color: #40583A; background: transparent; border-bottom: 2px solid #A76637; }
#designToolsSeparator { background: #D8D0C6; border: none; max-width: 1px; min-width: 1px; margin: 12px 4px; }
#designStage { background: #E7DDD1; }
#floatingPlan { background: #FFFCF8; border: 1px solid #E0D3C5; border-radius: 16px; }
#floatingPlan #canvasHeader { background: #FFFCF8; border: none; min-height: 40px; }
#floatingPlan #canvasTitle { color: #252A25; font-size: 9pt; font-weight: 700; }
#floatingPlan #planRoomDimensions { color: #8B7868; font-size: 8pt; font-weight: 600; }
#planExpandButton { color: #865331; background: transparent; border: none; border-radius: 8px; font-size: 8pt; font-weight: 700; padding: 5px 6px; }
#planExpandButton:hover { background: #F2E7DA; }
#live3dBadge { color: #4E653E; background: #FFFDF8; border: 1px solid #E6DFD3; border-radius: 8px; padding: 6px 10px; font-weight: 700; }
#viewportControls { background: #FFFCF8; border: 1px solid #DED3C5; border-radius: 23px; }
#viewportControls QToolButton { color: #403D37; background: transparent; border: none; border-radius: 16px; min-width: 46px; min-height: 39px; padding: 3px 6px; font-size: 8pt; font-weight: 600; }
#viewportControls QToolButton:hover { background: #F0E8DE; }
#viewportControls QToolButton:pressed { background: #E7D7C5; }
#viewportControls QToolButton:disabled { color: #AAA39A; background: transparent; }
#viewportControls #viewportInteriorButton:checked { color: #FFFFFF; background: #526C47; border-radius: 16px; }
#viewportSelection { background: #FFFCF8; border: 1px solid #E1D8CA; border-radius: 10px; }
#viewportSelectionTitle { color: #2D342C; font-size: 9pt; font-weight: 700; }
#viewportSelectionDetail { color: #6B6D62; font-size: 8pt; }
#propertiesScroll { background: #F8F4EF; border-left: 1px solid #E9E1D8; }
#propertiesScroll QWidget { background: transparent; }
#propertiesScroll QLabel { background: transparent; }
#inspectorEyebrow { color: #2A2C29; font-size: 10pt; font-weight: 700; }
#inspectorTitle { color: #252A23; font-size: 10pt; font-weight: 700; }
#inspectorSubtitle { color: #776D63; font-size: 8pt; }
#selectedObjectGroup { background: transparent; border: none; margin: 0; padding: 0; }
#propertiesScroll #inspectorIdentity { background: #FFFFFF; border: 1px solid #E7DED5; border-radius: 12px; }
#propertiesScroll #inspectorThumbnail { background: #EDE4DA; border-radius: 8px; }
#inspectorIdentity #cabinetIdBadge { background: #E3EBD9; color: #465F3C; border-radius: 12px; padding: 5px 6px; font-size: 8pt; }
#inspectorIdentity #inspectorObjectName { color: #252924; font-size: 9pt; font-weight: 700; }
#inspectorTabs { background: transparent; border-bottom: 1px solid #E5D7C8; }
#inspectorTab { background: transparent; color: #685F55; border: none; border-bottom: 2px solid transparent; border-radius: 0; padding: 7px 2px; font-size: 8pt; }
#inspectorTab:hover { color: #A15F31; background: #F7F1EA; }
#inspectorTab[current="true"] { color: #9C5D30; border-bottom: 2px solid #A76637; font-weight: 700; }
#propertiesScroll #inspectorCard, #propertiesScroll #inspectorFormCard { background: #FFFFFF; border: 1px solid #E7DED5; border-radius: 12px; }
#inspectorFormCard { margin-top: 10px; padding: 11px 8px 8px 8px; }
#inspectorFormCard::title { color: #89562D; left: 12px; padding: 0 4px; }
#inspectorSection { color: #89562D; font-size: 9pt; font-weight: 700; padding: 1px 0 3px 0; }
#inspectorFieldLabel { color: #504F49; font-size: 8pt; font-weight: 600; }
#propertiesScroll QSpinBox, #propertiesScroll QComboBox { background: #FFFCFA; color: #252A23; border: 1px solid #DED6CD; border-radius: 8px; min-height: 26px; padding: 4px 5px; }
#propertiesScroll QSpinBox:hover, #propertiesScroll QComboBox:hover { border-color: #B99470; }
#propertiesScroll QSpinBox:focus, #propertiesScroll QComboBox:focus { border: 1px solid #A66B3F; background: #FFFFFF; }
#propertiesScroll QSpinBox:disabled, #propertiesScroll QComboBox:disabled { color: #9C968E; background: #F3F0EC; }
#propertiesScroll QSpinBox::up-button, #propertiesScroll QSpinBox::down-button { width: 15px; background: #F6F1EB; border: none; border-left: 1px solid #E4DAD0; }
#propertiesScroll QSpinBox::up-button { subcontrol-origin: border; subcontrol-position: top right; border-top-right-radius: 7px; }
#propertiesScroll QSpinBox::down-button { subcontrol-origin: border; subcontrol-position: bottom right; border-bottom-right-radius: 7px; border-top: 1px solid #E4DAD0; }
#propertiesScroll QPushButton { background: #FFFFFF; color: #70462C; border: 1px solid #DDCFC0; border-radius: 8px; padding: 7px 9px; }
#propertiesScroll QPushButton:hover { background: #F5EDE4; border-color: #B5835B; }
#propertiesScroll QPushButton:disabled { color: #AAA39A; background: #F1EFEC; }
QStatusBar { background: #FBF8F4; color: #4F514A; border-top: 1px solid #E8DDD0; min-height: 21px; }
#statusContext { color: #4F514A; }
#statusBadge { background: #EDE7DD; color: #555345; border-radius: 4px; }
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
    application.aboutToQuit.connect(window.close_3d_views)
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

