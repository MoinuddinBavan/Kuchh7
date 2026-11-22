from __future__ import annotations

from copy import deepcopy
import json
from itertools import chain
from pathlib import Path

from PySide6.QtCore import QEvent, QSize, Qt
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QKeySequence, QPainter, QPen, QUndoStack
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QAbstractItemView,
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDockWidget,
    QFileDialog,
    QFrame,
    QFormLayout,
    QGraphicsDropShadowEffect,
    QGridLayout,
    QGroupBox,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QScrollArea,
    QSizePolicy,
    QPushButton,
    QSpinBox,
    QStyleOptionSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QToolBar,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
    QStyle,
)

from ..bom import generate_project_bom
from ..ai_design import (DesignProposal, LocalRuleBasedProvider, build_proposal,
                         configured_provider, project_fingerprint)
from ..catalogue import CATEGORIES, FURNITURE_FAMILIES, catalogue_items, create_catalogue_cabinet, furniture_items, get_catalogue_item, register_custom_items, unregister_custom_item
from ..custom_catalogue import load_custom_catalogue, save_custom_catalogue
from ..exports import export_bom_xlsx, export_front_elevation_dxf
from ..engineering_dxf import CNC_PROTOTYPE, DRAWING_LABELS, export_engineering_dxf
from ..complete_kitchen_dxf import export_complete_kitchen_dxf
from ..cut_list import export_cut_list_xlsx
from ..construction import ConstructionProfile, DEMO_STATUS, synthetic_profile_for
from ..models import MATERIALS, MAX_CABINETS, PROJECT_TYPES, HardwareAssignment, Opening, PlacedProduct, Project
from ..product_libraries import APPEARANCE_COLOURS, APPLIANCES, FURNITURE, HARDWARE, LIBRARIES, PROPS, get_product, products_for
from ..openings import DOOR_SWINGS, WALL_IDS, WALL_LABELS, wall_length
from ..persistence import load_project, save_project
from ..pricing_setup import (apply_company_setup_to_new_project,
                             load_company_price_setup, save_company_price_setup)
from ..pricing_refresh import apply_company_price_refresh, preview_company_price_refresh
from ..price_master import validate_company_price_setup
from ..rendering import capture_view_png, project_render_context
from ..platform_support import is_macos, platform_shortcut
from .cad_views import Cabinet3DView, FINISH_COLOURS, RoomPlanView
from .design_stage import DesignStage
from .ai_design_workspace import AIDesignWorkspace
from .catalogue_preview import catalogue_thumbnail, product_thumbnail
from .cabinet_library_dialog import CabinetLibraryDialog
from .documents_workspace import DocumentsWorkspace
from .pricing_workspace import PricingWorkspace
from .pricing_refresh_dialog import PricingRefreshDialog
from .premium_icons import brand_mark, outline_icon
from .top_svg_icons import AnchoredExportMenu, PremiumExportButton, top_icon, top_label_pixmap
from .engineering_export_dialog import EngineeringExportDialog
from .history import AddCabinetCommand, ApplyDesignProposalCommand, HardwareAssignmentCommand, MoveCabinetCommand, OpeningChangeCommand, ProductChangeCommand, RemoveCabinetCommand
from .manufacturing_preview import ManufacturingPreviewWidget
from .realistic_render_workspace import RealisticRenderWorkspace
from .sheet_nesting import SheetNestingWidget
from .sidebar_cards import (DETAIL_ROLE, EXPANDED_ROLE, KIND_ROLE, NAME_ROLE,
                            PREVIEW_ROLE, TALL_ROLE, SidebarCardDelegate,
                            appliance_card_preview, cached_cabinet_preview)


class InspectorSpinBox(QSpinBox):
    """Keep native spin interaction while drawing legible step symbols."""

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        option = QStyleOptionSpinBox()
        self.initStyleOption(option)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor("#806A58" if self.isEnabled() else "#B9B3AB"), 1.4))
        for sub_control, plus in ((QStyle.SubControl.SC_SpinBoxUp, True),
                                  (QStyle.SubControl.SC_SpinBoxDown, False)):
            bounds = self.style().subControlRect(QStyle.ComplexControl.CC_SpinBox,
                                                 option, sub_control, self)
            center = bounds.center()
            if bounds.width() < 6 or bounds.height() < 6:
                continue
            painter.drawLine(center.x() - 3, center.y(), center.x() + 3, center.y())
            if plus:
                painter.drawLine(center.x(), center.y() - 3, center.x(), center.y() + 3)
        painter.end()


class NewProjectDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("New Project")
        layout = QFormLayout(self)
        self.name_edit = QLineEdit("Client Demo Kitchen")
        self.type_combo = QComboBox()
        self.type_combo.addItems(PROJECT_TYPES)
        layout.addRow("Project name", self.name_edit)
        layout.addRow("Project type", self.type_combo)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)


class CompanyPriceSetupDialog(QDialog):
    """Edit the local company master before design; saving never reprices open projects."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Company Price Setup")
        self.resize(1120, 850)
        self.project = Project.empty(name="Company price setup")
        self.project.price_master = load_company_price_setup()
        layout = QVBoxLayout(self)
        note = QLabel("Configure rates and catalogue selling rules before design. Existing projects keep their saved pricing snapshots. No prices are supplied by KÜCHE7.")
        note.setWordWrap(True)
        layout.addWidget(note)
        self.workspace = PricingWorkspace(lambda: None, context_name="company setup")
        self.workspace.set_project(self.project)
        layout.addWidget(self.workspace.master_page)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.save_setup)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def save_setup(self) -> None:
        try:
            save_company_price_setup(self.project.price_master)
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, "Company Price Setup", str(error))
            return
        self.accept()


class MainWindow(QMainWindow):
    def close_3d_views(self) -> None:
        """Finalize both VTK widgets while their Qt surfaces are still alive."""
        if hasattr(self, "manufacturing_preview"):
            self.manufacturing_preview.exploded_view.close_plotter()
        if hasattr(self, "view3d"):
            self.view3d.close_plotter()

    def closeEvent(self, event) -> None:  # noqa: N802
        if hasattr(self, "realistic_render_workspace") and self.realistic_render_workspace.render_in_progress:
            event.ignore()
            self.statusBar().showMessage("Rendering request is still running. Close the application after it finishes.")
            return
        self.close_3d_views()
        super().closeEvent(event)

    def __init__(self, *, start_empty: bool = True) -> None:
        super().__init__()
        try:
            self.custom_library_items = load_custom_catalogue()
            self.custom_library_error = ""
        except (OSError, ValueError, TypeError) as error:
            self.custom_library_items = []
            self.custom_library_error = str(error)
        self.project = Project.empty() if start_empty else Project()
        self.project_path: Path | None = None
        self.selected_product_id: str | None = None
        self.selected_hardware_assignment_id: str | None = None
        self.pending_design_proposal: DesignProposal | None = None
        self._dirty = False
        self._updating_controls = False
        self._updating_opening_controls = False
        self._workspace_3d_maximized = False
        self._rail_material_active = False
        self._workspace_restore_sizes = [620, 720]
        self._workspace_restore_docks: dict[QDockWidget, bool] = {}
        self._engineering_restore_docks: dict[QDockWidget, bool] = {}
        self.selected_wall_id = "WEST"
        self._inspector_context = "cabinet"
        self.undo_stack = QUndoStack(self)
        self.setWindowTitle("kuchhe7 — Kitchen Design & Manufacturing Platform | AIZ INFOTECHS")
        self.resize(1540, 920)
        self.setMinimumSize(1100, 700)
        self.setDockNestingEnabled(True)
        self.setAnimated(True)
        self._build_actions()
        self._build_menu()
        self._build_toolbar()
        self._build_central_views()
        self._build_explorer()
        self._build_properties()
        self._build_bom()
        self.bom_preview_action = self.bom_dock.toggleViewAction()
        self.bom_preview_action.setText("BOM Preview")
        self.bom_preview_action.setShortcut("Ctrl+Shift+B")
        self.view_menu.addSeparator()
        self.view_menu.addAction(self.bom_preview_action)
        self._build_status_bar()
        self.resizeDocks([self.explorer_dock, self.properties_dock], [378, 318], Qt.Orientation.Horizontal)
        self.resizeDocks([self.bom_dock], [140], Qt.Orientation.Vertical)
        self.statusBar().showMessage("Ready — demonstration construction rules are not factory approved")
        if self.custom_library_error:
            self.statusBar().showMessage(f"Custom cabinet library could not be read: {self.custom_library_error}")
            self.library_create_button.setEnabled(False)
            self.library_edit_button.setEnabled(False)
        self.refresh_all(reset_camera=True)
        self.bom_dock.hide()

    def _build_actions(self) -> None:
        self.new_action = QAction("New Project", self, triggered=self.new_project)
        self.new_action.setShortcuts(QKeySequence.keyBindings(QKeySequence.StandardKey.New))
        self.open_action = QAction("Open Project…", self, triggered=self.open_project)
        self.open_action.setShortcuts(QKeySequence.keyBindings(QKeySequence.StandardKey.Open))
        self.save_action = QAction("Save Project", self, triggered=self.save_project)
        self.save_action.setShortcuts(QKeySequence.keyBindings(QKeySequence.StandardKey.Save))
        self.save_as_action = QAction("Save Project As…", self, triggered=lambda: self.save_project(save_as=True))
        self.load_sample_action = QAction("Load Sample Kitchen", self, triggered=self.load_sample_kitchen)
        self.load_complete_action = QAction(
            "Load Complete Kitchen Demo", self, triggered=self.load_complete_kitchen_demo
        )
        self.ai_design_action = QAction("Design Assistant…", self, triggered=self.show_ai_design)
        self.add_cabinet_action = QAction("Place Selected", self, triggered=self.begin_catalogue_placement)
        self.remove_cabinet_action = QAction("Remove Selected", self, triggered=self.remove_selected_object)
        self.delete_cabinet_action = QAction("Delete selected object", self, triggered=self.remove_selected_object)
        self.duplicate_action = QAction("Duplicate Selected", self, triggered=self.duplicate_selected_object)
        self.duplicate_action.setShortcut(platform_shortcut("Ctrl+D"))
        self.select_wall_action = QAction("Select Wall", self, triggered=self.begin_wall_selection)
        self.add_door_action = QAction("Add Door", self, triggered=lambda: self.begin_opening_placement("door"))
        self.add_window_action = QAction("Add Window", self, triggered=lambda: self.begin_opening_placement("window"))
        self.edit_opening_action = QAction("Edit Opening", self, triggered=self.focus_opening_properties)
        self.remove_opening_action = QAction("Remove Opening", self, triggered=self.remove_selected_opening)
        self.undo_action = self.undo_stack.createUndoAction(self, "Undo")
        self.undo_action.setShortcuts(QKeySequence.keyBindings(QKeySequence.StandardKey.Undo))
        self.redo_action = self.undo_stack.createRedoAction(self, "Redo")
        self.redo_action.setShortcuts(QKeySequence.keyBindings(QKeySequence.StandardKey.Redo))
        self.snap_action = QAction("Snap", self)
        self.snap_action.setCheckable(True)
        self.snap_action.setChecked(True)
        self.snap_action.setToolTip("Snap placement to walls, cabinet edges and enabled grid")
        self.snap_action.toggled.connect(self._update_snap_options)
        self.grid_snap_action = QAction("Grid 100 mm", self)
        self.grid_snap_action.setCheckable(True)
        self.grid_snap_action.setChecked(True)
        self.grid_snap_action.toggled.connect(self._update_snap_options)
        self.exit_action = QAction("Quit" if is_macos() else "Exit", self, triggered=self.close)
        self.exit_action.setShortcuts(QKeySequence.keyBindings(QKeySequence.StandardKey.Quit))
        self.export_xlsx_action = QAction("Export BOM (XLSX)…", self, triggered=self.export_xlsx)
        self.export_cut_list_action = QAction(
            "Export Demonstration Cut List (XLSX)…", self, triggered=self.export_cut_list
        )
        self.export_dxf_action = QAction("Export Elevation (DXF)…", self, triggered=self.export_dxf)
        self.export_dxf_action.setToolTip(
            "Export demonstration cabinet front elevations — not nesting or machine cutting instructions"
        )
        self.engineering_export_action = QAction(
            "Engineering Drawing Export…", self, triggered=self.export_engineering_drawing
        )
        self.engineering_export_action.setToolTip(
            "Choose room plan, kitchen layout, elevations, panel outlines or generic CNC-targeted DXF prototype"
        )
        self.complete_kitchen_export_action = QAction(
            "Export Complete Kitchen (DXF)…", self, triggered=self.export_complete_kitchen_drawing
        )
        self.complete_kitchen_export_action.setToolTip(
            "Export one drawing with plan, wall elevations, BOM schedules and panel contours; machine compatibility unverified"
        )
        self.manufacturing_preview_action = QAction(
            "Manufacturing Preview", self, shortcut=platform_shortcut("Ctrl+Shift+M"),
            triggered=self.show_manufacturing_preview,
        )
        self.manufacturing_preview_action.setToolTip(
            "Open the selected-cabinet exploded assembly and component preview"
        )
        self.demo_construction_action = QAction(
            "Apply Synthetic Construction Profile to Selected Cabinet…", self,
            triggered=self.apply_synthetic_construction_profile,
        )
        self.import_construction_action = QAction(
            "Import Construction Profile JSON for Selected Cabinet…", self,
            triggered=self.import_construction_profile,
        )
        self.legacy_construction_action = QAction(
            "Restore Legacy Demo Rules for Selected Cabinet…", self,
            triggered=self.restore_legacy_construction_profile,
        )
        self.sheet_nesting_action = QAction(
            "Sheet Nesting", self, shortcut=platform_shortcut("Ctrl+Shift+N"), triggered=self.show_sheet_nesting
        )
        self.sheet_nesting_action.setToolTip(
            "Open the BOM-driven demonstration sheet nesting workspace"
        )
        self.documents_action = QAction("BOM & Quotation", self, triggered=self.show_documents)
        self.price_setup_action = QAction("Company Price Setup…", self, triggered=self.show_company_price_setup)
        self.price_refresh_action = QAction("Review Company Price Refresh…", self, triggered=self.refresh_company_prices)
        self.realistic_render_action = QAction("Realistic Rendering", self, triggered=self.show_realistic_rendering)
        self.front_view_action = QAction("Front", self, triggered=lambda: self.view3d.view_front())
        self.isometric_view_action = QAction("Isometric", self, triggered=lambda: self.view3d.view_isometric())
        self.fit_all_action = QAction("Fit All Cabinets", self, shortcut="F", triggered=lambda: self.view3d.fit_all_cabinets())
        self.reset_3d_action = QAction("Reset View", self, triggered=lambda: self.view3d.reset_view())
        self.maximize_3d_action = QAction(
            "Maximize 3D", self, shortcut=platform_shortcut("Ctrl+Shift+3")
        )
        self.maximize_3d_action.setCheckable(True)
        self.maximize_3d_action.setToolTip("Maximize the 3D viewport or restore the split workspace")
        self.maximize_3d_action.toggled.connect(self._set_3d_maximized)
        self.presentation_view_action = QAction("Presentation View", self)
        self.presentation_view_action.setCheckable(True)
        self.presentation_view_action.setToolTip("Toggle the furnished room presentation environment")
        self.presentation_view_action.toggled.connect(self._set_presentation_view)
        self.presentation_camera_action = QAction("Presentation Camera", self, triggered=lambda: self.view3d.view_presentation())
        self.presentation_camera_action.setEnabled(False)
        self.hide_room_walls_action = QAction("Hide Room Walls", self)
        self.hide_room_walls_action.setCheckable(True)
        self.hide_room_walls_action.setEnabled(False)
        self.hide_room_walls_action.toggled.connect(lambda hidden: self.view3d.set_room_walls_visible(not hidden))
        self.show_interior_action = QAction("Show Interior", self)
        self.show_interior_action.setCheckable(True)
        self.show_interior_action.setToolTip("Hide the doors and handles to inspect internal shelves")
        self.show_interior_action.toggled.connect(lambda checked: self.view3d.set_doors_visible(not checked))
        self.about_action = QAction("About", self, triggered=self.show_about)

        icons = self.style().standardIcon
        self.new_action.setIcon(icons(QStyle.StandardPixmap.SP_FileIcon))
        self.open_action.setIcon(icons(QStyle.StandardPixmap.SP_DialogOpenButton))
        self.save_action.setIcon(icons(QStyle.StandardPixmap.SP_DialogSaveButton))
        self.load_sample_action.setIcon(icons(QStyle.StandardPixmap.SP_DirHomeIcon))
        self.load_complete_action.setIcon(icons(QStyle.StandardPixmap.SP_DirHomeIcon))
        self.add_cabinet_action.setIcon(icons(QStyle.StandardPixmap.SP_FileDialogNewFolder))
        self.remove_cabinet_action.setIcon(icons(QStyle.StandardPixmap.SP_TrashIcon))
        self.export_xlsx_action.setIcon(icons(QStyle.StandardPixmap.SP_DialogApplyButton))
        self.export_dxf_action.setIcon(icons(QStyle.StandardPixmap.SP_ArrowDown))
        self.manufacturing_preview_action.setIcon(icons(QStyle.StandardPixmap.SP_FileDialogDetailedView))
        self.sheet_nesting_action.setIcon(icons(QStyle.StandardPixmap.SP_FileDialogListView))
        self.reset_3d_action.setIcon(icons(QStyle.StandardPixmap.SP_BrowserReload))
        self.maximize_3d_action.setIcon(icons(QStyle.StandardPixmap.SP_TitleBarMaxButton))
        self.fit_all_action.setIcon(icons(QStyle.StandardPixmap.SP_TitleBarMaxButton))
        self.presentation_view_action.setIcon(icons(QStyle.StandardPixmap.SP_DesktopIcon))
        self.presentation_camera_action.setIcon(icons(QStyle.StandardPixmap.SP_ComputerIcon))
        self.undo_action.setIcon(icons(QStyle.StandardPixmap.SP_ArrowBack))
        self.redo_action.setIcon(icons(QStyle.StandardPixmap.SP_ArrowForward))

        # Compact ribbon captions keep the full 1920 px demo layout readable;
        # menus and tooltips retain the descriptive action names above.
        for action, caption in (
            (self.new_action, "New"), (self.open_action, "Open"), (self.save_action, "Save"),
            (self.load_sample_action, "Sample"), (self.load_complete_action, "Complete"),
            (self.add_cabinet_action, "Place"),
            (self.remove_cabinet_action, "Remove"), (self.undo_action, "Undo"),
            (self.redo_action, "Redo"), (self.snap_action, "Snap"),
            (self.grid_snap_action, "Grid 100"), (self.front_view_action, "Front"),
            (self.isometric_view_action, "Isometric"), (self.fit_all_action, "Fit All"),
            (self.reset_3d_action, "Reset"), (self.maximize_3d_action, "Max 3D"),
            (self.presentation_view_action, "Present"),
            (self.presentation_camera_action, "Camera"), (self.show_interior_action, "Interior"),
            (self.export_xlsx_action, "XLSX"), (self.export_dxf_action, "DXF"),
        ):
            action.setIconText(caption)

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("&File")
        file_menu.addActions([self.new_action, self.open_action, self.save_action, self.save_as_action])
        file_menu.addActions([self.load_sample_action, self.load_complete_action])
        file_menu.addSeparator()
        file_menu.addActions([self.export_xlsx_action, self.export_dxf_action])
        file_menu.addAction(self.engineering_export_action)
        file_menu.addAction(self.complete_kitchen_export_action)
        file_menu.addSeparator()
        file_menu.addAction(self.exit_action)
        edit_menu = self.menuBar().addMenu("&Edit")
        edit_menu.addActions([self.undo_action, self.redo_action])
        edit_menu.addAction(self.duplicate_action)
        edit_menu.addSeparator()
        edit_menu.addAction("Select Cabinet", lambda: self.width_spin.setFocus())
        view_menu = self.menuBar().addMenu("&View")
        self.view_menu = view_menu
        view_menu.addActions([
            self.front_view_action, self.isometric_view_action, self.fit_all_action,
            self.reset_3d_action, self.maximize_3d_action,
        ])
        view_menu.addSeparator()
        view_menu.addActions([self.presentation_view_action, self.presentation_camera_action, self.hide_room_walls_action])
        view_menu.addSeparator()
        view_menu.addAction(self.show_interior_action)
        view_menu.addAction(self.realistic_render_action)
        design_menu = self.menuBar().addMenu("&Design")
        design_menu.addActions([self.load_complete_action, self.add_cabinet_action,
                                self.duplicate_action, self.remove_cabinet_action])
        design_menu.addAction(self.ai_design_action)
        design_menu.addSeparator()
        opening_menu = design_menu.addMenu("Room Openings")
        opening_menu.addActions([
            self.select_wall_action, self.add_door_action, self.add_window_action,
            self.edit_opening_action, self.remove_opening_action,
        ])
        design_menu.addSeparator()
        design_menu.addActions([self.snap_action, self.grid_snap_action])
        design_menu.addSeparator()
        design_menu.addAction("Cabinet Properties", lambda: self.properties_dock.raise_())
        manufacturing_menu = self.menuBar().addMenu("&Manufacturing")
        manufacturing_menu.addAction(self.manufacturing_preview_action)
        manufacturing_menu.addAction(self.sheet_nesting_action)
        manufacturing_menu.addAction(self.documents_action)
        manufacturing_menu.addAction(self.price_setup_action)
        manufacturing_menu.addAction(self.price_refresh_action)
        manufacturing_menu.addSeparator()
        manufacturing_menu.addActions([self.demo_construction_action,
                                       self.import_construction_action,
                                       self.legacy_construction_action])
        manufacturing_menu.addSeparator()
        manufacturing_menu.addActions([self.export_xlsx_action, self.export_dxf_action])
        manufacturing_menu.addAction(self.export_cut_list_action)
        manufacturing_menu.addAction(self.engineering_export_action)
        manufacturing_menu.addAction(self.complete_kitchen_export_action)
        help_menu = self.menuBar().addMenu("&Help")
        help_menu.addAction(self.about_action)

    def _build_toolbar(self) -> None:
        def add_header_shadow(widget: QWidget) -> None:
            shadow = QGraphicsDropShadowEffect(widget)
            shadow.setBlurRadius(11)
            shadow.setOffset(0, 2)
            shadow.setColor(QColor(78, 56, 42, 35))
            widget.setGraphicsEffect(shadow)

        toolbar = QToolBar("Project Header")
        toolbar.setObjectName("mainRibbon")
        toolbar.setMovable(False)
        toolbar.setFloatable(False)
        toolbar.setFixedHeight(66)
        header = QWidget()
        header.setObjectName("premiumHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(22, 7, 16, 7)
        header_layout.setSpacing(0)
        brand_badge = QLabel()
        brand_badge.setObjectName("brandBadge")
        brand_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        brand_badge.setFixedSize(46, 46)
        brand_badge.setPixmap(brand_mark())
        brand_layout = QVBoxLayout()
        brand_layout.setSpacing(0)
        brand_layout.setContentsMargins(0, 0, 0, 4)
        brand_title = QLabel("KÜCHE7")
        brand_title.setObjectName("brandTitle")
        brand_title.setFixedWidth(112)
        self.header_workspace_caption = QLabel("DESIGN STUDIO")
        self.header_workspace_caption.setObjectName("brandCaption")
        self.header_workspace_caption.setFixedWidth(112)
        self.header_workspace_caption.setToolTip("DESIGN STUDIO")
        brand_layout.addWidget(brand_title)
        brand_layout.addWidget(self.header_workspace_caption)
        project_layout = QVBoxLayout()
        project_layout.setSpacing(7)
        self.header_project_title = QLabel()
        self.header_project_title.setObjectName("headerProjectTitle")
        self.header_project_title.setFixedSize(330, 19)
        self.header_project_meta = QLabel()
        self.header_project_meta.setObjectName("headerProjectMeta")
        self.header_project_meta.setFixedSize(330, 17)
        project_layout.addWidget(self.header_project_title)
        project_layout.addWidget(self.header_project_meta)
        brand_divider = QFrame()
        brand_divider.setObjectName("headerBrandDivider")
        brand_divider.setFixedSize(1, 38)
        menu = QMenu(self)
        for action in self.menuBar().actions():
            menu.addAction(action)
        menu_button = QToolButton()
        menu_button.setObjectName("headerMenu")
        menu_button.setIcon(top_icon("menu", "#915B37"))
        menu_button.setIconSize(QSize(20, 20))
        menu_button.setFixedSize(36, 36)
        menu_button.setMenu(menu)
        menu_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu_button.setToolTip("All project, design, view and manufacturing commands")
        header_layout.addWidget(brand_badge)
        header_layout.addSpacing(12)
        header_layout.addLayout(brand_layout)
        header_layout.addSpacing(37)
        header_layout.addWidget(brand_divider)
        header_layout.addSpacing(35)
        header_layout.addLayout(project_layout)
        header_layout.addStretch(1)
        self.header_saved_icon = QLabel()
        self.header_saved_icon.setObjectName("headerSavedIcon")
        self.header_saved_icon.setPixmap(top_label_pixmap("saved", "#446449"))
        header_layout.addWidget(self.header_saved_icon)
        self.header_dirty_label = QLabel("All changes saved")
        self.header_dirty_label.setObjectName("headerSaved")
        self.header_dirty_label.setFixedWidth(140)
        header_layout.addWidget(self.header_dirty_label)
        header_layout.addSpacing(12)
        status_divider = QFrame()
        status_divider.setObjectName("headerStatusDivider")
        status_divider.setFixedSize(1, 30)
        header_layout.addWidget(status_divider)
        header_layout.addSpacing(12)
        history = QFrame()
        history.setObjectName("headerHistory")
        history_layout = QHBoxLayout(history)
        history_layout.setContentsMargins(3, 2, 3, 2)
        history_layout.setSpacing(2)
        for action, icon_name in ((self.undo_action, "undo"), (self.redo_action, "redo")):
            button = QToolButton(history)
            button.setDefaultAction(action)
            button.setIcon(top_icon(icon_name, "#2A2C29"))
            button.setIconSize(QSize(20, 20))
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
            button.setObjectName("headerUtility")
            button.setToolTip(action.text())
            button.setFixedSize(37, 34)
            history_layout.addWidget(button)
            if icon_name == "undo":
                self.header_undo_button = button
            else:
                self.header_redo_button = button
        header_layout.addWidget(history)
        header_layout.addSpacing(12)
        save_button = QPushButton("Save")
        save_button.setObjectName("headerSave")
        save_button.setFixedSize(78, 40)
        save_button.setIcon(top_icon("save", "#252A27"))
        save_button.setIconSize(QSize(18, 18))
        save_button.clicked.connect(self.save_action.trigger)
        add_header_shadow(save_button)
        header_layout.addWidget(save_button)
        header_layout.addSpacing(12)
        export_button = PremiumExportButton()
        export_button.setObjectName("headerExport")
        export_menu = AnchoredExportMenu(export_button)
        export_icon = top_icon("export", "#646A61")
        for action in (self.export_xlsx_action, self.export_dxf_action,
                       self.engineering_export_action, self.complete_kitchen_export_action):
            action.setIcon(export_icon)
        export_menu.addAction(self.export_xlsx_action)
        for label, method in (
            ("Export BOM (PDF)…", "export_bom_pdf"),
            ("Export Quotation (XLSX)…", "export_quote_excel"),
            ("Export Quotation (PDF)…", "export_quote_pdf"),
            ("Export Issued Quotation (XLSX)…", "export_issued_quote_excel"),
            ("Export Issued Quotation (PDF)…", "export_issued_quote_pdf"),
        ):
            action = QAction(label, export_menu)
            action.setIcon(export_icon)
            action.triggered.connect(lambda checked=False, name=method: getattr(self.documents_workspace, name)())
            export_menu.addAction(action)
        export_menu.addSeparator()
        export_menu.addActions([self.complete_kitchen_export_action,
                                self.export_dxf_action, self.engineering_export_action])
        export_button.setMenu(export_menu)
        export_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        add_header_shadow(export_button)
        header_layout.addWidget(export_button)
        header_layout.addSpacing(18)
        header_layout.addWidget(menu_button)
        toolbar.addWidget(header)
        self.addToolBar(toolbar)
        self.menuBar().hide()
        # Hidden native menus remain accessible through Menu. Keep shortcuts
        # attached to the window rather than depending on menu visibility.
        self.addActions([self.new_action, self.open_action, self.save_action, self.save_as_action,
                         self.undo_action, self.redo_action, self.duplicate_action,
                         self.exit_action, self.fit_all_action, self.maximize_3d_action,
                         self.manufacturing_preview_action, self.sheet_nesting_action])

    @staticmethod
    def _canvas_panel(
        title: str,
        subtitle: str,
        content: QWidget,
        header_action: QAction | None = None,
    ) -> QFrame:
        panel = QFrame()
        panel.setObjectName("canvasPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        header = QFrame()
        header.setObjectName("canvasHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(12, 6, 12, 6)
        header_layout.setSpacing(8)
        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(1)
        title_label = QLabel(title)
        title_label.setObjectName("canvasTitle")
        subtitle_label = QLabel(subtitle)
        subtitle_label.setObjectName("canvasSubtitle")
        text_layout.addWidget(title_label)
        text_layout.addWidget(subtitle_label)
        header_layout.addLayout(text_layout, 1)
        if header_action is not None:
            action_button = QToolButton()
            action_button.setObjectName("canvasActionButton")
            action_button.setDefaultAction(header_action)
            action_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            header_layout.addWidget(action_button)
        layout.addWidget(header)
        layout.addWidget(content, 1)
        return panel

    def _build_central_views(self) -> None:
        self.workspace_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.workspace_splitter.setObjectName("workspaceSplitter")
        self.workspace_splitter.setChildrenCollapsible(False)
        self.workspace_splitter.setHandleWidth(0)
        self.plan_view = RoomPlanView()
        # The same interactive plan can fit a compact card; expand it for
        # precise placement instead of retaining its former 380x300 minimum.
        self.plan_view.setMinimumSize(0, 0)
        self.plan_view.installEventFilter(self)
        self.plan_view.viewport().installEventFilter(self)
        self.plan_view.cabinetSelected.connect(self.select_cabinet)
        self.plan_view.cabinetMoveRequested.connect(self.move_cabinet)
        self.plan_view.placementRequested.connect(self._place_catalogue_cabinet)
        self.plan_view.placementCancelled.connect(
            lambda: self.statusBar().showMessage("Placement cancelled; project unchanged")
        )
        self.plan_view.wallSelected.connect(self.select_wall)
        self.plan_view.openingSelected.connect(self.select_opening)
        self.plan_view.openingMoveRequested.connect(self.move_opening)
        self.plan_view.openingPlacementRequested.connect(self._place_opening)
        self.plan_view.productSelected.connect(self.select_product)
        self.plan_view.productPlacementRequested.connect(self._place_product)
        self.plan_view.productMoveRequested.connect(self.move_product)
        self.plan_view.placementRejected.connect(lambda message: self._show_placement_error(ValueError(message)))
        self.view3d = Cabinet3DView()
        self.view3d.cabinetSelected.connect(self._select_cabinet_from_3d)
        self.view3d.productSelected.connect(self._select_product_from_3d)
        self.plan_panel = self._canvas_panel("2D ROOM PLAN", "", self.plan_view)
        self.model_panel = self._canvas_panel("3D KITCHEN", "", self.view3d)
        self.model_panel.findChild(QFrame, "canvasHeader").hide()
        self.plan_room_dimensions = self.plan_panel.findChild(QLabel, "canvasSubtitle")
        self.plan_room_dimensions.setObjectName("planRoomDimensions")
        self.plan_expand_button = QToolButton()
        self.plan_expand_button.setObjectName("planExpandButton")
        self.plan_expand_button.setText("Open plan")
        self.plan_expand_button.setIcon(top_icon("maximize", "#965B31"))
        self.plan_expand_button.setIconSize(QSize(14, 14))
        self.plan_expand_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.plan_expand_button.clicked.connect(lambda: self._set_plan_expanded(not self.design_stage.plan_expanded))
        self.plan_panel.findChild(QFrame, "canvasHeader").layout().addWidget(self.plan_expand_button)
        self.design_stage = DesignStage(self.model_panel, self.plan_panel)
        live_badge = QLabel("●  LIVE 3D VIEW")
        live_badge.setObjectName("live3dBadge")
        self.design_stage.add_overlay(live_badge)
        viewport_controls = QFrame()
        viewport_controls.setObjectName("viewportControls")
        control_shadow = QGraphicsDropShadowEffect(viewport_controls)
        control_shadow.setBlurRadius(22)
        control_shadow.setOffset(0, 5)
        control_shadow.setColor(QColor(45, 37, 29, 45))
        viewport_controls.setGraphicsEffect(control_shadow)
        controls_layout = QHBoxLayout(viewport_controls)
        controls_layout.setContentsMargins(6, 3, 6, 3)
        controls_layout.setSpacing(1)
        for caption, icon_name, action in (("Front", "front", self.front_view_action),
                                           ("Isometric", "isometric", self.isometric_view_action),
                                           ("Fit", "fit", self.fit_all_action),
                                           ("Expand", "maximize", self.maximize_3d_action)):
            button = QToolButton()
            button.setObjectName("viewportControlButton")
            button.setText(caption)
            button.setIcon(top_icon(icon_name, "#524A40"))
            button.setIconSize(QSize(17, 17))
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            button.setToolTip(action.text())
            button.clicked.connect(action.trigger)
            button.setEnabled(action.isEnabled())
            action.changed.connect(lambda b=button, a=action: b.setEnabled(a.isEnabled()))
            controls_layout.addWidget(button)
        self.interior_view_button = QToolButton()
        self.interior_view_button.setObjectName("viewportInteriorButton")
        self.interior_view_button.setText("Interior")
        self.interior_view_button.setIcon(top_icon("interior", "#524A40", "#FFFFFF"))
        self.interior_view_button.setIconSize(QSize(17, 17))
        self.interior_view_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        self.interior_view_button.setCheckable(True)
        self.interior_view_button.setToolTip(self.show_interior_action.toolTip())
        self.interior_view_button.setEnabled(self.show_interior_action.isEnabled())
        self.show_interior_action.changed.connect(
            lambda: self.interior_view_button.setEnabled(self.show_interior_action.isEnabled())
        )
        self.interior_view_button.clicked.connect(
            lambda checked: self.show_interior_action.setChecked(checked)
        )
        self.show_interior_action.toggled.connect(self.interior_view_button.setChecked)
        controls_layout.addWidget(self.interior_view_button)

        self.viewport_view_button = QToolButton()
        self.viewport_view_button.setObjectName("viewportViewMenu")
        self.viewport_view_button.setText("View")
        self.viewport_view_button.setIcon(top_icon("menu", "#524A40"))
        self.viewport_view_button.setIconSize(QSize(17, 17))
        self.viewport_view_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        self.viewport_view_button.setToolTip("Camera, wall visibility and placement guides")
        view_options = QMenu(self.viewport_view_button)
        view_options.addActions([self.reset_3d_action, self.presentation_camera_action,
                                 self.hide_room_walls_action, self.show_interior_action])
        view_options.addSeparator()
        view_options.addActions([self.snap_action, self.grid_snap_action])
        self.viewport_view_button.setMenu(view_options)
        self.viewport_view_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        controls_layout.addWidget(self.viewport_view_button)
        self.design_stage.add_overlay(viewport_controls)
        selection_card = QFrame()
        selection_card.setObjectName("viewportSelection")
        selection_layout = QVBoxLayout(selection_card)
        selection_layout.setContentsMargins(15, 7, 15, 7)
        selection_layout.setSpacing(1)
        self.viewport_selection_title = QLabel()
        self.viewport_selection_title.setObjectName("viewportSelectionTitle")
        self.viewport_selection_detail = QLabel()
        self.viewport_selection_detail.setObjectName("viewportSelectionDetail")
        selection_layout.addWidget(self.viewport_selection_title)
        selection_layout.addWidget(self.viewport_selection_detail)
        self.design_stage.add_overlay(selection_card)
        design_root = QWidget()
        design_root.setObjectName("designRoot")
        design_layout = QVBoxLayout(design_root)
        design_layout.setContentsMargins(0, 0, 0, 0)
        design_layout.setSpacing(0)
        design_header = QFrame()
        design_header.setObjectName("designHeader")
        self.design_header = design_header
        design_header.installEventFilter(self)
        design_header_layout = QHBoxLayout(design_header)
        design_header_layout.setContentsMargins(14, 12, 61, 4)
        design_header_layout.setSpacing(0)
        title_stack = QVBoxLayout()
        title_stack.setSpacing(0)
        title = QLabel("Design Studio")
        title.setObjectName("designTitle")
        title.setFixedHeight(42)
        title_stack.addWidget(title)
        underline = QFrame()
        underline.setObjectName("designTitleUnderline")
        underline.setFixedSize(48, 2)
        title_stack.addWidget(underline)
        design_header_layout.addLayout(title_stack)
        design_header_layout.setAlignment(title_stack, Qt.AlignmentFlag.AlignTop)
        design_header_layout.addStretch(1)
        def view_icon(name: str) -> QIcon:
            return top_icon(name, "#343B35", "#FFFFFF")

        presentation_button = QToolButton()
        self.presentation_mode_button = presentation_button
        presentation_button.setObjectName("presentationModeButton")
        presentation_button.setText("Presentation")
        presentation_button.setIcon(top_icon("presentation", "#343B35"))
        presentation_button.setIconSize(QSize(19, 19))
        presentation_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        presentation_button.setCheckable(True)
        presentation_button.clicked.connect(self.presentation_view_action.trigger)
        self.presentation_view_action.toggled.connect(presentation_button.setChecked)
        self.technical_view_button = QToolButton()
        self.technical_view_button.setObjectName("technicalModeButton")
        self.technical_view_button.setText("3D View")
        self.technical_view_button.setIcon(view_icon("isometric"))
        self.technical_view_button.setIconSize(QSize(19, 19))
        self.technical_view_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.technical_view_button.setCheckable(True)
        self.technical_view_button.setChecked(True)
        self.technical_view_button.clicked.connect(
            lambda: (self._set_plan_expanded(False), self.presentation_view_action.setChecked(False))
        )
        self.plan_toggle_button = QToolButton()
        self.plan_toggle_button.setObjectName("designPlanButton")
        self.plan_toggle_button.setText("2D Plan")
        self.plan_toggle_button.setIcon(view_icon("plan"))
        self.plan_toggle_button.setIconSize(QSize(19, 19))
        self.plan_toggle_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.plan_toggle_button.setCheckable(True)
        self.plan_toggle_button.clicked.connect(lambda: self._set_plan_expanded(not self.design_stage.plan_expanded))
        for button, width in ((self.technical_view_button, 164),
                              (self.plan_toggle_button, 174),
                              (presentation_button, 190)):
            button.setFixedWidth(width)
            design_header_layout.addWidget(button)
            if button is self.plan_toggle_button:
                design_header_layout.addSpacing(16)
        design_layout.addWidget(design_header)
        design_tools = QFrame()
        design_tools.setObjectName("designTools")
        tools_layout = QHBoxLayout(design_tools)
        tools_layout.setContentsMargins(14, 6, 12, 6)
        tools_layout.setSpacing(5)
        self.design_tool_buttons = {}
        for caption, icon_name, handler, tooltip in (
            ("Select", "select", lambda: self._set_plan_expanded(True), "Select and edit objects in the 2D plan"),
            ("Place", "place", lambda: self.explorer_tabs.setCurrentWidget(self.library_page), "Browse products and place them in the 2D plan"),
            ("Move", "move", lambda: self._set_plan_expanded(True), "Move selected objects in the 2D plan"),
            ("Snap", "snap", self.snap_action.trigger, self.snap_action.toolTip()),
            ("Grid", "grid", self.grid_snap_action.trigger, "Toggle the 100 mm placement grid"),
            ("Duplicate", "duplicate", self.duplicate_action.trigger, "Duplicate selected object"),
            ("Delete", "delete", self.remove_cabinet_action.trigger, "Remove selected object"),
            ("Front", "front", self.front_view_action.trigger, "Front view"),
            ("Isometric", "isometric", self.isometric_view_action.trigger, "Isometric view"),
            ("Interior", "interior", self.show_interior_action.trigger, self.show_interior_action.toolTip()),
            ("Reset", "reset", self.reset_3d_action.trigger, "Reset camera view"),
            ("Max", "maximize", self.maximize_3d_action.trigger, "Maximize or restore the 3D viewport"),
            ("Fit", "fit", self.fit_all_action.trigger, "Fit the complete kitchen"),
        ):
            if caption == "Front":
                tools_layout.addSpacing(2)
                separator = QFrame()
                separator.setObjectName("designToolsSeparator")
                separator.setFrameShape(QFrame.Shape.VLine)
                tools_layout.addWidget(separator)
                tools_layout.addSpacing(2)
            button = QToolButton()
            button.setObjectName("designToolButton")
            button.setProperty("primary", caption == "Select")
            button.setText(caption)
            button.setIcon(top_icon(icon_name, "#8A502B" if caption == "Select" else "#343B35"))
            button.setIconSize(QSize(20, 20))
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            button.setToolTip(tooltip)
            button.setFixedWidth(
                70 if caption == "Duplicate" else 66 if caption == "Isometric"
                else 60 if caption in ("Front", "Interior", "Reset", "Max", "Fit") else 62
            )
            button.setFixedHeight(52)
            button.clicked.connect(handler)
            if caption in ("Snap", "Grid", "Interior", "Max"):
                action = {"Snap": self.snap_action, "Grid": self.grid_snap_action,
                          "Interior": self.show_interior_action, "Max": self.maximize_3d_action}[caption]
                button.setCheckable(True)
                button.setChecked(action.isChecked())
                action.toggled.connect(button.setChecked)
            tools_layout.addWidget(button)
            self.design_tool_buttons[caption] = button
        tools_layout.addStretch(1)
        self.design_tools = design_tools
        design_tools.installEventFilter(self)
        design_layout.addWidget(design_tools)
        design_layout.addWidget(self.design_stage, 1)
        self.workspace_splitter.addWidget(design_root)
        self.manufacturing_preview = ManufacturingPreviewWidget()
        self.manufacturing_preview.set_cabinet(self.project.selected_cabinet)
        self.sheet_nesting = SheetNestingWidget()
        self.sheet_nesting.set_project(self.project)
        self.documents_workspace = DocumentsWorkspace(lambda: self._set_dirty(True),
                                                      on_company_refresh=self.refresh_company_prices)
        self.documents_workspace.set_project(self.project)
        self.ai_design_workspace = AIDesignWorkspace(
            self.generate_design_proposal, self.apply_design_proposal, self.reject_design_proposal
        )
        self.realistic_render_workspace = RealisticRenderWorkspace(
            self.view3d, lambda: project_fingerprint(self.project), self._capture_render_scene,
            context_callback=lambda: project_render_context(self.project),
        )
        self.workspace_tabs = QTabWidget()
        self.workspace_tabs.setObjectName("workspaceTabs")
        self.workspace_tabs.setDocumentMode(True)
        self.workspace_tabs.addTab(self.workspace_splitter, "Design Studio")
        self.workspace_tabs.addTab(self.manufacturing_preview, "Manufacturing Preview")
        self.workspace_tabs.addTab(self.sheet_nesting, "Sheet Nesting")
        self.workspace_tabs.addTab(self.documents_workspace, "BOM & Quotation")
        self.workspace_tabs.addTab(self.ai_design_workspace, "Design Assistant")
        self.workspace_tabs.addTab(self.realistic_render_workspace, "Realistic Rendering")
        self.workspace_tabs.currentChanged.connect(self._workspace_changed)
        self.workspace_tabs.tabBar().hide()
        self.setCentralWidget(self.workspace_tabs)

    def _set_plan_expanded(self, expanded: bool) -> None:
        self.design_stage.set_plan_expanded(expanded)
        self.plan_expand_button.setText("Compact plan" if expanded else "Open plan")
        self.plan_toggle_button.setText("Compact plan" if expanded else "2D Plan")
        self.plan_toggle_button.setChecked(expanded)
        self.technical_view_button.setChecked(not expanded)
        self.statusBar().showMessage("2D plan expanded for placement and editing" if expanded else "Compact 2D plan")

    def _build_explorer(self) -> None:
        self.explorer_dock = QDockWidget("PROJECT & CATALOGUE", self)
        self.explorer_dock.setObjectName("explorerDock")
        self.explorer_dock.setMinimumWidth(370)
        self.project_tree = QTreeWidget()
        self.project_tree.installEventFilter(self)
        self.project_tree.viewport().installEventFilter(self)
        self.project_tree.setHeaderHidden(True)
        self.project_tree.setIndentation(15)
        self.project_tree.setUniformRowHeights(True)
        self.project_tree.setAnimated(True)
        self.project_tree.itemClicked.connect(self._tree_item_clicked)
        self.explorer_tabs = QTabWidget()
        self.explorer_tabs.setObjectName("explorerTabs")
        objects_page = QWidget()
        objects_layout = QVBoxLayout(objects_page)
        objects_layout.setContentsMargins(12, 17, 5, 9)
        objects_layout.setSpacing(1)
        self._cabinet_cards_collapsed = False
        self._appliance_cards_collapsed = False
        cabinet_heading = QWidget()
        cabinet_heading.setObjectName("sidebarCabinetHeading")
        cabinet_heading_layout = QHBoxLayout(cabinet_heading)
        cabinet_heading_layout.setContentsMargins(4, 0, 3, 0)
        cabinet_heading_layout.setSpacing(0)
        self.cabinet_count_label = QLabel("Cabinets (0)")
        self.cabinet_count_label.setObjectName("sidebarSectionTitle")
        self.cabinet_collapse_button = QToolButton()
        self.cabinet_collapse_button.setObjectName("sidebarCollapseButton")
        self.cabinet_collapse_button.setText("⌃")
        self.cabinet_collapse_button.setToolTip("Collapse cabinet cards")
        self.cabinet_collapse_button.clicked.connect(self._toggle_cabinet_cards)
        cabinet_heading_layout.addWidget(self.cabinet_count_label)
        cabinet_heading_layout.addStretch(1)
        cabinet_heading_layout.addWidget(self.cabinet_collapse_button)
        self.object_list = QListWidget()
        self.object_list.setObjectName("objectList")
        self.object_list.setSpacing(0)
        self.object_list.setMouseTracking(True)
        self.object_list.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.object_list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.object_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.object_list.setItemDelegate(SidebarCardDelegate(self.object_list))
        self.object_list.itemClicked.connect(self._object_card_clicked)
        self.object_summary = QLabel()
        self.object_summary.setObjectName("objectSummary")
        self.object_summary.setWordWrap(True)
        self.object_summary.hide()
        self.browse_library_button = QPushButton("＋  Browse Product Library")
        self.browse_library_button.setObjectName("browseLibraryButton")
        self.browse_library_button.clicked.connect(lambda: self.explorer_tabs.setCurrentWidget(self.library_page))
        objects_layout.addWidget(cabinet_heading)
        objects_layout.addWidget(self.object_list, 1)
        objects_layout.addWidget(self.object_summary)
        objects_layout.addWidget(self.browse_library_button)
        self.explorer_tabs.addTab(objects_page, "Objects")
        self.explorer_tabs.addTab(self.project_tree, "Hierarchy")
        catalogue_page = QWidget()
        catalogue_layout = QVBoxLayout(catalogue_page)
        catalogue_layout.setContentsMargins(8, 10, 8, 10)
        catalogue_layout.setSpacing(8)
        self.catalogue_category_combo = QComboBox()
        self.catalogue_category_combo.addItems(["All Furniture — 15", *CATEGORIES])
        self.catalogue_list = QListWidget()
        self.catalogue_list.setObjectName("catalogueList")
        self.catalogue_list.setAlternatingRowColors(True)
        self.catalogue_list.setIconSize(QSize(76, 60))
        self.catalogue_list.setSpacing(2)
        self.catalogue_detail = QLabel()
        self.catalogue_detail.setObjectName("catalogueDetail")
        self.catalogue_detail.setWordWrap(True)
        self.catalogue_add_button = QPushButton("Place selected furniture")
        self.catalogue_add_button.setObjectName("primaryButton")
        catalogue_layout.addWidget(self.catalogue_category_combo)
        catalogue_layout.addWidget(self.catalogue_list, 1)
        catalogue_layout.addWidget(self.catalogue_detail)
        catalogue_layout.addWidget(self.catalogue_add_button)
        self.explorer_tabs.addTab(catalogue_page, "Catalogue")
        library_page = QWidget()
        library_layout = QVBoxLayout(library_page)
        library_layout.setContentsMargins(8, 10, 8, 10)
        library_layout.setSpacing(8)
        self.library_combo = QComboBox()
        self.library_combo.addItems(LIBRARIES)
        self.library_family_combo = QComboBox()
        self.library_family_combo.addItems(FURNITURE_FAMILIES)
        self.library_category_combo = QComboBox()
        self.library_list = QListWidget()
        self.library_list.setAlternatingRowColors(True)
        self.library_list.setIconSize(QSize(54, 48))
        self.library_description = QLabel()
        self.library_description.setWordWrap(True)
        self.hardware_quantity_spin = self._spin(1, 100, "")
        self.hardware_quantity_spin.setValue(1)
        self.hardware_quantity_label = QLabel("Assignment quantity (demo metadata)")
        self.library_add_button = QPushButton("Place selected product in 2D")
        self.library_add_button.setObjectName("primaryButton")
        self.library_create_button = QPushButton("Add Cabinet…")
        self.library_edit_button = QPushButton("Edit Cabinet…")
        library_manage = QHBoxLayout()
        library_manage.addWidget(self.library_create_button)
        library_manage.addWidget(self.library_edit_button)
        self.library_remove_hardware_button = QPushButton("Remove selected hardware assignment")
        self.library_remove_hardware_button.hide()
        library_heading = QLabel("PRODUCT LIBRARY")
        library_heading.setObjectName("sidebarSectionTitle")
        library_layout.addWidget(library_heading)
        library_layout.addWidget(self.library_combo)
        library_layout.addWidget(self.library_family_combo)
        library_layout.addWidget(self.library_category_combo)
        library_layout.addWidget(self.library_list, 1)
        library_layout.addWidget(self.library_description)
        library_layout.addWidget(self.hardware_quantity_label)
        library_layout.addWidget(self.hardware_quantity_spin)
        library_layout.addWidget(self.library_add_button)
        library_layout.addLayout(library_manage)
        library_layout.addWidget(self.library_remove_hardware_button)
        self.library_page = library_page
        self.explorer_tabs.addTab(library_page, "Libraries")
        # The original catalogue widgets remain available to legacy scripts,
        # while users browse one unified product-library interface.
        self.explorer_tabs.tabBar().moveTab(3, 1)
        self.explorer_tabs.setTabVisible(3, False)
        self.explorer_tabs.setCurrentWidget(objects_page)
        self.explorer_tabs.currentChanged.connect(lambda _index: self._sync_workspace_rail())
        navigation = QFrame()
        navigation.setObjectName("workspaceRail")
        navigation.setFixedWidth(96)
        rail_layout = QVBoxLayout(navigation)
        rail_layout.setContentsMargins(6, 23, 6, 8)
        rail_layout.setSpacing(6)
        self.rail_buttons = []
        for caption, icon_name, target in (
            ("Design Studio", "design", self.workspace_splitter),
            ("Libraries", "library", self.workspace_splitter),
            ("Project", "project", self.workspace_splitter),
            ("Materials", "materials", self.workspace_splitter),
            ("Manufacturing", "engineering", self.manufacturing_preview),
            ("Sheet Nesting", "nesting", self.sheet_nesting),
            ("BOM & Quotation", "documents", self.documents_workspace),
            ("Design Assistant", "assistant", self.ai_design_workspace),
            ("Realistic Rendering", "render", self.realistic_render_workspace),
        ):
            button = QToolButton(navigation)
            button.setObjectName("railButton")
            rail_icon = {"library": "layers", "engineering": "gear"}.get(icon_name, icon_name)
            button.setIcon(outline_icon(rail_icon, "#454C40"))
            button.setIconSize(QSize(25, 25))
            button.setText({
                "Design Studio": "Design\nStudio",
                "Sheet Nesting": "Sheet Nesting",
                "BOM & Quotation": "BOM &\nQuotation",
                "Design Assistant": "Design\nAssistant",
                "Realistic Rendering": "Realistic\nRendering",
            }.get(caption, caption))
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            button.setFixedSize(82, 70)
            if icon_name in ("engineering", "nesting"):
                button.setProperty("compactLabel", True)
                compact_font = QFont(button.font())
                compact_font.setPointSizeF(7.0)
                button.setFont(compact_font)
            button.setToolTip(caption)
            button.clicked.connect(lambda _checked=False, page=target, icon=icon_name:
                                   self._navigate_rail(page, icon))
            self.rail_buttons.append((button, target, icon_name))
            if icon_name in ("project", "materials"):
                button.hide()  # These remain available from the project dropdown.
            else:
                rail_layout.addWidget(button)
        rail_layout.addStretch(1)
        self.rail_settings_button = QToolButton(navigation)
        self.rail_settings_button.setObjectName("railFooterButton")
        self.rail_settings_button.setIcon(outline_icon("gear", "#343A35"))
        self.rail_settings_button.setIconSize(QSize(21, 21))
        self.rail_settings_button.setText("Settings")
        self.rail_settings_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        self.rail_settings_button.setFixedSize(82, 47)
        settings_menu = QMenu(self.rail_settings_button)
        settings_menu.addActions([self.price_setup_action, self.price_refresh_action])
        self.rail_settings_menu = settings_menu
        self.rail_settings_button.clicked.connect(
            lambda: settings_menu.popup(
                self.rail_settings_button.mapToGlobal(self.rail_settings_button.rect().topRight())
            )
        )
        self.rail_settings_button.setToolTip("Company pricing settings")
        rail_layout.addWidget(self.rail_settings_button)
        self.rail_help_button = QToolButton(navigation)
        self.rail_help_button.setObjectName("railFooterButton")
        self.rail_help_button.setIcon(outline_icon("help", "#343A35"))
        self.rail_help_button.setIconSize(QSize(21, 21))
        self.rail_help_button.setText("Help")
        self.rail_help_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        self.rail_help_button.setFixedSize(82, 47)
        self.rail_help_button.clicked.connect(self.about_action.trigger)
        rail_layout.addWidget(self.rail_help_button)
        sidebar = QWidget()
        sidebar.setObjectName("projectSidebar")
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(0)
        sidebar_heading = QWidget()
        sidebar_heading.setObjectName("sidebarHeading")
        sidebar_heading.setMinimumHeight(76)
        heading_layout = QVBoxLayout(sidebar_heading)
        heading_layout.setContentsMargins(15, 10, 11, 8)
        heading_layout.setSpacing(3)
        heading_label = QLabel("PROJECT")
        heading_label.setObjectName("sidebarEyebrow")
        self.sidebar_project_label = QLabel("Kitchen workspace")
        self.sidebar_project_label.setObjectName("sidebarProjectName")
        self.sidebar_project_label.setWordWrap(False)
        self.sidebar_project_label.setMinimumWidth(0)
        project_row = QHBoxLayout()
        project_row.setContentsMargins(0, 0, 0, 0)
        project_row.setSpacing(7)
        project_icon = QLabel()
        project_icon.setObjectName("sidebarProjectIcon")
        project_icon.setPixmap(outline_icon("project", "#A76637").pixmap(QSize(21, 21)))
        self.sidebar_project_menu_button = QToolButton()
        self.sidebar_project_menu_button.setObjectName("sidebarProjectMenu")
        self.sidebar_project_menu_button.setText("")
        self.sidebar_project_menu_button.setToolTip("Project and materials navigation")
        project_menu = QMenu(self.sidebar_project_menu_button)
        project_menu.addAction("Project hierarchy", lambda: self._navigate_rail(self.workspace_splitter, "project"))
        project_menu.addAction("Materials", lambda: self._navigate_rail(self.workspace_splitter, "materials"))
        project_menu.addSeparator()
        project_menu.addActions([self.new_action, self.open_action, self.save_action])
        self.sidebar_project_menu_button.setMenu(project_menu)
        self.sidebar_project_menu_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        heading_layout.addWidget(heading_label)
        project_row.addWidget(project_icon)
        project_row.addWidget(self.sidebar_project_label, 1)
        project_row.addWidget(self.sidebar_project_menu_button)
        heading_layout.addLayout(project_row)
        sidebar_layout.addWidget(sidebar_heading)
        sidebar_layout.addWidget(self.explorer_tabs, 1)
        dock_content = QWidget()
        dock_content.setObjectName("explorerContent")
        dock_layout = QHBoxLayout(dock_content)
        dock_layout.setContentsMargins(0, 0, 0, 0)
        dock_layout.setSpacing(0)
        dock_layout.addWidget(navigation)
        dock_layout.addWidget(sidebar, 1)
        self.explorer_dock.setTitleBarWidget(QWidget())
        self.explorer_dock.setWidget(dock_content)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.explorer_dock)
        self.catalogue_category_combo.currentTextChanged.connect(self._populate_catalogue)
        self.catalogue_list.currentItemChanged.connect(self._catalogue_selection_changed)
        self.catalogue_list.itemDoubleClicked.connect(lambda _item: self.begin_catalogue_placement())
        self.catalogue_add_button.clicked.connect(self.begin_catalogue_placement)
        self._populate_catalogue()
        self.library_combo.currentTextChanged.connect(self._populate_product_library)
        self.library_family_combo.currentTextChanged.connect(self._populate_product_library)
        self.library_category_combo.currentTextChanged.connect(
            lambda _text: self._populate_product_library(update_categories=False)
        )
        self.library_list.currentItemChanged.connect(self._library_selection_changed)
        self.library_add_button.clicked.connect(self.begin_library_placement)
        self.library_create_button.clicked.connect(self.create_library_cabinet)
        self.library_edit_button.clicked.connect(self.edit_library_cabinet)
        self.library_remove_hardware_button.clicked.connect(self.remove_selected_hardware_assignment)
        self.library_list.itemDoubleClicked.connect(lambda _item: self.begin_library_placement())
        self._populate_product_library()
        self._sync_workspace_rail()

    def _navigate_workspace(self, page: QWidget, library: bool = False) -> None:
        self._rail_material_active = False
        self.workspace_tabs.setCurrentWidget(page)
        if page is self.workspace_splitter:
            self.explorer_tabs.setCurrentWidget(self.library_page if library else self.explorer_tabs.widget(0))
        self._sync_workspace_rail()

    def _navigate_rail(self, page: QWidget, icon_name: str) -> None:
        if icon_name == "project":
            self._rail_material_active = False
            self.workspace_tabs.setCurrentWidget(self.workspace_splitter)
            self.explorer_tabs.setCurrentWidget(self.project_tree)
        elif icon_name == "materials":
            self._rail_material_active = True
            self.workspace_tabs.setCurrentWidget(self.workspace_splitter)
            self.explorer_tabs.setCurrentWidget(self.explorer_tabs.widget(0))
            self._show_inspector_tab("material")
        else:
            self._navigate_workspace(page, library=icon_name == "library")
        self._sync_workspace_rail()

    def _sync_workspace_rail(self) -> None:
        if not hasattr(self, "rail_buttons"):
            return
        active = self.workspace_tabs.currentWidget()
        library_active = self.explorer_tabs.currentWidget() is self.library_page
        project_active = self.explorer_tabs.currentWidget() is self.project_tree
        for button, page, icon_name in self.rail_buttons:
            if page is not active:
                selected = False
            elif icon_name == "library":
                selected = library_active
            elif icon_name == "project":
                selected = project_active
            elif icon_name == "materials":
                selected = self._rail_material_active and not library_active and not project_active
            elif icon_name == "design":
                selected = not library_active
            else:
                selected = True
            button.setProperty("active", selected)
            rail_icon = {"library": "layers", "engineering": "gear"}.get(icon_name, icon_name)
            button.setIcon(outline_icon(rail_icon, "#FFFFFF" if selected else "#454C40"))
            if selected and button.graphicsEffect() is None:
                shadow = QGraphicsDropShadowEffect(button)
                shadow.setBlurRadius(15)
                shadow.setOffset(0, 3)
                shadow.setColor(QColor(62, 72, 51, 65))
                button.setGraphicsEffect(shadow)
            elif not selected and button.graphicsEffect() is not None:
                button.setGraphicsEffect(None)
            button.style().unpolish(button)
            button.style().polish(button)

    def _object_card_clicked(self, item: QListWidgetItem) -> None:
        if item.data(KIND_ROLE) == "section":
            if item.data(NAME_ROLE) == "Appliances":
                self._toggle_appliance_cards()
            return
        item_id = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(item_id, str):
            return
        if item_id.startswith("catalogue:"):
            type_id = item_id.split(":", 1)[1]
            self.library_combo.setCurrentText(APPLIANCES)
            for row in range(self.library_list.count()):
                if self.library_list.item(row).data(Qt.ItemDataRole.UserRole) == type_id:
                    self.library_list.setCurrentRow(row)
                    break
            self.explorer_tabs.setCurrentWidget(self.library_page)
        elif item_id.startswith("opening:"):
            self.select_opening(item_id.split(":", 1)[1])
        elif item_id.startswith("product:"):
            self.select_product(item_id.split(":", 1)[1])
        else:
            self.select_cabinet(item_id)

    def _toggle_cabinet_cards(self) -> None:
        self._cabinet_cards_collapsed = not self._cabinet_cards_collapsed
        self.cabinet_collapse_button.setText("⌄" if self._cabinet_cards_collapsed else "⌃")
        self.cabinet_collapse_button.setToolTip(
            "Expand cabinet cards" if self._cabinet_cards_collapsed else "Collapse cabinet cards"
        )
        for item in self._cabinet_card_items:
            item.setHidden(self._cabinet_cards_collapsed)

    def _toggle_appliance_cards(self) -> None:
        self._appliance_cards_collapsed = not self._appliance_cards_collapsed
        self.appliance_section_item.setData(EXPANDED_ROLE, not self._appliance_cards_collapsed)
        for item in self._appliance_card_items:
            item.setHidden(self._appliance_cards_collapsed)
        self.object_list.viewport().update()

    def _populate_product_library(self, *_args, update_categories: bool = True) -> None:
        library = self.library_combo.currentText()
        self.library_family_combo.setVisible(library == FURNITURE)
        self.library_list.clear()
        if library == FURNITURE:
            definitions = furniture_items(self.library_family_combo.currentText())
            rows = [(item.type_id, item.name, item.category, item.width, item.depth, item.height)
                    for item in definitions]
        else:
            rows = [(item.type_id, item.name, item.category, item.width, item.depth, item.height)
                    for item in products_for(library)]
        if update_categories:
            self.library_category_combo.blockSignals(True)
            self.library_category_combo.clear()
            self.library_category_combo.addItems(["All categories", *dict.fromkeys(row[2] for row in rows)])
            self.library_category_combo.blockSignals(False)
        selected_category = self.library_category_combo.currentText()
        if selected_category and selected_category != "All categories":
            rows = [row for row in rows if row[2] == selected_category]
        for type_id, name, category, width, depth, height in rows:
            pixmap = (catalogue_thumbnail(get_catalogue_item(type_id)) if library == FURNITURE
                      else product_thumbnail(get_product(type_id)))
            row = QListWidgetItem(QIcon(pixmap), f"{name}\n{category} · {width} × {depth} × {height} mm")
            row.setData(Qt.ItemDataRole.UserRole, type_id)
            row.setSizeHint(QSize(0, 58))
            row.setToolTip(f"{name}\n{category} · {width} × {depth} × {height} mm")
            self.library_list.addItem(row)
        if rows:
            self.library_list.setCurrentRow(0)
        self.library_add_button.setText("Assign to selected cabinet" if library == HARDWARE else "Place selected product in 2D")
        self.library_remove_hardware_button.setVisible(library == HARDWARE)
        self.library_create_button.setVisible(library == FURNITURE)
        self.library_edit_button.setVisible(library == FURNITURE)
        self.hardware_quantity_spin.setVisible(library == HARDWARE)
        self.hardware_quantity_label.setVisible(library == HARDWARE)

    def _library_selection_changed(self, current: QListWidgetItem | None, _previous=None) -> None:
        if current is None:
            self.library_description.clear()
            return
        library = self.library_combo.currentText()
        try:
            selected = (get_catalogue_item(current.data(Qt.ItemDataRole.UserRole))
                        if library == FURNITURE else get_product(current.data(Qt.ItemDataRole.UserRole)))
        except ValueError:
            # Category changes can briefly emit a selection signal for the old list.
            self.library_description.clear()
            return
        details = (f"{selected.name} · {selected.category}\n"
                   f"{selected.width} × {selected.depth} × {selected.height} mm\n")
        if library == PROPS:
            note = "Visual only · excluded from BOM, nesting, drilling and exports."
        elif library == HARDWARE:
            note = "Demo assignment to selected cabinet · existing BOM rules unchanged."
        elif library == APPLIANCES:
            note = "Sample product · commercial and manufacturing treatment requires client approval."
        else:
            definition = get_catalogue_item(current.data(Qt.ItemDataRole.UserRole))
            note = (f"Product {definition.product_id} · revision {definition.revision}. "
                    "Pricing is saved in Company Price Setup; existing projects keep their snapshots."
                    if definition.product_id else
                    "Furniture uses existing illustrative cabinet construction rules.")
        self.library_description.setText(details + note)

    def create_library_cabinet(self) -> None:
        self._edit_library_cabinet(None)

    def edit_library_cabinet(self) -> None:
        current = self.library_list.currentItem()
        if self.library_combo.currentText() != FURNITURE or current is None:
            QMessageBox.information(self, "Cabinet library", "Select a furniture cabinet first.")
            return
        self._edit_library_cabinet(get_catalogue_item(current.data(Qt.ItemDataRole.UserRole)))

    def _edit_library_cabinet(self, selected) -> None:
        item = None
        try:
            if self.custom_library_error:
                raise ValueError(f"Resolve the library file error before editing: {self.custom_library_error}")
            company = load_company_price_setup()
            previous_rule = next((rule for rule in company.catalogue_rules
                                  if selected and rule.type_id == selected.type_id), None)
            dialog = CabinetLibraryDialog(self.custom_library_items, company, selected, previous_rule, self)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            item, rule = dialog.build()
            register_custom_items([item])
            updated_company = deepcopy(company)
            updated_company.catalogue_rules.append(rule)
            validate_company_price_setup(updated_company)
            try:
                save_custom_catalogue([*self.custom_library_items, item])
                save_company_price_setup(updated_company)
            except (OSError, ValueError):
                save_custom_catalogue(self.custom_library_items)
                unregister_custom_item(item.type_id)
                raise
            self.custom_library_items.append(item)
            self._populate_product_library()
            for row in range(self.library_list.count()):
                if self.library_list.item(row).data(Qt.ItemDataRole.UserRole) == item.type_id:
                    self.library_list.setCurrentRow(row)
                    break
            self.statusBar().showMessage(
                f"Saved {item.product_id} revision {item.revision} with a {rule.status} Price Master rule. New projects copy it; existing projects remain unchanged."
            )
        except (OSError, ValueError, TypeError) as error:
            if item is not None and all(existing.type_id != item.type_id for existing in self.custom_library_items):
                unregister_custom_item(item.type_id)
            QMessageBox.warning(self, "Cabinet library", str(error))

    def _populate_catalogue(self, *_args) -> None:
        self.catalogue_list.clear()
        selected_category = self.catalogue_category_combo.currentText()
        categories = CATEGORIES if selected_category.startswith("All Furniture") else (selected_category,)
        first_product_row = -1
        for category in categories:
            if len(categories) > 1:
                heading = QListWidgetItem(category.upper())
                heading.setData(Qt.ItemDataRole.UserRole, None)
                heading.setFlags(Qt.ItemFlag.NoItemFlags)
                heading.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
                heading.setSizeHint(QSize(0, 30))
                self.catalogue_list.addItem(heading)
            for catalogue_item in catalogue_items(category):
                row = QListWidgetItem(
                    QIcon(catalogue_thumbnail(catalogue_item)),
                    f"{catalogue_item.name}\n{catalogue_item.category}  •  "
                    f"{catalogue_item.width} × {catalogue_item.height} × {catalogue_item.depth} mm",
                )
                row.setData(Qt.ItemDataRole.UserRole, catalogue_item.type_id)
                row.setToolTip(f"Add {catalogue_item.name} with its catalogue defaults")
                row.setSizeHint(QSize(0, 70))
                self.catalogue_list.addItem(row)
                if first_product_row < 0:
                    first_product_row = self.catalogue_list.count() - 1
        if first_product_row >= 0:
            self.catalogue_list.setCurrentRow(first_product_row)

    def _catalogue_selection_changed(self, current: QListWidgetItem | None, _previous=None) -> None:
        if current is None or not current.data(Qt.ItemDataRole.UserRole):
            self.catalogue_detail.clear()
            self.catalogue_add_button.setEnabled(False)
            return
        item = get_catalogue_item(current.data(Qt.ItemDataRole.UserRole))
        fronts = []
        if item.door_count:
            fronts.append(f"{item.door_count} door{'s' if item.door_count != 1 else ''}")
        if item.drawer_count:
            fronts.append(f"{item.drawer_count} drawers")
        fronts.append(f"{item.shelf_count} shelves")
        self.catalogue_detail.setText(
            f"{item.width} × {item.height} × {item.depth} mm\n" + " • ".join(fronts)
        )
        self.catalogue_add_button.setEnabled(len(self.project.cabinets) < MAX_CABINETS)

    @staticmethod
    def _spin(minimum: int, maximum: int, suffix: str = " mm") -> QSpinBox:
        spin = InspectorSpinBox()
        spin.setRange(minimum, maximum)
        spin.setSuffix(suffix)
        spin.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.PlusMinus)
        spin.setKeyboardTracking(False)
        return spin

    def _build_properties(self) -> None:
        self.properties_dock = QDockWidget("PROPERTIES / CONFIGURATION", self)
        self.properties_dock.setObjectName("propertiesDock")
        wrapper = QWidget()
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(12, 14, 12, 16)
        layout.setSpacing(9)
        eyebrow = QLabel("INSPECTOR")
        eyebrow.setObjectName("inspectorEyebrow")
        self.inspector_title = QLabel()
        self.inspector_title.setObjectName("inspectorTitle")
        self.inspector_subtitle = QLabel()
        self.inspector_subtitle.setObjectName("inspectorSubtitle")
        layout.addWidget(eyebrow)
        layout.addWidget(self.inspector_title)
        layout.addWidget(self.inspector_subtitle)
        self.inspector_title.hide()
        self.inspector_subtitle.hide()
        room_group = QGroupBox("Room")
        room_group.setObjectName("inspectorFormCard")
        self.room_group = room_group
        room_form = QFormLayout(room_group)
        room_form.setHorizontalSpacing(8)
        room_form.setVerticalSpacing(6)
        self.room_width_spin = self._spin(1200, 20000)
        self.room_depth_spin = self._spin(1200, 20000)
        self.room_height_spin = self._spin(2100, 5000)
        room_form.addRow("Width", self.room_width_spin)
        room_form.addRow("Depth", self.room_depth_spin)
        room_form.addRow("Wall height", self.room_height_spin)

        self.opening_group = QGroupBox("Room openings")
        self.opening_group.setObjectName("inspectorFormCard")
        opening_form = QFormLayout(self.opening_group)
        opening_form.setHorizontalSpacing(8)
        opening_form.setVerticalSpacing(6)
        self.opening_id_label = QLabel("None")
        self.opening_id_label.setObjectName("cabinetIdBadge")
        self.opening_kind_label = QLabel("—")
        self.opening_kind_label.setObjectName("inspectorObjectName")
        self.opening_wall_combo = QComboBox()
        for wall_id in WALL_IDS:
            self.opening_wall_combo.addItem(WALL_LABELS[wall_id], wall_id)
        self.opening_offset_spin = self._spin(0, 20000)
        self.opening_width_spin = self._spin(300, 3000)
        self.opening_height_spin = self._spin(300, 3000)
        self.opening_elevation_spin = self._spin(0, 5000)
        self.opening_swing_combo = QComboBox()
        self.opening_swing_combo.addItems(DOOR_SWINGS)
        opening_form.addRow("Opening ID", self.opening_id_label)
        opening_form.addRow("Type", self.opening_kind_label)
        opening_form.addRow("Wall", self.opening_wall_combo)
        opening_form.addRow("Offset", self.opening_offset_spin)
        opening_form.addRow("Width", self.opening_width_spin)
        opening_form.addRow("Height", self.opening_height_spin)
        opening_form.addRow("Elevation", self.opening_elevation_spin)
        opening_form.addRow("Door swing", self.opening_swing_combo)
        opening_buttons = QHBoxLayout()
        self.select_wall_button = QPushButton("Wall")
        self.select_wall_button.setToolTip("Select a wall in the 2D plan")
        self.add_door_button = QPushButton("+ Door")
        self.add_door_button.setToolTip("Place a door on the selected wall")
        self.add_window_button = QPushButton("+ Window")
        self.add_window_button.setToolTip("Place a window on the selected wall")
        opening_buttons.addWidget(self.select_wall_button)
        opening_buttons.addWidget(self.add_door_button)
        opening_buttons.addWidget(self.add_window_button)
        opening_form.addRow(opening_buttons)
        self.remove_opening_button = QPushButton("Remove Opening")
        opening_form.addRow(self.remove_opening_button)
        self.cabinet_group = QGroupBox()
        self.cabinet_group.setObjectName("selectedObjectGroup")
        cabinet_layout = QVBoxLayout(self.cabinet_group)
        cabinet_layout.setContentsMargins(0, 3, 0, 3)
        cabinet_layout.setSpacing(8)
        self.width_spin = self._spin(300, 3000)
        self.height_spin = self._spin(300, 3000)
        self.depth_spin = self._spin(200, 1200)
        for dimension_spin in (self.width_spin, self.height_spin, self.depth_spin):
            dimension_spin.setMinimumWidth(68)
            dimension_spin.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.thickness_spin = self._spin(10, 50)
        self.door_spin = self._spin(0, 6, "")
        self.drawer_spin = self._spin(0, 8, "")
        self.shelf_spin = self._spin(0, 10, "")
        self.material_combo = QComboBox()
        self.material_combo.addItems(MATERIALS)
        self.cabinet_id_label = QLabel()
        self.cabinet_id_label.setObjectName("cabinetIdBadge")
        self.cabinet_type_label = QLabel()
        self.cabinet_type_label.setObjectName("inspectorObjectName")
        self.cabinet_category_label = QLabel()
        self.cabinet_category_label.setWordWrap(True)
        self.cabinet_duplicate_button = QPushButton("Duplicate cabinet")
        self.position_x_spin = self._spin(0, 20000)
        self.position_y_spin = self._spin(0, 20000)
        self.inspector_identity = QFrame()
        self.inspector_identity.setObjectName("inspectorIdentity")
        identity_layout = QHBoxLayout(self.inspector_identity)
        identity_layout.setContentsMargins(11, 9, 11, 9)
        self.inspector_thumbnail = QLabel()
        self.inspector_thumbnail.setFixedSize(55, 55)
        self.inspector_thumbnail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.inspector_thumbnail.setObjectName("inspectorThumbnail")
        identity_layout.addWidget(self.inspector_thumbnail)
        identity_text = QVBoxLayout()
        identity_text.setSpacing(1)
        identity_text.addWidget(self.cabinet_type_label)
        identity_text.addWidget(self.cabinet_category_label)
        identity_layout.addLayout(identity_text, 1)
        identity_layout.addWidget(self.cabinet_id_label)
        layout.addWidget(self.inspector_identity)
        inspector_tabs = QFrame()
        inspector_tabs.setObjectName("inspectorTabs")
        tabs_layout = QHBoxLayout(inspector_tabs)
        tabs_layout.setContentsMargins(1, 0, 1, 0)
        tabs_layout.setSpacing(3)
        tab_buttons = []
        for caption in ("Properties", "Material", "Details"):
            tab_button = QToolButton()
            tab_button.setObjectName("inspectorTab")
            tab_button.setText(caption)
            tabs_layout.addWidget(tab_button, 1)
            tab_buttons.append(tab_button)
        cabinet_layout.addWidget(inspector_tabs)
        self.inspector_tabs = inspector_tabs
        self.inspector_tab_buttons = tab_buttons

        def section(title: str) -> tuple[QFrame, QGridLayout]:
            card = QFrame()
            card.setObjectName("inspectorCard")
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(11, 8, 11, 10)
            card_layout.setSpacing(6)
            heading = QLabel(title)
            heading.setObjectName("inspectorSection")
            card_layout.addWidget(heading)
            grid = QGridLayout()
            grid.setHorizontalSpacing(9)
            grid.setVerticalSpacing(8)
            card_layout.addLayout(grid)
            cabinet_layout.addWidget(card)
            return card, grid

        def field(grid: QGridLayout, row: int, column: int, label: QLabel | str, control: QWidget) -> QWidget:
            field_box = QWidget()
            field_layout = QVBoxLayout(field_box)
            field_layout.setContentsMargins(0, 0, 0, 0)
            field_layout.setSpacing(3)
            label_widget = label if isinstance(label, QLabel) else QLabel(label)
            label_widget.setObjectName("inspectorFieldLabel")
            field_layout.addWidget(label_widget)
            field_layout.addWidget(control)
            grid.addWidget(field_box, row, column)
            return field_box

        position_card, position_grid = section("POSITION")
        field(position_grid, 0, 0, "X · MM", self.position_x_spin)
        field(position_grid, 0, 1, "Y · MM", self.position_y_spin)
        self.dimensions_card, dimensions_grid = section("DIMENSIONS")
        field(dimensions_grid, 0, 0, "WIDTH · MM", self.width_spin)
        field(dimensions_grid, 0, 1, "HEIGHT · MM", self.height_spin)
        field(dimensions_grid, 0, 2, "DEPTH · MM", self.depth_spin)
        field(dimensions_grid, 1, 0, "BOARD · MM", self.thickness_spin)
        self.door_label = QLabel("Door count")
        self.drawer_label = QLabel("Drawer count")
        self.shelf_label = QLabel("Shelf count")
        configuration_card, configuration_grid = section("CONFIGURATION")
        self.door_field = field(configuration_grid, 0, 0, self.door_label, self.door_spin)
        self.drawer_field = field(configuration_grid, 0, 1, self.drawer_label, self.drawer_spin)
        self.shelf_field = field(configuration_grid, 1, 0, self.shelf_label, self.shelf_spin)
        self.configuration_grid = configuration_grid
        self.position_card = position_card
        self.configuration_card = configuration_card
        self.material_card, material_grid = section("MATERIAL / FINISH")
        finish_control = QWidget()
        finish_layout = QHBoxLayout(finish_control)
        finish_layout.setContentsMargins(0, 0, 0, 0)
        finish_layout.setSpacing(8)
        self.finish_swatch = QLabel()
        self.finish_swatch.setObjectName("finishSwatch")
        self.finish_swatch.setFixedSize(31, 31)
        finish_layout.addWidget(self.finish_swatch)
        finish_layout.addWidget(self.material_combo, 1)
        field(material_grid, 0, 0, "FINISH", finish_control)
        material_grid.addWidget(self.cabinet_duplicate_button, 1, 0)
        self.cabinet_duplicate_button.clicked.connect(self.duplicate_selected_object)
        self.placement_warning = QLabel()
        self.placement_warning.setObjectName("placementWarning")
        self.placement_warning.setWordWrap(True)
        self.placement_warning.hide()
        note = QLabel("Demo rules only — not factory approved")
        note.setWordWrap(True)
        note.setObjectName("warningLabel")
        layout.addWidget(self.opening_group)
        layout.addWidget(self.cabinet_group)
        self.product_group = QGroupBox("Selected library product")
        self.product_group.setObjectName("inspectorFormCard")
        product_form = QFormLayout(self.product_group)
        self.product_id_label = QLabel()
        self.product_name_label = QLabel()
        self.product_name_label.setObjectName("inspectorObjectName")
        self.product_rule_label = QLabel()
        self.product_rule_label.setWordWrap(True)
        self.product_rule_label.setMaximumWidth(210)
        self.product_x_spin = self._spin(0, 20000)
        self.product_y_spin = self._spin(0, 20000)
        self.product_z_spin = self._spin(0, 5000)
        self.product_width_spin = self._spin(20, 3000)
        self.product_depth_spin = self._spin(20, 3000)
        self.product_height_spin = self._spin(10, 3000)
        self.product_orientation_combo = QComboBox()
        for angle in (0, 90, 180, 270):
            self.product_orientation_combo.addItem(f"{angle}°", angle)
        self.product_orientation_label = QLabel("Rotation")
        self.product_remove_button = QPushButton("Remove selected product")
        self.product_duplicate_button = QPushButton("Duplicate product")
        product_form.addRow("Product ID", self.product_id_label)
        product_form.addRow("Model", self.product_name_label)
        product_form.addRow(self.product_rule_label)
        for label, control in (("Position X", self.product_x_spin), ("Position Y", self.product_y_spin),
                               ("Elevation Z", self.product_z_spin), ("Width", self.product_width_spin),
                               ("Depth", self.product_depth_spin), ("Height", self.product_height_spin)):
            product_form.addRow(label, control)
            control.valueChanged.connect(self._product_properties_changed)
        product_form.addRow(self.product_orientation_label, self.product_orientation_combo)
        self.product_orientation_combo.currentIndexChanged.connect(self._product_properties_changed)
        product_form.addRow(self.product_remove_button)
        product_form.addRow(self.product_duplicate_button)
        self.product_treatment_group = QGroupBox("Product treatment")
        treatment_form = QFormLayout(self.product_treatment_group)
        self.product_commercial_combo = QComboBox()
        self.product_commercial_combo.addItems(["Unpriced demo", "Client supplied"])
        self.product_manufacturing_combo = QComboBox()
        self.product_manufacturing_combo.addItems(["Review required", "Supplier supplied"])
        self.product_appearance_combo = QComboBox()
        self.product_appearance_combo.addItems(["Catalogue", *APPEARANCE_COLOURS])
        treatment_form.addRow("Commercial", self.product_commercial_combo)
        treatment_form.addRow("Manufacturing", self.product_manufacturing_combo)
        treatment_form.addRow("Appearance", self.product_appearance_combo)
        self.product_commercial_combo.currentTextChanged.connect(self._product_properties_changed)
        self.product_manufacturing_combo.currentTextChanged.connect(self._product_properties_changed)
        self.product_appearance_combo.currentTextChanged.connect(self._product_properties_changed)
        product_form.addRow(self.product_treatment_group)
        self.product_remove_button.clicked.connect(self.remove_selected_product)
        self.product_duplicate_button.clicked.connect(self.duplicate_selected_object)
        self.product_group.hide()
        layout.addWidget(self.product_group)
        layout.addWidget(room_group)
        layout.addWidget(self.placement_warning)
        layout.addWidget(note)
        layout.addStretch()
        scroll = QScrollArea()
        scroll.setObjectName("propertiesScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(wrapper)
        self.properties_scroll = scroll
        for button, tab_name in zip(tab_buttons, ("properties", "material", "details")):
            button.setProperty("current", button is tab_buttons[0])
            button.clicked.connect(lambda _checked=False, name=tab_name: self._show_inspector_tab(name))
        self._inspector_tab = "properties"
        self.properties_dock.setMinimumWidth(300)
        self.properties_dock.setTitleBarWidget(QWidget())
        self.properties_dock.setWidget(scroll)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.properties_dock)
        for spin in [self.room_width_spin, self.room_depth_spin, self.room_height_spin, self.width_spin, self.height_spin,
                     self.depth_spin, self.thickness_spin, self.door_spin, self.drawer_spin, self.shelf_spin,
                     self.position_x_spin, self.position_y_spin]:
            spin.valueChanged.connect(self._properties_changed)
        self.material_combo.currentTextChanged.connect(self._properties_changed)
        self.material_combo.currentTextChanged.connect(self._update_finish_swatch)
        self._update_finish_swatch(self.material_combo.currentText())
        for widget_signal in [
            self.opening_wall_combo.currentIndexChanged,
            self.opening_offset_spin.valueChanged,
            self.opening_width_spin.valueChanged,
            self.opening_height_spin.valueChanged,
            self.opening_elevation_spin.valueChanged,
            self.opening_swing_combo.currentIndexChanged,
        ]:
            widget_signal.connect(self._opening_properties_changed)
        self.select_wall_button.clicked.connect(self.begin_wall_selection)
        self.add_door_button.clicked.connect(lambda: self.begin_opening_placement("door"))
        self.add_window_button.clicked.connect(lambda: self.begin_opening_placement("window"))
        self.remove_opening_button.clicked.connect(self.remove_selected_opening)

    def _update_finish_swatch(self, finish: str) -> None:
        colour = FINISH_COLOURS.get(finish, "#BDB2A5")
        self.finish_swatch.setStyleSheet(
            f"background: {colour}; border: 1px solid #D9CFC3; border-radius: 7px;"
        )

    def _show_inspector_tab(self, name: str) -> None:
        """Switch the cabinet inspector without changing any project data."""
        self._inspector_tab = name
        for button in self.inspector_tab_buttons:
            current = button.text().lower() == name
            button.setProperty("current", current)
            button.style().unpolish(button)
            button.style().polish(button)
        self.position_card.setVisible(name == "properties")
        self.dimensions_card.setVisible(name == "properties")
        self.configuration_card.setVisible(name in ("properties", "details"))
        self.material_card.setVisible(name in ("properties", "material"))
        if name == "material":
            self.properties_scroll.ensureWidgetVisible(self.material_card)
        else:
            self.properties_scroll.verticalScrollBar().setValue(0)

    def _refresh_inspector_context(self) -> None:
        """Keep the visible editor and identity card aligned with the selected object."""
        opening = self.project.selected_opening
        product = next((item for item in self.project.placed_products
                        if item.item_id == self.selected_product_id), None)
        context = self._inspector_context
        if opening is not None:
            context = "opening"
        elif product is not None:
            context = "product"
        elif context not in ("room", "wall"):
            context = "cabinet"
        self.cabinet_group.setVisible(context == "cabinet" and self.project.selected_cabinet is not None)
        self.opening_group.setVisible(context == "opening")
        self.product_group.setVisible(context == "product")
        self.room_group.setVisible(context in ("room", "wall"))
        self.inspector_identity.setVisible(context != "cabinet" or self.project.selected_cabinet is not None)
        if context == "cabinet" and self.project.selected_cabinet is not None:
            cabinet = self.project.selected_cabinet
            definition = get_catalogue_item(cabinet.cabinet_type_id)
            self.cabinet_id_label.setText(cabinet.cabinet_id)
            self.cabinet_type_label.setText(definition.name)
            self.cabinet_category_label.setText(f"{definition.category} · {cabinet.material}")
            self.inspector_thumbnail.setPixmap(catalogue_thumbnail(definition, cabinet.material).scaled(
                52, 52, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        elif context == "product" and product is not None:
            definition = get_product(product.type_id)
            self.cabinet_id_label.setText(product.item_id)
            self.cabinet_type_label.setText(definition.name)
            self.cabinet_category_label.setText(definition.library)
            self.inspector_thumbnail.setPixmap(product_thumbnail(definition).scaled(
                52, 52, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        else:
            if context == "opening" and opening is not None:
                title, detail, badge, icon = (opening.kind.title(),
                    f"{WALL_LABELS[opening.wall_id]} · {opening.width} × {opening.height} mm",
                    opening.opening_id, "front" if opening.kind == "door" else "grid")
            elif context == "wall":
                title, detail, badge, icon = (WALL_LABELS[self.selected_wall_id],
                    f"Room wall · {wall_length(self.project.room, self.selected_wall_id)} mm",
                    self.selected_wall_id, "layers")
            else:
                title, detail, badge, icon = ("Room", f"{self.project.room.width} × {self.project.room.depth} mm",
                    "ROOM", "plan")
            self.cabinet_id_label.setText(badge)
            self.cabinet_type_label.setText(title)
            self.cabinet_category_label.setText(detail)
            self.inspector_thumbnail.setPixmap(outline_icon(icon, "#8C6546").pixmap(38, 38))

    def _build_bom(self) -> None:
        self.bom_dock = QDockWidget("COMPONENTS & BILL OF MATERIALS", self)
        self.bom_dock.setObjectName("bomDock")
        self.bom_dock.setMinimumHeight(140)
        self.bom_table = QTableWidget(0, 8)
        self.bom_table.setHorizontalHeaderLabels(["Component", "Length", "Width", "Thickness", "Material", "Qty", "Cabinet ID", "Furniture Type"])
        self.bom_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.bom_table.setAlternatingRowColors(True)
        self.bom_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.bom_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.bom_table.setShowGrid(False)
        self.bom_table.setWordWrap(False)
        self.bom_table.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.bom_table.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.bom_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.bom_table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.bom_table.verticalHeader().setVisible(False)
        self.bom_table.verticalHeader().setDefaultSectionSize(26)
        header = self.bom_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.Stretch)
        for column, width in enumerate([200, 105, 105, 110, 150, 55, 75, 210]):
            self.bom_table.setColumnWidth(column, width)
        self.bom_dock.setWidget(self.bom_table)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.bom_dock)

    def _build_status_bar(self) -> None:
        status = self.statusBar()
        status.setSizeGripEnabled(True)
        self.status_project_label = QLabel()
        self.status_project_label.setObjectName("statusContext")
        self.status_demo_label = QLabel("CLIENT DEMO v1.0.1 • MM")
        self.status_demo_label.setObjectName("statusBadge")
        status.addPermanentWidget(self.status_project_label)
        status.addPermanentWidget(self.status_demo_label)

    def eventFilter(self, watched, event) -> bool:  # noqa: N802 - Qt API
        if watched is getattr(self, "design_header", None) and event.type() == QEvent.Type.Resize:
            compact = event.size().width() < 800
            for button, normal, small in (
                (self.technical_view_button, 164, 110),
                (self.plan_toggle_button, 174, 110),
                (self.presentation_mode_button, 190, 132),
            ):
                desired = small if compact else normal
                if button.width() != desired:
                    button.setFixedWidth(desired)
        if watched is getattr(self, "design_tools", None) and event.type() == QEvent.Type.Resize:
            show_optional = event.size().width() >= 840
            for caption in ("Snap", "Grid", "Interior", "Max"):
                button = self.design_tool_buttons[caption]
                if button.isHidden() == show_optional:
                    button.setVisible(show_optional)
        delete_targets = {
            getattr(self, "plan_view", None),
            getattr(getattr(self, "plan_view", None), "viewport", lambda: None)(),
            getattr(self, "project_tree", None),
            getattr(getattr(self, "project_tree", None), "viewport", lambda: None)(),
        }
        if (
            watched in delete_targets
            and event.type() == QEvent.Type.KeyPress
            and event.key() in (
                (Qt.Key.Key_Delete, Qt.Key.Key_Backspace) if is_macos() else (Qt.Key.Key_Delete,)
            )
        ):
            self.remove_selected_object()
            event.accept()
            return True
        return super().eventFilter(watched, event)

    def _set_presentation_view(self, enabled: bool) -> None:
        if self.presentation_view_action.isChecked() != enabled:
            self.presentation_view_action.blockSignals(True)
            self.presentation_view_action.setChecked(enabled)
            self.presentation_view_action.blockSignals(False)
        if hasattr(self, "presentation_mode_button"):
            self.presentation_mode_button.setChecked(enabled)
            self.technical_view_button.setChecked(not self.design_stage.plan_expanded)
        self.presentation_camera_action.setEnabled(enabled)
        self.hide_room_walls_action.setEnabled(enabled)
        self.view3d.set_presentation_mode(enabled)
        mode = "Presentation View" if enabled else "Technical CAD View"
        self.statusBar().showMessage(f"{mode} active — project and manufacturing data unchanged")

    def show_manufacturing_preview(self) -> None:
        self.manufacturing_preview.set_cabinet(self.project.selected_cabinet, force=True)
        self.workspace_tabs.setCurrentWidget(self.manufacturing_preview)
        if self.project.selected_cabinet is None:
            self.statusBar().showMessage("Manufacturing Preview — add and select a cabinet to inspect components")
        else:
            self.statusBar().showMessage(
                f"Manufacturing Preview — selected cabinet {self.project.selected_cabinet_id}; demo rules only"
            )

    def show_sheet_nesting(self) -> None:
        self.sheet_nesting.set_project(self.project, force=True)
        self.workspace_tabs.setCurrentWidget(self.sheet_nesting)
        self.statusBar().showMessage(
            "Sheet Nesting — deterministic demonstration layout; not approved for factory use"
        )

    def show_documents(self) -> None:
        self.documents_workspace.set_project(self.project)
        self.workspace_tabs.setCurrentWidget(self.documents_workspace)
        self.statusBar().showMessage("Review illustrative BOM and automatically resolved draft prices; incomplete pricing is flagged")

    def show_company_price_setup(self) -> None:
        try:
            dialog = CompanyPriceSetupDialog(self)
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, "Company Price Setup", str(error))
            return
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.statusBar().showMessage("Company Price Setup saved locally; new projects use a copy. Existing projects remain unchanged.")

    def refresh_company_prices(self) -> None:
        try:
            preview = preview_company_price_refresh(self.project, load_company_price_setup())
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, "Company Price Refresh", str(error))
            return
        dialog = PricingRefreshDialog(preview, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            self.statusBar().showMessage("Company price refresh cancelled; project pricing unchanged")
            return
        try:
            apply_company_price_refresh(self.project, preview)
        except ValueError as error:
            QMessageBox.warning(self, "Company Price Refresh", str(error))
            return
        self._set_dirty(True)
        self.refresh_all()
        self.statusBar().showMessage(
            f"Applied company pricing revision {preview.source_revision}; draft recalculated, issued snapshot preserved")

    def show_ai_design(self) -> None:
        self.workspace_tabs.setCurrentWidget(self.ai_design_workspace)
        self.statusBar().showMessage("Design Assistant — proposals are previews until explicitly applied")

    def show_realistic_rendering(self) -> None:
        self.realistic_render_workspace.refresh_provider_status()
        captured = self.realistic_render_workspace.capture()
        self.workspace_tabs.setCurrentWidget(self.realistic_render_workspace)
        self.statusBar().showMessage(
            "Standard 3D capture ready; AI rendering requires an approved configured service"
            if captured else "3D capture unavailable; open Design Studio and try Capture current 3D"
        )

    def _capture_render_scene(self, camera: str) -> bytes:
        previous = self.workspace_tabs.currentWidget()
        temporary_presentation = camera == "Presentation" and not self.view3d.presentation_mode
        previous_camera = self.view3d.plotter.camera_position if temporary_presentation else None
        previous_angle = self.view3d.plotter.camera.view_angle if temporary_presentation else None
        if previous is not self.workspace_splitter:
            self.workspace_tabs.setCurrentWidget(self.workspace_splitter)
            QApplication.processEvents()
        try:
            if temporary_presentation:
                self.view3d.set_presentation_mode(True)
            return capture_view_png(self.view3d, camera)
        finally:
            if temporary_presentation:
                self.view3d.set_presentation_mode(False)
                self.view3d.plotter.camera_position = previous_camera
                self.view3d.plotter.camera.view_angle = previous_angle
                self.view3d.plotter.render()
            if previous is not self.workspace_splitter:
                self.workspace_tabs.setCurrentWidget(previous)

    def generate_design_proposal(self, prompt: str, mode: str = "replace") -> DesignProposal | None:
        fallback_warning = None
        try:
            provider = configured_provider()
            intent = provider.interpret(prompt, self.project)
        except (RuntimeError, ValueError) as error:
            provider = LocalRuleBasedProvider()
            intent = provider.interpret(prompt, self.project)
            fallback_warning = f"Configured service unavailable or invalid; using local rule-based demo. {error}"
        try:
            proposal = build_proposal(
                self.project, intent, source=provider.name, mode=mode,
                allow_reposition=isinstance(provider, LocalRuleBasedProvider),
            )
        except ValueError as error:
            self.pending_design_proposal = None
            self.ai_design_workspace.clear_proposal(f"Could not build proposal: {error}")
            self.statusBar().showMessage(str(error))
            return None
        if fallback_warning:
            proposal.warnings = (fallback_warning, *proposal.warnings)
        self.pending_design_proposal = proposal
        self.ai_design_workspace.show_proposal(proposal)
        self.statusBar().showMessage(
            f"{provider.name}: {len(proposal.items)} validated item(s); project unchanged"
        )
        return proposal

    def reject_design_proposal(self) -> None:
        self.pending_design_proposal = None
        self.ai_design_workspace.clear_proposal()
        self.statusBar().showMessage("Design proposal rejected; project unchanged")

    def _apply_design_snapshot(self, snapshot: Project) -> None:
        snapshot.validate()
        self.project = deepcopy(snapshot)
        self.selected_product_id = None
        self.selected_hardware_assignment_id = None
        self._set_dirty(True)
        self.refresh_all(reset_camera=True)
        self.view3d.fit_all_cabinets()

    def apply_design_proposal(self) -> bool:
        proposal = self.pending_design_proposal
        if proposal is None or not proposal.can_apply:
            self.statusBar().showMessage("Generate a valid design proposal first")
            return False
        if project_fingerprint(self.project) != proposal.base_fingerprint:
            self.reject_design_proposal()
            self.statusBar().showMessage("Project changed after generation; regenerate the proposal")
            return False
        if proposal.mode == "replace" and (self.project.cabinets or self.project.placed_products):
            answer = QMessageBox.question(
                self, "Replace current layout?",
                "Applying this proposal will replace the current furniture and placed products. "
                "The room and openings remain. You can Undo this change.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                self.statusBar().showMessage("Proposal not applied; existing layout preserved")
                return False
        proposal.after_project.validate()
        self.pending_design_proposal = None
        self.undo_stack.push(ApplyDesignProposalCommand(
            self.project, proposal.after_project, self._apply_design_snapshot
        ))
        self.ai_design_workspace.clear_proposal("Proposal applied. Edit furniture in the 2D Design Studio.")
        self.workspace_tabs.setCurrentIndex(0)
        self.statusBar().showMessage("Validated design applied; edit in 2D or use Undo")
        return True

    def _workspace_changed(self, index: int) -> None:
        self._sync_workspace_rail()
        if hasattr(self, "header_workspace_caption"):
            caption = self.workspace_tabs.tabText(index).upper()
            short_caption = {
                "MANUFACTURING PREVIEW": "ENGINEERING",
                "BOM & QUOTATION": "BOM & QUOTE",
                "DESIGN ASSISTANT": "DESIGN ASSIST",
                "REALISTIC RENDERING": "AI RENDERING",
            }.get(caption, caption)
            self.header_workspace_caption.setText(short_caption)
            self.header_workspace_caption.setToolTip(caption)
        engineering_active = index == self.workspace_tabs.indexOf(self.manufacturing_preview)
        nesting_active = index == self.workspace_tabs.indexOf(self.sheet_nesting)
        documents_active = index == self.workspace_tabs.indexOf(self.documents_workspace)
        design_assistant_active = index == self.workspace_tabs.indexOf(self.ai_design_workspace)
        rendering_active = index == self.workspace_tabs.indexOf(self.realistic_render_workspace)
        auxiliary_active = engineering_active or nesting_active or documents_active or design_assistant_active or rendering_active
        if auxiliary_active and self.maximize_3d_action.isChecked():
            self.maximize_3d_action.setChecked(False)
        self.maximize_3d_action.setEnabled(not auxiliary_active)
        if auxiliary_active:
            if not self._engineering_restore_docks:
                self._engineering_restore_docks = {
                    dock: dock.isVisible() for dock in (self.properties_dock, self.bom_dock)
                }
            self.properties_dock.hide()
            self.bom_dock.hide()
            if engineering_active:
                self.manufacturing_preview.set_cabinet(self.project.selected_cabinet, force=True)
                if self.project.selected_cabinet is None:
                    self.statusBar().showMessage("Manufacturing Preview — no cabinet selected")
                else:
                    self.statusBar().showMessage(
                        f"Engineering feasibility preview for {self.project.selected_cabinet_id} — not approved for production"
                    )
            elif nesting_active:
                self.sheet_nesting.set_project(self.project)
                self.statusBar().showMessage(
                    "Demonstration sheet nesting — click Recalculate after project changes"
                )
            elif documents_active:
                self.documents_workspace.set_project(self.project)
                self.statusBar().showMessage("BOM and quotation review — illustrative quantities and resolved draft prices")
            elif design_assistant_active:
                self.statusBar().showMessage("Design Assistant — local proposal preview; project unchanged")
            elif rendering_active:
                self.statusBar().showMessage("Realistic Rendering — 3D capture is separate from project data")
        else:
            for dock, was_visible in self._engineering_restore_docks.items():
                dock.setVisible(was_visible)
            self._engineering_restore_docks.clear()
            self.statusBar().showMessage("Design Studio active")

    def _set_3d_maximized(self, enabled: bool) -> None:
        if not hasattr(self, "workspace_splitter") or enabled == self._workspace_3d_maximized:
            return
        self._workspace_3d_maximized = enabled
        if enabled:
            self._workspace_restore_sizes = self.workspace_splitter.sizes()
            self._workspace_restore_docks = {
                dock: dock.isVisible()
                for dock in (self.explorer_dock, self.properties_dock, self.bom_dock)
            }
            self.plan_panel.hide()
            for dock in self._workspace_restore_docks:
                dock.hide()
            self.maximize_3d_action.setText("Restore Workspace")
            self.maximize_3d_action.setIconText("Restore")
            self.maximize_3d_action.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_TitleBarNormalButton))
            self.statusBar().showMessage("3D viewport maximized — use Restore Workspace or Ctrl+Shift+3 to return")
        else:
            self.plan_panel.show()
            for dock, was_visible in self._workspace_restore_docks.items():
                dock.setVisible(was_visible)
            self.workspace_splitter.setSizes(self._workspace_restore_sizes)
            self.maximize_3d_action.setText("Maximize 3D")
            self.maximize_3d_action.setIconText("Max 3D")
            self.maximize_3d_action.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_TitleBarMaxButton))
            self.statusBar().showMessage("Split 2D / 3D workspace restored")
        if self.view3d.presentation_mode:
            self.view3d.view_presentation()
        else:
            self.view3d.fit_all_cabinets()

    def _update_snap_options(self, *_args) -> None:
        if not hasattr(self, "plan_view"):
            return
        self.plan_view.set_snap_options(
            snap_enabled=self.snap_action.isChecked(),
            grid_enabled=self.grid_snap_action.isChecked(),
        )
        state = "on" if self.snap_action.isChecked() else "off"
        self.statusBar().showMessage(f"Placement snapping {state}; grid is {'on' if self.grid_snap_action.isChecked() else 'off'}")

    def begin_wall_selection(self) -> None:
        self.plan_view.begin_wall_selection()
        self.statusBar().showMessage("Select one of the four room walls in the 2D plan; Esc cancels")

    def select_room_for_inspector(self) -> None:
        self._inspector_context = "room"
        self.selected_product_id = None
        self.project.select_opening(None)
        self.refresh_visuals(reset_camera=False)
        self.statusBar().showMessage("Selected room dimensions")

    def select_wall(self, wall_id: str) -> None:
        if wall_id not in WALL_IDS:
            return
        self._inspector_context = "wall"
        self.selected_wall_id = wall_id
        self.selected_product_id = None
        self.project.select_opening(None)
        self._load_opening_controls()
        self.refresh_visuals(reset_camera=False)
        self.statusBar().showMessage(f"Selected {WALL_LABELS[wall_id]}")

    def begin_opening_placement(self, kind: str) -> None:
        self.plan_view.begin_opening_placement(kind, self.selected_wall_id)
        self.statusBar().showMessage(
            f"Place {kind} on {self.selected_wall_id}: move along the wall, click to commit, Esc to cancel"
        )

    def _opening_defaults(self, kind: str, wall_id: str, offset: int) -> Opening:
        return Opening(
            self.project.next_opening_id(kind), kind, wall_id, offset,
            900 if kind == "door" else 1200,
            2100 if kind == "door" else 1000,
            0 if kind == "door" else 1000,
            "Left In",
        )

    def _place_opening(self, kind: str, wall_id: str, offset: int) -> None:
        try:
            opening = self._opening_defaults(kind, wall_id, offset)
            self.project.validate_opening(opening)
            self.plan_view.cancel_interaction(emit_signal=False)
            self.undo_stack.push(OpeningChangeCommand(
                opening.opening_id, None, opening, self._apply_opening_state, f"Add {opening.opening_id}"
            ))
        except ValueError as error:
            self._show_placement_error(error)

    def _apply_opening_state(self, opening_id: str, state: Opening | None) -> None:
        existing = next((item for item in self.project.room.openings if item.opening_id == opening_id), None)
        if state is None:
            if existing is not None:
                self.project.remove_opening(opening_id)
        elif existing is None:
            self.project.add_opening(state)
        else:
            self.project.replace_opening(state)
        if state is not None:
            self.project.select_opening(opening_id)
            self.selected_wall_id = state.wall_id
            self._inspector_context = "opening"
        elif self._inspector_context == "opening":
            self._inspector_context = "room"
        self._set_dirty(True)
        self.refresh_all(reset_camera=False)

    def select_opening(self, opening_id: str) -> None:
        try:
            opening = self.project.select_opening(opening_id)
        except ValueError as error:
            self.statusBar().showMessage(str(error))
            return
        self.selected_wall_id = opening.wall_id
        self._inspector_context = "opening"
        self.selected_product_id = None
        self._load_opening_controls()
        self.refresh_visuals(reset_camera=False)
        self.statusBar().showMessage(f"Selected {opening.kind} {opening.opening_id} on {opening.wall_id}")

    def move_opening(self, opening_id: str, offset: int) -> None:
        before = deepcopy(next(item for item in self.project.room.openings if item.opening_id == opening_id))
        if before.offset == offset:
            return
        after = deepcopy(before)
        after.offset = offset
        try:
            self.project.validate_opening(after)
        except ValueError as error:
            self._show_placement_error(error)
            return
        self.undo_stack.push(OpeningChangeCommand(
            opening_id, before, after, self._apply_opening_state, f"Move {opening_id}", merge_moves=True
        ))

    def focus_opening_properties(self) -> None:
        if self.project.selected_opening is None:
            self.statusBar().showMessage("Select a door or window in the plan or project tree first")
            return
        self.properties_dock.raise_()
        self.opening_offset_spin.setFocus()

    def remove_selected_opening(self) -> None:
        opening = self.project.selected_opening
        if opening is None:
            self.statusBar().showMessage("No room opening is selected")
            return
        self.undo_stack.push(OpeningChangeCommand(
            opening.opening_id, opening, None, self._apply_opening_state, f"Remove {opening.opening_id}"
        ))

    def _opening_properties_changed(self, *_args) -> None:
        if self._updating_opening_controls or self.project.selected_opening is None:
            return
        before = deepcopy(self.project.selected_opening)
        after = deepcopy(before)
        after.wall_id = self.opening_wall_combo.currentData()
        after.offset = self.opening_offset_spin.value()
        after.width = self.opening_width_spin.value()
        after.height = self.opening_height_spin.value()
        after.elevation = self.opening_elevation_spin.value()
        after.swing = self.opening_swing_combo.currentText()
        if after == before:
            return
        try:
            self.project.validate_opening(after)
        except ValueError as error:
            self._show_placement_error(error)
            self._load_opening_controls()
            return
        self.undo_stack.push(OpeningChangeCommand(
            after.opening_id, before, after, self._apply_opening_state, f"Edit {after.opening_id}"
        ))

    def _show_placement_error(self, error: Exception) -> None:
        self.placement_warning.setText(str(error))
        self.placement_warning.show()
        self.statusBar().showMessage(str(error))

    def _properties_changed(self, *_args) -> None:
        if self._updating_controls:
            return
        candidate_project = deepcopy(self.project)
        try:
            candidate_project.room.width = self.room_width_spin.value()
            candidate_project.room.depth = self.room_depth_spin.value()
            candidate_project.room.height = self.room_height_spin.value()
            selected = candidate_project.selected_cabinet
            if selected is not None:
                selected.width = self.width_spin.value()
                selected.height = self.height_spin.value()
                selected.depth = self.depth_spin.value()
                selected.board_thickness = self.thickness_spin.value()
                selected.door_count = self.door_spin.value()
                selected.drawer_count = self.drawer_spin.value()
                selected.shelf_count = self.shelf_spin.value()
                selected.material = self.material_combo.currentText()
                selected.position_x = self.position_x_spin.value()
                selected.position_y = self.position_y_spin.value()
                candidate_project.validate_cabinet_placement(selected)
            candidate_project.validate()
            current = self.project.selected_cabinet
            if selected is None or current is None:
                self.project = candidate_project
                self._set_dirty(True)
                self.placement_warning.hide()
                self.refresh_visuals()
                self.statusBar().showMessage(
                    f"Updated room: {candidate_project.room.width} × {candidate_project.room.depth} mm"
                )
                return
            old_non_position = {key: value for key, value in current.__dict__.items() if key not in ("position_x", "position_y")}
            new_non_position = {key: value for key, value in selected.__dict__.items() if key not in ("position_x", "position_y")}
            position_changed = (current.position_x, current.position_y) != (selected.position_x, selected.position_y)
            room_unchanged = self.project.room == candidate_project.room
            if position_changed and room_unchanged and old_non_position == new_non_position:
                self.undo_stack.push(MoveCabinetCommand(
                    current.cabinet_id,
                    (current.position_x, current.position_y),
                    (selected.position_x, selected.position_y),
                    self._apply_cabinet_position,
                ))
                return
            self.project = candidate_project
            self._set_dirty(True)
            self.placement_warning.hide()
            self.refresh_visuals()
            self.statusBar().showMessage(
                f"Updated {selected.cabinet_id}: {selected.width} × {selected.height} × {selected.depth} mm"
            )
        except ValueError as error:
            self.placement_warning.setText(str(error))
            self.placement_warning.show()
            self.statusBar().showMessage(str(error))
            self._load_selected_controls()

    def _apply_cabinet_position(self, cabinet_id: str, x: int, y: int) -> None:
        cabinet = self.project.select_cabinet(cabinet_id)
        cabinet.position_x, cabinet.position_y = x, y
        self.project.validate_cabinet_placement(cabinet)
        self._set_dirty(True)
        self.refresh_all(reset_camera=False)
        self.statusBar().showMessage(f"Moved {cabinet_id} to X {x} mm, Y {y} mm")

    def move_cabinet(self, cabinet_id: str, x: int, y: int) -> None:
        cabinet = next((item for item in self.project.cabinets if item.cabinet_id == cabinet_id), None)
        if cabinet is None:
            self.statusBar().showMessage(f"Cabinet {cabinet_id!r} does not exist")
            return
        if (cabinet.position_x, cabinet.position_y) == (x, y):
            return
        candidate = deepcopy(cabinet)
        candidate.position_x, candidate.position_y = x, y
        try:
            self.project.validate_cabinet_placement(candidate)
        except ValueError as error:
            self.placement_warning.setText(str(error))
            self.placement_warning.show()
            self.statusBar().showMessage(str(error))
            return
        self.undo_stack.push(MoveCabinetCommand(
            cabinet_id,
            (cabinet.position_x, cabinet.position_y),
            (x, y),
            self._apply_cabinet_position,
        ))

    def _load_selected_controls(self) -> None:
        self._updating_controls = True
        room, cabinet = self.project.room, self.project.selected_cabinet
        self.room_width_spin.setValue(room.width)
        self.room_depth_spin.setValue(room.depth)
        self.room_height_spin.setValue(room.height)
        self.cabinet_group.setEnabled(cabinet is not None)
        if cabinet is None:
            self.cabinet_id_label.setText("None")
            self.inspector_thumbnail.clear()
            self.cabinet_type_label.setText("Add furniture from the Catalogue")
            self.cabinet_category_label.setText("—")
            self.cabinet_group.setTitle("")
            self._updating_controls = False
            self._load_opening_controls()
            return
        self.width_spin.setValue(cabinet.width)
        self.height_spin.setValue(cabinet.height)
        self.depth_spin.setValue(cabinet.depth)
        self.thickness_spin.setValue(cabinet.board_thickness)
        self.door_spin.setValue(cabinet.door_count)
        self.drawer_spin.setValue(cabinet.drawer_count)
        self.shelf_spin.setValue(cabinet.shelf_count)
        if self.material_combo.findText(cabinet.material) < 0:
            # Preserve exact finish names stored by v0.4 projects.
            self.material_combo.addItem(cabinet.material)
        self.material_combo.setCurrentText(cabinet.material)
        self.position_x_spin.setMaximum(max(0, room.width - 300))
        self.position_y_spin.setMaximum(max(0, room.depth - 200))
        self.position_x_spin.setValue(cabinet.position_x)
        self.position_y_spin.setValue(cabinet.position_y)
        self.cabinet_id_label.setText(cabinet.cabinet_id)
        catalogue_item = get_catalogue_item(cabinet.cabinet_type_id)
        self.inspector_thumbnail.setPixmap(
            catalogue_thumbnail(catalogue_item, cabinet.material).scaled(
                49, 49, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
            )
        )
        self.cabinet_type_label.setText(catalogue_item.name)
        self.cabinet_category_label.setText(catalogue_item.category)
        shows_doors = catalogue_item.front_style not in ("drawers", "open")
        shows_drawers = catalogue_item.front_style == "drawers"
        shows_shelves = catalogue_item.front_style != "sink"
        for field_box, visible in ((self.door_field, shows_doors),
                                   (self.drawer_field, shows_drawers),
                                   (self.shelf_field, shows_shelves)):
            field_box.setVisible(visible)
        self.configuration_grid.removeWidget(self.shelf_field)
        self.configuration_grid.addWidget(self.shelf_field, 0, 1 if not shows_drawers else 1)
        self.cabinet_group.setTitle("")
        self._updating_controls = False
        self._load_opening_controls()

    def _load_opening_controls(self) -> None:
        if not hasattr(self, "opening_group"):
            return
        self._updating_opening_controls = True
        opening = self.project.selected_opening
        enabled = opening is not None
        self.opening_group.setVisible(enabled)
        self.cabinet_group.setVisible(not enabled)
        for widget in (
            self.opening_wall_combo, self.opening_offset_spin, self.opening_width_spin,
            self.opening_height_spin, self.opening_elevation_spin, self.opening_swing_combo,
        ):
            widget.setEnabled(enabled)
        self.remove_opening_button.setEnabled(enabled)
        self.edit_opening_action.setEnabled(enabled)
        self.remove_opening_action.setEnabled(enabled)
        if opening is None:
            self.opening_group.setTitle(f"Room openings — wall {self.selected_wall_id}")
            self.opening_id_label.setText("None")
            self.opening_kind_label.setText("Select or add an opening")
            self.opening_wall_combo.setCurrentIndex(self.opening_wall_combo.findData(self.selected_wall_id))
            self.opening_swing_combo.setVisible(False)
        else:
            self.opening_group.setTitle(f"Selected opening — {opening.opening_id}")
            self.opening_id_label.setText(opening.opening_id)
            self.opening_kind_label.setText(opening.kind.title())
            self.opening_wall_combo.setCurrentIndex(self.opening_wall_combo.findData(opening.wall_id))
            self.opening_offset_spin.setMaximum(max(0, wall_length(self.project.room, opening.wall_id) - 300))
            self.opening_offset_spin.setValue(opening.offset)
            self.opening_width_spin.setValue(opening.width)
            self.opening_height_spin.setValue(opening.height)
            self.opening_elevation_spin.setMaximum(self.project.room.height - 300)
            self.opening_elevation_spin.setValue(opening.elevation)
            self.opening_swing_combo.setCurrentText(opening.swing)
            self.opening_swing_combo.setVisible(opening.kind == "door")
        self._updating_opening_controls = False

    def refresh_all(self, reset_camera: bool = False) -> None:
        if (self.pending_design_proposal is not None
                and project_fingerprint(self.project) != self.pending_design_proposal.base_fingerprint):
            self.pending_design_proposal = None
            self.ai_design_workspace.clear_proposal("Project changed; regenerate the design proposal.")
        if not any(item.item_id == self.selected_product_id for item in self.project.placed_products):
            self.selected_product_id = None
        if not any(item.assignment_id == self.selected_hardware_assignment_id for item in self.project.hardware_assignments):
            self.selected_hardware_assignment_id = None
        self._load_selected_controls()
        self.placement_warning.hide()
        self.status_project_label.setText(f"{self.project.name}  •  {self.project.project_type}")
        self._refresh_design_labels()
        self.refresh_visuals(reset_camera)

    def _set_dirty(self, dirty: bool) -> None:
        self._dirty = dirty
        title = "kuchhe7 — Kitchen Design & Manufacturing Platform | AIZ INFOTECHS"
        self.setWindowTitle(f"{title}{' *' if dirty else ''}")
        if hasattr(self, "header_dirty_label"):
            self.header_dirty_label.setText("Unsaved changes" if dirty else "All changes saved")
            self.header_dirty_label.setProperty("dirty", dirty)
            self.header_dirty_label.style().unpolish(self.header_dirty_label)
            self.header_dirty_label.style().polish(self.header_dirty_label)
            self.header_saved_icon.setPixmap(top_label_pixmap(
                "unsaved" if dirty else "saved", "#9A6237" if dirty else "#446449"
            ))

    def _confirm_replace_unsaved(self, target_name: str = "sample kitchen") -> bool:
        if not self._dirty:
            return True
        answer = QMessageBox.question(
            self,
            "Unsaved project changes",
            f"Opening the {target_name} will replace the current unsaved project.",
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer == QMessageBox.StandardButton.Save:
            self.save_project()
            return not self._dirty
        # Preserve compatibility with integrations that mocked the former Yes/No prompt.
        return answer in (QMessageBox.StandardButton.Discard, QMessageBox.StandardButton.Yes)

    def refresh_visuals(self, reset_camera: bool = False) -> None:
        self.plan_view.redraw(
            self.project.room,
            self.project.cabinets,
            None if self.selected_product_id else self.project.selected_cabinet_id,
            self.project.selected_opening_id,
            self.selected_wall_id,
            self.project.placed_products,
            self.selected_product_id,
        )
        self.view3d.update_scene(
            self.project.room,
            self.project.cabinets,
            None if self.selected_product_id else self.project.selected_cabinet_id,
            reset_camera,
            placed_products=self.project.placed_products,
            selected_product_id=self.selected_product_id,
        )
        self._load_product_controls()
        if hasattr(self, "manufacturing_preview"):
            self.manufacturing_preview.set_cabinet(self.project.selected_cabinet)
        if hasattr(self, "sheet_nesting"):
            self.sheet_nesting.set_project(self.project)
        if hasattr(self, "documents_workspace"):
            self.documents_workspace.set_project(self.project)
        self._refresh_tree()
        self._refresh_object_cards()
        self._refresh_design_labels()
        self._refresh_inspector_context()
        self._refresh_bom()
        cabinet_selected = self.project.selected_cabinet is not None and self.project.selected_opening is None
        object_selected = cabinet_selected or self.selected_product_id is not None
        self.remove_cabinet_action.setEnabled(object_selected)
        self.delete_cabinet_action.setEnabled(object_selected)
        self.duplicate_action.setEnabled(object_selected)
        self.add_cabinet_action.setEnabled(len(self.project.cabinets) < MAX_CABINETS)
        self.catalogue_add_button.setEnabled(len(self.project.cabinets) < MAX_CABINETS)
        self.remove_opening_action.setEnabled(self.project.selected_opening is not None)

    def _refresh_design_labels(self) -> None:
        if not hasattr(self, "header_project_title"):
            return
        self.header_project_title.setText(self.project.name)
        self.header_project_meta.setText(
            f"{self.project.project_type}  ·  {self.project.room.width} × {self.project.room.depth} mm"
            f"  ·  {len(self.project.cabinets)} cabinets"
            f"  ·  {len(self.project.room.openings)} openings"
        )
        self.plan_room_dimensions.setText(
            f"{self.project.room.width:,} × {self.project.room.depth:,} mm"
        )
        self.sidebar_project_label.setText(self.project.name)
        self.sidebar_project_label.setToolTip(self.project.name)
        opening = self.project.selected_opening
        if opening:
            self.inspector_title.setText(f"{opening.opening_id} · {opening.kind.title()}")
            self.inspector_subtitle.setText(f"{WALL_LABELS[opening.wall_id]} / Room opening")
        elif self.selected_product_id:
            product = next((item for item in self.project.placed_products
                            if item.item_id == self.selected_product_id), None)
            if product:
                definition = get_product(product.type_id)
                self.inspector_title.setText(f"{product.item_id} · {definition.name}")
                self.inspector_subtitle.setText(definition.library)
        elif self.project.selected_cabinet:
            cabinet = self.project.selected_cabinet
            definition = get_catalogue_item(cabinet.cabinet_type_id)
            self.inspector_title.setText(f"{cabinet.cabinet_id} · {definition.name}")
            self.inspector_subtitle.setText(f"{definition.category} / {self.project.project_type}")
        else:
            self.inspector_title.setText("Room")
            self.inspector_subtitle.setText("Select an object to edit its properties")
        self.inspector_title.hide()
        self.inspector_subtitle.hide()
        if self.selected_product_id:
            product = next((item for item in self.project.placed_products
                            if item.item_id == self.selected_product_id), None)
            if product:
                self.viewport_selection_title.setText(f"{product.item_id} · {get_product(product.type_id).name}")
                self.viewport_selection_detail.setText(
                    f"{product.width} × {product.height} × {product.depth} mm · Visual design object"
                )
                return
        cabinet = self.project.selected_cabinet
        if cabinet:
            self.viewport_selection_title.setText(
                f"{cabinet.cabinet_id} · {get_catalogue_item(cabinet.cabinet_type_id).name}"
            )
            self.viewport_selection_detail.setText(
                f"{cabinet.material}  ·  {cabinet.width} × {cabinet.height} × {cabinet.depth} mm"
            )
        else:
            self.viewport_selection_title.setText("Kitchen workspace")
            self.viewport_selection_detail.setText("Select furniture in the plan or object list")

    def _refresh_object_cards(self) -> None:
        if not hasattr(self, "object_list"):
            return
        self.object_list.blockSignals(True)
        self.object_list.clear()
        self._cabinet_card_items = []
        self._appliance_card_items = []
        self.cabinet_count_label.setText(f"Cabinets ({len(self.project.cabinets)})")
        selected_item = None
        for cabinet in self.project.cabinets:
            definition = get_catalogue_item(cabinet.cabinet_type_id)
            preview = cached_cabinet_preview(definition.type_id, cabinet.material)
            icon = QIcon()
            icon.addPixmap(preview, QIcon.Mode.Normal)
            icon.addPixmap(preview, QIcon.Mode.Selected)
            card_name = definition.name.replace(" Cabinet", "").replace(" Unit", "")
            item = QListWidgetItem(
                icon,
                f"{cabinet.cabinet_id}  {card_name}\n"
                f"{cabinet.material}\nW{cabinet.width} H{cabinet.height} D{cabinet.depth}",
            )
            item.setData(Qt.ItemDataRole.UserRole, cabinet.cabinet_id)
            item.setData(KIND_ROLE, "cabinet")
            item.setData(NAME_ROLE, card_name)
            item.setData(DETAIL_ROLE, f"W {cabinet.width} × H {cabinet.height} × D {cabinet.depth}")
            item.setData(PREVIEW_ROLE, preview)
            item.setData(TALL_ROLE, cabinet.height > 1300)
            item.setSizeHint(QSize(0, 68))
            item.setToolTip(f"{cabinet.cabinet_id} · {definition.name}\n"
                            f"{cabinet.width} × {cabinet.height} × {cabinet.depth} mm · {cabinet.material}")
            self.object_list.addItem(item)
            self._cabinet_card_items.append(item)
            item.setHidden(self._cabinet_cards_collapsed)
            if cabinet.cabinet_id == self.project.selected_cabinet_id and not self.selected_product_id:
                selected_item = item
        appliances = products_for(APPLIANCES)
        if appliances:
            self.appliance_section_item = QListWidgetItem("Appliances")
            self.appliance_section_item.setData(KIND_ROLE, "section")
            self.appliance_section_item.setData(NAME_ROLE, "Appliances")
            self.appliance_section_item.setData(EXPANDED_ROLE, not self._appliance_cards_collapsed)
            self.appliance_section_item.setSizeHint(QSize(0, 49))
            self.object_list.addItem(self.appliance_section_item)
            for definition in appliances:
                appliance = QListWidgetItem(definition.name)
                appliance.setData(Qt.ItemDataRole.UserRole, f"catalogue:{definition.type_id}")
                appliance.setData(KIND_ROLE, "appliance")
                appliance.setData(NAME_ROLE, definition.name)
                appliance.setData(DETAIL_ROLE, definition.category)
                appliance_preview = appliance_card_preview(definition)
                appliance.setData(PREVIEW_ROLE, appliance_preview if appliance_preview is not None
                                  else product_thumbnail(definition))
                appliance.setSizeHint(QSize(0, 61))
                appliance.setToolTip(f"Browse {definition.name} in the product library")
                self.object_list.addItem(appliance)
                self._appliance_card_items.append(appliance)
                appliance.setHidden(self._appliance_cards_collapsed)
        if self.project.room.openings:
            heading = QListWidgetItem("ROOM & OPENINGS")
            heading.setData(KIND_ROLE, "section")
            heading.setData(NAME_ROLE, "Room & Openings")
            heading.setFlags(Qt.ItemFlag.ItemIsEnabled)
            heading.setSizeHint(QSize(0, 31))
            self.object_list.addItem(heading)
            for opening in self.project.room.openings:
                item = QListWidgetItem(outline_icon("design", "#60796C"),
                                       f"{opening.opening_id}   {opening.kind.title()}\n"
                                       f"{opening.width} × {opening.height} mm")
                item.setData(Qt.ItemDataRole.UserRole, f"opening:{opening.opening_id}")
                item.setData(KIND_ROLE, "object")
                item.setData(NAME_ROLE, f"{opening.opening_id} · {opening.kind.title()}")
                item.setData(DETAIL_ROLE, f"{opening.width} × {opening.height} mm")
                item.setData(PREVIEW_ROLE, outline_icon("project", "#7A7B70").pixmap(QSize(56, 46)))
                item.setSizeHint(QSize(0, 58))
                self.object_list.addItem(item)
                if opening.opening_id == self.project.selected_opening_id:
                    selected_item = item
        if self.project.placed_products:
            heading = QListWidgetItem("PLACED PRODUCTS")
            heading.setData(KIND_ROLE, "section")
            heading.setData(NAME_ROLE, "Placed Products")
            heading.setFlags(Qt.ItemFlag.ItemIsEnabled)
            heading.setSizeHint(QSize(0, 31))
            self.object_list.addItem(heading)
            for product in self.project.placed_products:
                definition = get_product(product.type_id)
                preview = product_thumbnail(definition)
                item = QListWidgetItem(QIcon(preview),
                                       f"{product.item_id}   {definition.name}\n{definition.library}")
                item.setData(Qt.ItemDataRole.UserRole, f"product:{product.item_id}")
                item.setData(KIND_ROLE, "object")
                item.setData(NAME_ROLE, f"{product.item_id} · {definition.name}")
                item.setData(DETAIL_ROLE, definition.library)
                item.setData(PREVIEW_ROLE, preview)
                item.setSizeHint(QSize(0, 61))
                self.object_list.addItem(item)
                if product.item_id == self.selected_product_id:
                    selected_item = item
        if selected_item is not None:
            self.object_list.setCurrentItem(selected_item)
        self.object_list.blockSignals(False)
        self.object_summary.setText(
            f"{len(self.project.room.openings)} openings  ·  "
            f"{len(self.project.placed_products)} placed products"
        )

    def _refresh_tree(self) -> None:
        self.project_tree.clear()
        root = QTreeWidgetItem([self.project.name])
        room = QTreeWidgetItem([f"Room — {self.project.room.width} × {self.project.room.depth} mm"])
        room.setData(0, Qt.ItemDataRole.UserRole, "room")
        walls = QTreeWidgetItem([f"Walls & openings ({len(self.project.room.openings)})"])
        selected_opening_item = None
        for wall in self.project.room.walls:
            wall_item = QTreeWidgetItem([wall.label])
            wall_item.setData(0, Qt.ItemDataRole.UserRole, f"wall:{wall.wall_id}")
            for opening in (item for item in self.project.room.openings if item.wall_id == wall.wall_id):
                opening_item = QTreeWidgetItem([
                    f"{opening.opening_id} — {opening.kind.title()} — {opening.width} × {opening.height} mm"
                ])
                opening_item.setData(0, Qt.ItemDataRole.UserRole, f"opening:{opening.opening_id}")
                wall_item.addChild(opening_item)
                if opening.opening_id == self.project.selected_opening_id:
                    selected_opening_item = opening_item
            walls.addChild(wall_item)
        furniture = QTreeWidgetItem([f"Furniture ({len(self.project.cabinets)})"])
        selected_item = None
        for cabinet in self.project.cabinets:
            type_name = get_catalogue_item(cabinet.cabinet_type_id).name
            item = QTreeWidgetItem([f"{cabinet.cabinet_id} — {type_name} — {cabinet.material}"])
            item.setData(0, Qt.ItemDataRole.UserRole, cabinet.cabinet_id)
            if cabinet.cabinet_id == self.project.selected_cabinet_id:
                selected_item = item
            furniture.addChild(item)
        # Preserve the v0.5 Furniture node index for compatibility.
        root.addChildren([room, furniture, walls])
        products_node = QTreeWidgetItem([f"Placed products ({len(self.project.placed_products)})"])
        for product in self.project.placed_products:
            definition = get_product(product.type_id)
            entry = QTreeWidgetItem([f"{product.item_id} — {definition.name}"])
            entry.setData(0, Qt.ItemDataRole.UserRole, f"product:{product.item_id}")
            products_node.addChild(entry)
            if product.item_id == self.selected_product_id:
                selected_item = entry
        root.addChild(products_node)
        hardware_node = QTreeWidgetItem([f"Hardware assignments ({len(self.project.hardware_assignments)})"])
        for assignment in self.project.hardware_assignments:
            definition = get_product(assignment.type_id)
            entry = QTreeWidgetItem([f"{assignment.assignment_id} — {definition.name} → {assignment.cabinet_id} ×{assignment.quantity}"])
            entry.setData(0, Qt.ItemDataRole.UserRole, f"hardware:{assignment.assignment_id}")
            hardware_node.addChild(entry)
        root.addChild(hardware_node)
        self.project_tree.addTopLevelItem(root)
        root.setExpanded(True)
        walls.setExpanded(True)
        furniture.setExpanded(True)
        products_node.setExpanded(True)
        hardware_node.setExpanded(True)
        for index in range(walls.childCount()):
            walls.child(index).setExpanded(True)
        if self._inspector_context == "room":
            self.project_tree.setCurrentItem(room)
        elif self._inspector_context == "wall":
            for index in range(walls.childCount()):
                if walls.child(index).data(0, Qt.ItemDataRole.UserRole) == f"wall:{self.selected_wall_id}":
                    self.project_tree.setCurrentItem(walls.child(index))
                    break
        elif selected_opening_item is not None:
            self.project_tree.setCurrentItem(selected_opening_item)
        elif selected_item is not None:
            self.project_tree.setCurrentItem(selected_item)

    def _refresh_bom(self) -> None:
        items = generate_project_bom(self.project)
        self.bom_table.setRowCount(len(items))
        for row, item in enumerate(items):
            values = [item.name, f"{item.length_mm:g} mm" if item.length_mm else "—",
                      f"{item.width_mm:g} mm" if item.width_mm else "—",
                      f"{item.thickness_mm:g} mm" if item.thickness_mm else "—", item.material, str(item.quantity),
                      item.cabinet_id, item.cabinet_type]
            for column, value in enumerate(values):
                cell = QTableWidgetItem(value)
                if column in (1, 2, 3):
                    cell.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                elif column in (5, 6):
                    cell.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.bom_table.setItem(row, column, cell)

    def _tree_item_clicked(self, item: QTreeWidgetItem) -> None:
        item_id = item.data(0, Qt.ItemDataRole.UserRole)
        if item_id == "room":
            self.select_room_for_inspector()
        elif isinstance(item_id, str) and item_id.startswith("opening:"):
            self.select_opening(item_id.split(":", 1)[1])
        elif isinstance(item_id, str) and item_id.startswith("wall:"):
            self.select_wall(item_id.split(":", 1)[1])
        elif isinstance(item_id, str) and item_id.startswith("product:"):
            self.select_product(item_id.split(":", 1)[1])
        elif isinstance(item_id, str) and item_id.startswith("hardware:"):
            assignment = next(item for item in self.project.hardware_assignments if item.assignment_id == item_id.split(":", 1)[1])
            self.select_cabinet(assignment.cabinet_id)
            self.selected_hardware_assignment_id = assignment.assignment_id
        elif item_id:
            self.select_cabinet(item_id)

    def select_cabinet(self, cabinet_id: str) -> None:
        self._inspector_context = "cabinet"
        self.selected_product_id = None
        self.selected_hardware_assignment_id = None
        try:
            self.project.select_cabinet(cabinet_id)
            self.project.select_opening(None)
        except ValueError as error:
            self.statusBar().showMessage(str(error))
            return
        self._load_selected_controls()
        self.placement_warning.hide()
        self.refresh_visuals()
        self.width_spin.setFocus()
        self.statusBar().showMessage(f"Selected cabinet {cabinet_id}")

    def _select_cabinet_from_3d(self, cabinet_id: str) -> None:
        if self.project.selected_cabinet_id == cabinet_id and self._inspector_context == "cabinet":
            return
        camera = self.view3d.plotter.camera_position
        angle = self.view3d.plotter.camera.view_angle
        self.select_cabinet(cabinet_id)
        self.view3d.plotter.camera_position = camera
        self.view3d.plotter.camera.view_angle = angle
        self.view3d.plotter.reset_camera_clipping_range()
        self.view3d.plotter.render()

    def _select_product_from_3d(self, item_id: str) -> None:
        if self.selected_product_id == item_id:
            return
        camera = self.view3d.plotter.camera_position
        angle = self.view3d.plotter.camera.view_angle
        self.select_product(item_id)
        self.view3d.plotter.camera_position = camera
        self.view3d.plotter.camera.view_angle = angle
        self.view3d.plotter.reset_camera_clipping_range()
        self.view3d.plotter.render()

    def _load_product_controls(self) -> None:
        product = next((item for item in self.project.placed_products if item.item_id == self.selected_product_id), None)
        self.product_group.setVisible(product is not None)
        if product is None:
            return
        self.cabinet_group.hide()
        self.opening_group.hide()
        self._updating_product_controls = True
        self.product_id_label.setText(product.item_id)
        self.product_name_label.setText(get_product(product.type_id).name)
        self.product_rule_label.setText(
            "Visual only. Excluded from BOM,\nnesting, drilling and exports."
            if get_product(product.type_id).library == PROPS
            else "Unpriced sample. Manufacturing\ntreatment is metadata only."
        )
        self.product_treatment_group.setVisible(get_product(product.type_id).library == APPLIANCES)
        show_rotation = get_product(product.type_id).library == PROPS
        self.product_orientation_label.setVisible(show_rotation)
        self.product_orientation_combo.setVisible(show_rotation)
        self.product_orientation_combo.setCurrentIndex(
            self.product_orientation_combo.findData(product.orientation_degrees))
        if get_product(product.type_id).library == APPLIANCES:
            self.product_commercial_combo.setCurrentText(product.commercial_treatment)
            self.product_manufacturing_combo.setCurrentText(product.manufacturing_treatment)
            self.product_appearance_combo.setCurrentText(product.appearance)
        for control, value in ((self.product_x_spin, product.position_x), (self.product_y_spin, product.position_y),
                               (self.product_z_spin, product.elevation_z), (self.product_width_spin, product.width),
                               (self.product_depth_spin, product.depth), (self.product_height_spin, product.height)):
            control.setValue(value)
        self._updating_product_controls = False

    def select_product(self, item_id: str) -> None:
        if not any(item.item_id == item_id for item in self.project.placed_products):
            return
        self.selected_product_id = item_id
        self._inspector_context = "product"
        self.selected_hardware_assignment_id = None
        self.project.select_opening(None)
        self._load_opening_controls()
        self.refresh_visuals()
        self.statusBar().showMessage(f"Selected library product {item_id}")

    def begin_library_placement(self) -> None:
        current = self.library_list.currentItem()
        if current is None:
            self.statusBar().showMessage("Select a library product first")
            return
        type_id = current.data(Qt.ItemDataRole.UserRole)
        library = self.library_combo.currentText()
        try:
            if library == FURNITURE:
                if len(self.project.cabinets) >= MAX_CABINETS:
                    raise ValueError(f"This demo supports a maximum of {MAX_CABINETS} cabinets.")
                item = get_catalogue_item(type_id)
                if item.product_id and not any(rule.type_id == type_id for rule in self.project.price_master.catalogue_rules):
                    raise ValueError("This existing project lacks this cabinet's Price Master snapshot. Review Company Price Refresh before placing it.")
                self.plan_view.begin_placement(type_id)
            elif library == HARDWARE:
                cabinet = self.project.selected_cabinet
                if cabinet is None:
                    raise ValueError("Select a cabinet before assigning hardware.")
                assignment = HardwareAssignment(self.project.next_assignment_id(), cabinet.cabinet_id, type_id,
                                                self.hardware_quantity_spin.value())
                self.undo_stack.push(HardwareAssignmentCommand(assignment, self._apply_hardware_assignment))
                self.statusBar().showMessage(f"Assigned {get_product(type_id).name} to {cabinet.cabinet_id}; BOM unchanged")
                return
            else:
                self.plan_view.begin_product_placement(type_id)
            self.workspace_tabs.setCurrentIndex(0)
            self.statusBar().showMessage(f"Place {get_catalogue_item(type_id).name if library == FURNITURE else get_product(type_id).name} in the 2D plan; Esc cancels")
        except ValueError as error:
            self.statusBar().showMessage(str(error))

    def _place_product(self, type_id: str, x: int, y: int) -> None:
        definition = get_product(type_id)
        product = PlacedProduct(self.project.next_product_id(definition.library), type_id, x, y,
                                definition.elevation_z, definition.width, definition.depth, definition.height)
        try:
            self.project.validate_product_placement(product)
        except ValueError as error:
            self._show_placement_error(error)
            return
        self.plan_view.cancel_interaction(emit_signal=False)
        self.undo_stack.push(ProductChangeCommand(product.item_id, None, product,
                                                  self._apply_product_state, f"Place {product.item_id}"))
        self.statusBar().showMessage(f"Placed {product.item_id}: {definition.name}")

    def _apply_product_state(self, item_id: str, state: PlacedProduct | None) -> None:
        existing = next((item for item in self.project.placed_products if item.item_id == item_id), None)
        if state is None:
            if existing is not None:
                self.project.remove_product(item_id)
            self.selected_product_id = None
        elif existing is None:
            self.project.add_product(state)
            self.selected_product_id = item_id
        else:
            self.project.validate_product_placement(state)
            existing.__dict__.update(state.__dict__)
            self.selected_product_id = item_id
        self.project.select_opening(None)
        self._set_dirty(True)
        self._load_opening_controls()
        self.refresh_all(reset_camera=False)

    def move_product(self, item_id: str, x: int, y: int) -> None:
        product = next((item for item in self.project.placed_products if item.item_id == item_id), None)
        if product is None:
            return
        if (product.position_x, product.position_y) == (x, y):
            return
        candidate = deepcopy(product)
        candidate.position_x, candidate.position_y = x, y
        try:
            self.project.validate_product_placement(candidate)
        except ValueError as error:
            self._show_placement_error(error)
            return
        self.undo_stack.push(ProductChangeCommand(item_id, product, candidate,
                                                  self._apply_product_state, f"Move {item_id}"))

    def _product_properties_changed(self, *_args) -> None:
        if getattr(self, "_updating_product_controls", False) or self.selected_product_id is None:
            return
        product = next((item for item in self.project.placed_products if item.item_id == self.selected_product_id), None)
        if product is None:
            return
        candidate = deepcopy(product)
        candidate.position_x, candidate.position_y, candidate.elevation_z = (
            self.product_x_spin.value(), self.product_y_spin.value(), self.product_z_spin.value())
        candidate.width, candidate.depth, candidate.height = (
            self.product_width_spin.value(), self.product_depth_spin.value(), self.product_height_spin.value())
        if get_product(candidate.type_id).library == PROPS:
            candidate.orientation_degrees = int(self.product_orientation_combo.currentData())
        if get_product(candidate.type_id).library == APPLIANCES:
            candidate.commercial_treatment = self.product_commercial_combo.currentText()
            candidate.manufacturing_treatment = self.product_manufacturing_combo.currentText()
            candidate.appearance = self.product_appearance_combo.currentText()
        try:
            self.project.validate_product_placement(candidate)
        except ValueError as error:
            self._show_placement_error(error)
            self._load_product_controls()
            return
        if candidate != product:
            self.undo_stack.push(ProductChangeCommand(product.item_id, product, candidate,
                                                      self._apply_product_state, f"Edit {product.item_id}"))

    def remove_selected_product(self) -> None:
        if self.selected_product_id is None:
            return
        product = next(item for item in self.project.placed_products if item.item_id == self.selected_product_id)
        self.undo_stack.push(ProductChangeCommand(product.item_id, product, None,
                                                  self._apply_product_state, f"Remove {product.item_id}"))

    def remove_selected_object(self) -> None:
        if self.selected_product_id is not None:
            self.remove_selected_product()
        elif self.selected_hardware_assignment_id is not None:
            self.remove_selected_hardware_assignment()
        else:
            self.remove_selected_cabinet()

    def _duplicate_position(self, candidate, source, validate) -> tuple[int, int]:
        """Find a nearby valid 2D position, then scan the rectangular room."""
        w = getattr(candidate, "footprint_width", candidate.width)
        d = getattr(candidate, "footprint_depth", candidate.depth)
        source_w = getattr(source, "footprint_width", source.width)
        source_d = getattr(source, "footprint_depth", source.depth)
        preferred = (
            (source.position_x + source_w + 40, source.position_y),
            (source.position_x - w - 40, source.position_y),
            (source.position_x, source.position_y - d - 40),
            (source.position_x, source.position_y + source_d + 40),
        )
        scan = ((x, y) for y in range(0, max(0, self.project.room.depth - d) + 1, 100)
                for x in range(0, max(0, self.project.room.width - w) + 1, 100))
        for x, y in chain(preferred, scan):
            candidate.position_x, candidate.position_y = x, y
            try:
                validate(candidate)
                return x, y
            except ValueError:
                continue
        raise ValueError(f"No valid room position is available for a duplicate of {source.item_id if hasattr(source, 'item_id') else source.cabinet_id}.")

    def duplicate_selected_object(self) -> None:
        try:
            if self.selected_product_id is not None:
                source = next(item for item in self.project.placed_products if item.item_id == self.selected_product_id)
                candidate = deepcopy(source)
                candidate.item_id = self.project.next_product_id(get_product(source.type_id).library)
                self._duplicate_position(candidate, source, self.project.validate_product_placement)
                self.undo_stack.push(ProductChangeCommand(candidate.item_id, None, candidate,
                                                          self._apply_product_state, f"Duplicate {source.item_id}"))
            elif self.selected_hardware_assignment_id is not None:
                source = next(item for item in self.project.hardware_assignments
                              if item.assignment_id == self.selected_hardware_assignment_id)
                candidate = deepcopy(source)
                candidate.assignment_id = self.project.next_assignment_id()
                self.undo_stack.push(HardwareAssignmentCommand(candidate, self._apply_hardware_assignment))
            else:
                source = self.project.selected_cabinet
                if source is None or self.project.selected_opening is not None:
                    raise ValueError("Select a cabinet or library product to duplicate.")
                if len(self.project.cabinets) >= MAX_CABINETS:
                    raise ValueError(f"This demo supports a maximum of {MAX_CABINETS} cabinets.")
                candidate = deepcopy(source)
                candidate.cabinet_id = self.project.next_cabinet_id()
                self._duplicate_position(candidate, source, self.project.validate_cabinet_placement)
                self.undo_stack.push(AddCabinetCommand(candidate, self._apply_cabinet_addition))
        except ValueError as error:
            self._show_placement_error(error)

    def remove_selected_hardware_assignment(self) -> None:
        assignment_id = self.selected_hardware_assignment_id
        if assignment_id is None:
            self.statusBar().showMessage("Select a hardware assignment in the project tree first")
            return
        assignment = next(item for item in self.project.hardware_assignments if item.assignment_id == assignment_id)
        self.undo_stack.push(HardwareAssignmentCommand(assignment, self._apply_hardware_assignment, add=False))

    def _apply_hardware_assignment(self, assignment: HardwareAssignment, add: bool) -> None:
        if add:
            self.project.add_hardware_assignment(assignment)
            self.selected_hardware_assignment_id = assignment.assignment_id
        else:
            self.project.hardware_assignments = [item for item in self.project.hardware_assignments
                                                 if item.assignment_id != assignment.assignment_id]
            self.selected_hardware_assignment_id = None
        self._set_dirty(True)
        self.refresh_visuals()

    def _selected_catalogue_type_id(self) -> str:
        current = self.catalogue_list.currentItem()
        type_id = current.data(Qt.ItemDataRole.UserRole) if current else None
        if not type_id:
            raise ValueError("Select a furniture model from the Catalogue tab first.")
        return type_id

    def begin_catalogue_placement(self) -> None:
        if self.explorer_tabs.currentWidget() is self.library_page:
            self.begin_library_placement()
            return
        try:
            if len(self.project.cabinets) >= MAX_CABINETS:
                raise ValueError(f"This demo supports a maximum of {MAX_CABINETS} cabinets.")
            type_id = self._selected_catalogue_type_id()
            item = get_catalogue_item(type_id)
            self.plan_view.begin_placement(type_id)
            self.statusBar().showMessage(f"Place {item.name}: move over the 2D room, click to commit, Esc to cancel")
        except ValueError as error:
            self.statusBar().showMessage(str(error))

    def _apply_cabinet_addition(self, cabinet, add: bool) -> None:
        if add:
            self.project.add_cabinet(cabinet)
            definition = get_catalogue_item(cabinet.cabinet_type_id)
            if definition.product_id:
                if not any(item.type_id == definition.type_id for item in self.project.custom_catalogue):
                    self.project.custom_catalogue.append(definition)
                for type_id, quantity in definition.hardware_defaults.items():
                    self.project.add_hardware_assignment(HardwareAssignment(
                        self.project.next_assignment_id(), cabinet.cabinet_id, type_id, quantity))
            message = f"Placed {cabinet.cabinet_id} at X {cabinet.position_x} mm, Y {cabinet.position_y} mm"
        else:
            self.project.remove_cabinet(cabinet.cabinet_id)
            message = f"Undid placement of {cabinet.cabinet_id}"
        self._set_dirty(True)
        self.refresh_all(reset_camera=False)
        self.statusBar().showMessage(message)

    def _apply_cabinet_removal(self, cabinet, index: int, remove: bool,
                               assignments: list[HardwareAssignment] | None = None) -> None:
        if remove:
            self.project.remove_cabinet(cabinet.cabinet_id)
            message = f"Removed cabinet {cabinet.cabinet_id}"
        else:
            self.project.restore_cabinet(cabinet, index)
            self.project.hardware_assignments.extend(deepcopy(assignments or []))
            message = f"Restored cabinet {cabinet.cabinet_id}"
        self._set_dirty(True)
        self.refresh_all(reset_camera=False)
        self.statusBar().showMessage(message)

    def _place_catalogue_cabinet(self, type_id: str, x: int, y: int) -> None:
        try:
            cabinet = create_catalogue_cabinet(
                type_id,
                self.project.next_cabinet_id(),
                position_x=x,
                position_y=y,
            )
            self.project.validate_cabinet_placement(cabinet)
            self.plan_view.cancel_interaction(emit_signal=False)
            self.undo_stack.push(AddCabinetCommand(cabinet, self._apply_cabinet_addition))
        except ValueError as error:
            self.placement_warning.setText(str(error))
            self.placement_warning.show()
            self.statusBar().showMessage(str(error))

    def add_cabinet(self) -> None:
        """Legacy one-click placement retained for API and workflow compatibility."""
        try:
            type_id = self._selected_catalogue_type_id()
            catalogue_item = get_catalogue_item(type_id)
            x, y = self.project.find_available_back_wall_position(
                catalogue_item.width,
                catalogue_item.depth,
                height=catalogue_item.height,
                elevation_z=catalogue_item.elevation_z,
                cabinet_type_id=catalogue_item.type_id,
            )
            cabinet = create_catalogue_cabinet(type_id, self.project.next_cabinet_id(), position_x=x, position_y=y)
            self.undo_stack.push(AddCabinetCommand(cabinet, self._apply_cabinet_addition))
            self.statusBar().showMessage(f"Added {cabinet.cabinet_id}: {catalogue_item.name} at X {x} mm, Y {y} mm")
        except ValueError as error:
            self.placement_warning.setText(str(error))
            self.placement_warning.show()
            self.statusBar().showMessage(str(error))

    def remove_selected_cabinet(self) -> None:
        cabinet = self.project.selected_cabinet
        if cabinet is None or self.project.selected_opening is not None:
            self.statusBar().showMessage("Select a cabinet before removing it")
            return
        try:
            index = next(
                index for index, item in enumerate(self.project.cabinets)
                if item.cabinet_id == cabinet.cabinet_id
            )
            related = [item for item in self.project.hardware_assignments if item.cabinet_id == cabinet.cabinet_id]
            self.undo_stack.push(RemoveCabinetCommand(cabinet, index, self._apply_cabinet_removal, related))
        except ValueError as error:
            self.statusBar().showMessage(str(error))

    def load_sample_kitchen(self) -> None:
        if not self._confirm_replace_unsaved():
            self.statusBar().showMessage("Sample kitchen loading cancelled; unsaved project preserved")
            return
        self.project = Project.sample_kitchen("AIZ Sample Kitchen")
        self.selected_wall_id = "WEST"
        self._inspector_context = "cabinet"
        self.project_path = None
        self.undo_stack.clear()
        self.plan_view.cancel_interaction(emit_signal=False)
        self._set_dirty(True)
        self.refresh_all(reset_camera=True)
        self.view3d.fit_all_cabinets()
        self.statusBar().showMessage("Loaded premium sample: base C1, wall C2 and tall C3")

    def load_complete_kitchen_demo(self) -> None:
        if not self._confirm_replace_unsaved("complete kitchen demo"):
            self.statusBar().showMessage("Complete kitchen loading cancelled; unsaved project preserved")
            return
        self.project = Project.complete_kitchen_demo("AIZ Complete Kitchen Demo")
        self.selected_wall_id = "WEST"
        self._inspector_context = "cabinet"
        self.project_path = None
        self.undo_stack.clear()
        self.plan_view.cancel_interaction(emit_signal=False)
        self._set_dirty(True)
        self.refresh_all(reset_camera=True)
        self.view3d.fit_all_cabinets()
        self.statusBar().showMessage(
            "Loaded complete demo: connected base run, two wall units and tall pantry"
        )

    def new_project(self) -> None:
        if not self._confirm_replace_unsaved("new project"):
            self.statusBar().showMessage("New project cancelled; current project preserved")
            return
        dialog = NewProjectDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            name = dialog.name_edit.text().strip()
            if not name:
                QMessageBox.warning(self, "Invalid project", "Please enter a project name.")
                return
            self.project = Project.empty(name=name, project_type=dialog.type_combo.currentText())
            self.project.custom_catalogue = list(self.custom_library_items)
            try:
                apply_company_setup_to_new_project(self.project, load_company_price_setup())
            except (OSError, ValueError) as error:
                QMessageBox.warning(self, "Company Price Setup", f"New project created without company prices: {error}")
            self.selected_wall_id = "WEST"
            self._inspector_context = "room"
            self.project_path = None
            self.undo_stack.clear()
            self.plan_view.cancel_interaction(emit_signal=False)
            self._set_dirty(True)
            self.refresh_all(reset_camera=True)
            self.statusBar().showMessage(f"Created project: {name}")

    def open_project(self) -> None:
        if not self._confirm_replace_unsaved("selected project"):
            self.statusBar().showMessage("Open cancelled; current project preserved")
            return
        filename, _ = QFileDialog.getOpenFileName(self, "Open kuchhe7 Project", "", "kuchhe7 Project (*.json)")
        if not filename:
            return
        try:
            self.project = load_project(filename)
            self._inspector_context = "opening" if self.project.selected_opening is not None else "cabinet"
            if self.project.selected_opening is not None:
                self.selected_wall_id = self.project.selected_opening.wall_id
            self.project_path = Path(filename)
            self.undo_stack.clear()
            self.plan_view.cancel_interaction(emit_signal=False)
            self._set_dirty(False)
            self.refresh_all(reset_camera=True)
            self.statusBar().showMessage(f"Opened {filename}")
        except (OSError, ValueError, KeyError, TypeError) as error:
            QMessageBox.critical(self, "Open failed", str(error))

    def save_project(self, save_as: bool = False) -> bool:
        path = self.project_path
        if path is None or save_as:
            filename, _ = QFileDialog.getSaveFileName(self, "Save kuchhe7 Project", f"{self.project.name}.json", "kuchhe7 Project (*.json)")
            if not filename:
                return False
            path = Path(filename)
        try:
            self.project_path = save_project(self.project, path)
            self._set_dirty(False)
            self.statusBar().showMessage(f"Saved {self.project_path}")
            return True
        except (OSError, ValueError) as error:
            QMessageBox.critical(self, "Save failed", str(error))
            return False

    def _set_selected_construction_profile(self, profile_data: dict | None) -> None:
        cabinet = self.project.selected_cabinet
        if cabinet is None:
            QMessageBox.information(self, "Construction Profile", "Select a cabinet first.")
            return
        candidate = deepcopy(self.project)
        candidate.selected_cabinet.construction_profile = deepcopy(profile_data)
        try:
            candidate.validate()
            generate_project_bom(candidate)
        except ValueError as error:
            QMessageBox.warning(self, "Invalid Construction Profile", str(error))
            return
        label = (f"{profile_data['profile_id']} / {profile_data['revision']}"
                 if profile_data else "legacy demonstration rules")
        reply = QMessageBox.question(
            self, "Apply Construction Profile",
            f"Apply {label} to {cabinet.cabinet_id}?\n\n"
            "This changes its draft BOM and dependent draft outputs. "
            "Construction specifications are demonstration-only, not factory approved.",
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self.project = candidate
        self._set_dirty(True)
        self.refresh_visuals()
        self.statusBar().showMessage(f"{cabinet.cabinet_id}: {label} — {DEMO_STATUS}")

    def apply_synthetic_construction_profile(self) -> None:
        cabinet = self.project.selected_cabinet
        if cabinet is None:
            QMessageBox.information(self, "Construction Profile", "Select a cabinet first.")
            return
        self._set_selected_construction_profile(synthetic_profile_for(cabinet).to_dict())

    def import_construction_profile(self) -> None:
        if self.project.selected_cabinet is None:
            QMessageBox.information(self, "Construction Profile", "Select a cabinet first.")
            return
        filename, _ = QFileDialog.getOpenFileName(
            self, "Import demonstration construction profile", "", "JSON files (*.json)"
        )
        if not filename:
            return
        try:
            data = json.loads(Path(filename).read_text(encoding="utf-8"))
            profile = ConstructionProfile.from_dict(data)
            profile.validate_for(self.project.selected_cabinet)
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, "Invalid Construction Profile", str(error))
            return
        self._set_selected_construction_profile(profile.to_dict())

    def restore_legacy_construction_profile(self) -> None:
        self._set_selected_construction_profile(None)

    def export_xlsx(self) -> None:
        filename, _ = QFileDialog.getSaveFileName(self, "Export Demonstration BOM", f"{self.project.name}-BOM.xlsx", "Excel Workbook (*.xlsx)")
        if filename:
            try:
                path = export_bom_xlsx(self.project, filename)
                self.statusBar().showMessage(f"Exported BOM: {path}")
            except (OSError, ValueError) as error:
                QMessageBox.critical(self, "Export failed", str(error))

    def export_cut_list(self) -> None:
        filename, _ = QFileDialog.getSaveFileName(
            self, "Export Demonstration Cut List (not factory approved)",
            f"{self.project.name}-cut-list.xlsx", "Excel Workbook (*.xlsx)"
        )
        if filename:
            try:
                path = export_cut_list_xlsx(self.project, filename)
                self.statusBar().showMessage(f"Exported demonstration cut list: {path}")
            except (OSError, ValueError) as error:
                QMessageBox.critical(self, "Cut list export failed", str(error))

    def export_dxf(self) -> None:
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Export Demonstration Cabinet Elevations (not nesting/CNC)",
            f"{self.project.name}-elevation.dxf",
            "AutoCAD DXF (*.dxf)",
        )
        if filename:
            try:
                path = export_front_elevation_dxf(self.project, filename)
                self.statusBar().showMessage(
                    f"Exported demonstration cabinet elevations: {path} — not nesting or machine cutting instructions"
                )
            except (OSError, ValueError) as error:
                QMessageBox.critical(self, "Export failed", str(error))

    def export_engineering_drawing(self) -> None:
        dialog = EngineeringExportDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        drawing_type = dialog.drawing_type
        filename, _ = QFileDialog.getSaveFileName(
            self,
            f"Export {DRAWING_LABELS[drawing_type]} — demonstration DXF",
            f"{self.project.name}-{drawing_type}.dxf",
            "AutoCAD DXF (*.dxf)",
        )
        if not filename:
            return
        try:
            path = export_engineering_dxf(
                self.project, filename, drawing_type, cnc_profile=dialog.cnc_profile()
            )
            suffix = "generic CNC prototype; client CAM import not verified" if drawing_type == CNC_PROTOTYPE else "demonstration drawing"
            self.statusBar().showMessage(f"Exported {suffix}: {path}")
        except (OSError, ValueError) as error:
            QMessageBox.critical(self, "Engineering export failed", str(error))

    def export_complete_kitchen_drawing(self) -> None:
        filename, _ = QFileDialog.getSaveFileName(
            self, "Export Complete Kitchen — one demonstration DXF",
            "KUCHE7_COMPLETE_KITCHEN.dxf", "AutoCAD DXF (*.dxf)",
        )
        if not filename:
            return
        try:
            path = export_complete_kitchen_dxf(self.project, filename)
            self.statusBar().showMessage(
                f"Exported one complete kitchen DXF: {path} — CNC machine compatibility not validated"
            )
        except (OSError, ValueError) as error:
            QMessageBox.critical(self, "Complete kitchen export failed", str(error))

    def show_about(self) -> None:
        QMessageBox.about(self, "About kuchhe7", "<b>kuchhe7 Client Approval Demo v1.0.1</b><br>Kitchen Design & Manufacturing Platform<br><br>Interactive design, cabinet engineering and sheet nesting feasibility previews by AIZ INFOTECHS.<br>Nesting, drilling, clearances, DXF exports and construction rules are demonstration-only and not approved for production.")

