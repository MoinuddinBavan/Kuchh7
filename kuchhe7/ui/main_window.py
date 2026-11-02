from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from PySide6.QtCore import QEvent, QSize, Qt
from PySide6.QtGui import QAction, QFont, QIcon, QKeySequence, QUndoStack
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDockWidget,
    QFileDialog,
    QFrame,
    QFormLayout,
    QGroupBox,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QScrollArea,
    QPushButton,
    QSpinBox,
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
from ..catalogue import CATEGORIES, catalogue_items, create_catalogue_cabinet, get_catalogue_item
from ..exports import export_bom_xlsx, export_front_elevation_dxf
from ..models import MATERIALS, MAX_CABINETS, PROJECT_TYPES, Opening, Project
from ..openings import DOOR_SWINGS, WALL_IDS, WALL_LABELS, wall_length
from ..persistence import load_project, save_project
from ..platform_support import is_macos, platform_shortcut
from .cad_views import Cabinet3DView, RoomPlanView
from .catalogue_preview import catalogue_thumbnail
from .history import AddCabinetCommand, MoveCabinetCommand, OpeningChangeCommand, RemoveCabinetCommand
from .manufacturing_preview import ManufacturingPreviewWidget
from .sheet_nesting import SheetNestingWidget


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


class MainWindow(QMainWindow):
    def __init__(self, *, start_empty: bool = True) -> None:
        super().__init__()
        self.project = Project.empty() if start_empty else Project()
        self.project_path: Path | None = None
        self._dirty = False
        self._updating_controls = False
        self._updating_opening_controls = False
        self._workspace_3d_maximized = False
        self._workspace_restore_sizes = [620, 720]
        self._workspace_restore_docks: dict[QDockWidget, bool] = {}
        self._engineering_restore_docks: dict[QDockWidget, bool] = {}
        self.selected_wall_id = "WEST"
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
        self._build_status_bar()
        self.resizeDocks([self.explorer_dock, self.properties_dock], [330, 305], Qt.Orientation.Horizontal)
        self.resizeDocks([self.bom_dock], [245], Qt.Orientation.Vertical)
        self.statusBar().showMessage("Ready — demonstration construction rules are not factory approved")
        self.refresh_all(reset_camera=True)

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
        self.add_cabinet_action = QAction("Place Selected", self, triggered=self.begin_catalogue_placement)
        self.remove_cabinet_action = QAction("Remove Cabinet", self, triggered=self.remove_selected_cabinet)
        self.delete_cabinet_action = QAction("Delete selected cabinet", self, triggered=self.remove_selected_cabinet)
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
        self.export_dxf_action = QAction("Export Elevation (DXF)…", self, triggered=self.export_dxf)
        self.export_dxf_action.setToolTip(
            "Export demonstration cabinet front elevations — not nesting or machine cutting instructions"
        )
        self.manufacturing_preview_action = QAction(
            "Manufacturing Preview", self, shortcut=platform_shortcut("Ctrl+Shift+M"),
            triggered=self.show_manufacturing_preview,
        )
        self.manufacturing_preview_action.setToolTip(
            "Open the selected-cabinet exploded assembly and component preview"
        )
        self.sheet_nesting_action = QAction(
            "Sheet Nesting", self, shortcut=platform_shortcut("Ctrl+Shift+N"), triggered=self.show_sheet_nesting
        )
        self.sheet_nesting_action.setToolTip(
            "Open the BOM-driven demonstration sheet nesting workspace"
        )
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
        file_menu.addSeparator()
        file_menu.addAction(self.exit_action)
        edit_menu = self.menuBar().addMenu("&Edit")
        edit_menu.addActions([self.undo_action, self.redo_action])
        edit_menu.addSeparator()
        edit_menu.addAction("Select Cabinet", lambda: self.width_spin.setFocus())
        view_menu = self.menuBar().addMenu("&View")
        view_menu.addActions([
            self.front_view_action, self.isometric_view_action, self.fit_all_action,
            self.reset_3d_action, self.maximize_3d_action,
        ])
        view_menu.addSeparator()
        view_menu.addActions([self.presentation_view_action, self.presentation_camera_action, self.hide_room_walls_action])
        view_menu.addSeparator()
        view_menu.addAction(self.show_interior_action)
        design_menu = self.menuBar().addMenu("&Design")
        design_menu.addActions([self.load_complete_action, self.add_cabinet_action, self.remove_cabinet_action])
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
        manufacturing_menu.addSeparator()
        manufacturing_menu.addActions([self.export_xlsx_action, self.export_dxf_action])
        help_menu = self.menuBar().addMenu("&Help")
        help_menu.addAction(self.about_action)

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("Main Ribbon")
        toolbar.setObjectName("mainRibbon")
        toolbar.setMovable(False)
        toolbar.setIconSize(toolbar.iconSize() * 1.15)
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        project_label = QLabel("PROJECT")
        project_label.setObjectName("ribbonGroupLabel")
        toolbar.addWidget(project_label)
        toolbar.addActions([self.new_action, self.open_action, self.save_action])
        toolbar.addSeparator()
        design_label = QLabel("LAYOUT")
        design_label.setObjectName("ribbonGroupLabel")
        toolbar.addWidget(design_label)
        toolbar.addActions([self.load_complete_action, self.add_cabinet_action, self.remove_cabinet_action])
        toolbar.addActions([self.undo_action, self.redo_action])
        toolbar.addSeparator()
        placement_label = QLabel("PLACEMENT")
        placement_label.setObjectName("ribbonGroupLabel")
        toolbar.addWidget(placement_label)
        toolbar.addActions([self.snap_action, self.grid_snap_action])
        toolbar.addSeparator()
        view_label = QLabel("CABINET VIEW")
        view_label.setObjectName("ribbonGroupLabel")
        toolbar.addWidget(view_label)
        toolbar.addActions([
            self.front_view_action,
            self.isometric_view_action,
            self.fit_all_action,
            self.reset_3d_action,
            self.presentation_view_action,
            self.presentation_camera_action,
            self.show_interior_action,
        ])
        toolbar.addSeparator()
        export_label = QLabel("EXPORT")
        export_label.setObjectName("ribbonGroupLabel")
        toolbar.addWidget(export_label)
        toolbar.addActions([self.export_xlsx_action, self.export_dxf_action])
        self.addToolBar(toolbar)

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
        header_layout.setContentsMargins(14, 9, 14, 9)
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
        self.workspace_splitter.setHandleWidth(6)
        self.plan_view = RoomPlanView()
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
        self.view3d = Cabinet3DView()
        self.plan_panel = self._canvas_panel(
            "2D ROOM PLAN", "Click to select • drag to move • Esc to cancel", self.plan_view
        )
        self.model_panel = self._canvas_panel(
            "3D CABINET", "Technical CAD / presentation • rotate, pan and zoom",
            self.view3d, self.maximize_3d_action,
        )
        self.workspace_splitter.addWidget(self.plan_panel)
        self.workspace_splitter.addWidget(self.model_panel)
        self.workspace_splitter.setStretchFactor(0, 1)
        self.workspace_splitter.setStretchFactor(1, 1)
        self.workspace_splitter.setSizes([620, 720])
        self.manufacturing_preview = ManufacturingPreviewWidget()
        self.manufacturing_preview.set_cabinet(self.project.selected_cabinet)
        self.sheet_nesting = SheetNestingWidget()
        self.sheet_nesting.set_project(self.project)
        self.workspace_tabs = QTabWidget()
        self.workspace_tabs.setObjectName("workspaceTabs")
        self.workspace_tabs.setDocumentMode(True)
        self.workspace_tabs.addTab(self.workspace_splitter, "Design Studio")
        self.workspace_tabs.addTab(self.manufacturing_preview, "Manufacturing Preview")
        self.workspace_tabs.addTab(self.sheet_nesting, "Sheet Nesting")
        self.workspace_tabs.currentChanged.connect(self._workspace_changed)
        self.setCentralWidget(self.workspace_tabs)

    def _build_explorer(self) -> None:
        self.explorer_dock = QDockWidget("PROJECT & CATALOGUE", self)
        self.explorer_dock.setObjectName("explorerDock")
        self.explorer_dock.setMinimumWidth(270)
        self.project_tree = QTreeWidget()
        self.project_tree.installEventFilter(self)
        self.project_tree.viewport().installEventFilter(self)
        self.project_tree.setHeaderHidden(True)
        self.project_tree.setIndentation(18)
        self.project_tree.setUniformRowHeights(True)
        self.project_tree.setAnimated(True)
        self.project_tree.itemClicked.connect(self._tree_item_clicked)
        self.explorer_tabs = QTabWidget()
        self.explorer_tabs.addTab(self.project_tree, "Project")
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
        self.explorer_dock.setWidget(self.explorer_tabs)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.explorer_dock)
        self.catalogue_category_combo.currentTextChanged.connect(self._populate_catalogue)
        self.catalogue_list.currentItemChanged.connect(self._catalogue_selection_changed)
        self.catalogue_list.itemDoubleClicked.connect(lambda _item: self.begin_catalogue_placement())
        self.catalogue_add_button.clicked.connect(self.begin_catalogue_placement)
        self._populate_catalogue()

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
        spin = QSpinBox()
        spin.setRange(minimum, maximum)
        spin.setSuffix(suffix)
        spin.setKeyboardTracking(False)
        return spin

    def _build_properties(self) -> None:
        self.properties_dock = QDockWidget("PROPERTIES / CONFIGURATION", self)
        self.properties_dock.setObjectName("propertiesDock")
        wrapper = QWidget()
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)
        room_group = QGroupBox("Room")
        room_form = QFormLayout(room_group)
        room_form.setHorizontalSpacing(14)
        room_form.setVerticalSpacing(9)
        self.room_width_spin = self._spin(1200, 20000)
        self.room_depth_spin = self._spin(1200, 20000)
        self.room_height_spin = self._spin(2100, 5000)
        room_form.addRow("Width", self.room_width_spin)
        room_form.addRow("Depth", self.room_depth_spin)
        room_form.addRow("Wall height", self.room_height_spin)

        self.opening_group = QGroupBox("Room openings")
        opening_form = QFormLayout(self.opening_group)
        opening_form.setHorizontalSpacing(14)
        opening_form.setVerticalSpacing(8)
        self.opening_id_label = QLabel("None")
        self.opening_id_label.setObjectName("cabinetIdBadge")
        self.opening_kind_label = QLabel("—")
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
        self.cabinet_group = QGroupBox("Selected cabinet")
        form = QFormLayout(self.cabinet_group)
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(9)
        self.width_spin = self._spin(300, 3000)
        self.height_spin = self._spin(300, 3000)
        self.depth_spin = self._spin(200, 1200)
        self.thickness_spin = self._spin(10, 50)
        self.door_spin = self._spin(0, 6, "")
        self.drawer_spin = self._spin(0, 8, "")
        self.shelf_spin = self._spin(0, 10, "")
        self.material_combo = QComboBox()
        self.material_combo.addItems(MATERIALS)
        self.cabinet_id_label = QLabel()
        self.cabinet_id_label.setObjectName("cabinetIdBadge")
        self.cabinet_type_label = QLabel()
        self.cabinet_category_label = QLabel()
        self.position_x_spin = self._spin(0, 20000)
        self.position_y_spin = self._spin(0, 20000)
        form.addRow("Cabinet ID", self.cabinet_id_label)
        form.addRow("Furniture type", self.cabinet_type_label)
        form.addRow("Category", self.cabinet_category_label)
        for label, widget in [
            ("Width", self.width_spin), ("Height", self.height_spin), ("Depth", self.depth_spin),
            ("Board thickness", self.thickness_spin),
            ("Position X", self.position_x_spin), ("Position Y", self.position_y_spin),
        ]:
            form.addRow(label, widget)
        self.door_label = QLabel("Door count")
        self.drawer_label = QLabel("Drawer count")
        self.shelf_label = QLabel("Shelf count")
        form.insertRow(6, self.door_label, self.door_spin)
        form.insertRow(7, self.drawer_label, self.drawer_spin)
        form.insertRow(8, self.shelf_label, self.shelf_spin)
        form.insertRow(9, "Material / finish", self.material_combo)
        self.placement_warning = QLabel()
        self.placement_warning.setObjectName("placementWarning")
        self.placement_warning.setWordWrap(True)
        self.placement_warning.hide()
        note = QLabel("Demo rules only — not factory approved")
        note.setWordWrap(True)
        note.setObjectName("warningLabel")
        layout.addWidget(room_group)
        layout.addWidget(self.opening_group)
        layout.addWidget(self.cabinet_group)
        layout.addWidget(self.placement_warning)
        layout.addWidget(note)
        layout.addStretch()
        scroll = QScrollArea()
        scroll.setObjectName("propertiesScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setWidget(wrapper)
        self.properties_dock.setMinimumWidth(260)
        self.properties_dock.setWidget(scroll)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.properties_dock)
        for spin in [self.room_width_spin, self.room_depth_spin, self.room_height_spin, self.width_spin, self.height_spin,
                     self.depth_spin, self.thickness_spin, self.door_spin, self.drawer_spin, self.shelf_spin,
                     self.position_x_spin, self.position_y_spin]:
            spin.valueChanged.connect(self._properties_changed)
        self.material_combo.currentTextChanged.connect(self._properties_changed)
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

    def _build_bom(self) -> None:
        self.bom_dock = QDockWidget("COMPONENTS & BILL OF MATERIALS", self)
        self.bom_dock.setObjectName("bomDock")
        self.bom_dock.setMinimumHeight(190)
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
        self.bom_table.verticalHeader().setDefaultSectionSize(30)
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
            self.remove_selected_cabinet()
            event.accept()
            return True
        return super().eventFilter(watched, event)

    def _set_presentation_view(self, enabled: bool) -> None:
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

    def _workspace_changed(self, index: int) -> None:
        engineering_active = index == self.workspace_tabs.indexOf(self.manufacturing_preview)
        nesting_active = index == self.workspace_tabs.indexOf(self.sheet_nesting)
        auxiliary_active = engineering_active or nesting_active
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
            else:
                self.sheet_nesting.set_project(self.project)
                self.statusBar().showMessage(
                    "Demonstration sheet nesting — click Recalculate after project changes"
                )
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

    def select_wall(self, wall_id: str) -> None:
        if wall_id not in WALL_IDS:
            return
        self.selected_wall_id = wall_id
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
        self._set_dirty(True)
        self.refresh_all(reset_camera=False)

    def select_opening(self, opening_id: str) -> None:
        try:
            opening = self.project.select_opening(opening_id)
        except ValueError as error:
            self.statusBar().showMessage(str(error))
            return
        self.selected_wall_id = opening.wall_id
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
            self.cabinet_type_label.setText("Add furniture from the Catalogue")
            self.cabinet_category_label.setText("—")
            self.cabinet_group.setTitle("Selected cabinet — none")
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
        self.cabinet_type_label.setText(catalogue_item.name)
        self.cabinet_category_label.setText(catalogue_item.category)
        shows_doors = catalogue_item.front_style not in ("drawers", "open")
        shows_drawers = catalogue_item.front_style == "drawers"
        shows_shelves = catalogue_item.front_style != "sink"
        self.door_label.setVisible(shows_doors)
        self.door_spin.setVisible(shows_doors)
        self.drawer_label.setVisible(shows_drawers)
        self.drawer_spin.setVisible(shows_drawers)
        self.shelf_label.setVisible(shows_shelves)
        self.shelf_spin.setVisible(shows_shelves)
        self.cabinet_group.setTitle(f"Selected cabinet — {cabinet.cabinet_id}")
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
        self._load_selected_controls()
        self.placement_warning.hide()
        self.status_project_label.setText(f"{self.project.name}  •  {self.project.project_type}")
        self.refresh_visuals(reset_camera)

    def _set_dirty(self, dirty: bool) -> None:
        self._dirty = dirty
        title = "kuchhe7 — Kitchen Design & Manufacturing Platform | AIZ INFOTECHS"
        self.setWindowTitle(f"{title}{' *' if dirty else ''}")

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
            self.project.selected_cabinet_id,
            self.project.selected_opening_id,
            self.selected_wall_id,
        )
        self.view3d.update_scene(
            self.project.room,
            self.project.cabinets,
            self.project.selected_cabinet_id,
            reset_camera,
        )
        if hasattr(self, "manufacturing_preview"):
            self.manufacturing_preview.set_cabinet(self.project.selected_cabinet)
        if hasattr(self, "sheet_nesting"):
            self.sheet_nesting.set_project(self.project)
        self._refresh_tree()
        self._refresh_bom()
        cabinet_selected = self.project.selected_cabinet is not None and self.project.selected_opening is None
        self.remove_cabinet_action.setEnabled(cabinet_selected)
        self.delete_cabinet_action.setEnabled(cabinet_selected)
        self.add_cabinet_action.setEnabled(len(self.project.cabinets) < MAX_CABINETS)
        self.catalogue_add_button.setEnabled(len(self.project.cabinets) < MAX_CABINETS)
        self.remove_opening_action.setEnabled(self.project.selected_opening is not None)

    def _refresh_tree(self) -> None:
        self.project_tree.clear()
        root = QTreeWidgetItem([self.project.name])
        room = QTreeWidgetItem([f"Room — {self.project.room.width} × {self.project.room.depth} mm"])
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
        self.project_tree.addTopLevelItem(root)
        root.setExpanded(True)
        walls.setExpanded(True)
        furniture.setExpanded(True)
        for index in range(walls.childCount()):
            walls.child(index).setExpanded(True)
        if selected_opening_item is not None:
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
        if isinstance(item_id, str) and item_id.startswith("opening:"):
            self.select_opening(item_id.split(":", 1)[1])
        elif isinstance(item_id, str) and item_id.startswith("wall:"):
            self.select_wall(item_id.split(":", 1)[1])
        elif item_id:
            self.select_cabinet(item_id)

    def select_cabinet(self, cabinet_id: str) -> None:
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

    def _selected_catalogue_type_id(self) -> str:
        current = self.catalogue_list.currentItem()
        type_id = current.data(Qt.ItemDataRole.UserRole) if current else None
        if not type_id:
            raise ValueError("Select a furniture model from the Catalogue tab first.")
        return type_id

    def begin_catalogue_placement(self) -> None:
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
            message = f"Placed {cabinet.cabinet_id} at X {cabinet.position_x} mm, Y {cabinet.position_y} mm"
        else:
            self.project.remove_cabinet(cabinet.cabinet_id)
            message = f"Undid placement of {cabinet.cabinet_id}"
        self._set_dirty(True)
        self.refresh_all(reset_camera=False)
        self.statusBar().showMessage(message)

    def _apply_cabinet_removal(self, cabinet, index: int, remove: bool) -> None:
        if remove:
            self.project.remove_cabinet(cabinet.cabinet_id)
            message = f"Removed cabinet {cabinet.cabinet_id}"
        else:
            self.project.restore_cabinet(cabinet, index)
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
            self.undo_stack.push(RemoveCabinetCommand(cabinet, index, self._apply_cabinet_removal))
        except ValueError as error:
            self.statusBar().showMessage(str(error))

    def load_sample_kitchen(self) -> None:
        if not self._confirm_replace_unsaved():
            self.statusBar().showMessage("Sample kitchen loading cancelled; unsaved project preserved")
            return
        self.project = Project.sample_kitchen("AIZ Sample Kitchen")
        self.selected_wall_id = "WEST"
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
            self.selected_wall_id = "WEST"
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

    def export_xlsx(self) -> None:
        filename, _ = QFileDialog.getSaveFileName(self, "Export Demonstration BOM", f"{self.project.name}-BOM.xlsx", "Excel Workbook (*.xlsx)")
        if filename:
            try:
                path = export_bom_xlsx(self.project, filename)
                self.statusBar().showMessage(f"Exported BOM: {path}")
            except (OSError, ValueError) as error:
                QMessageBox.critical(self, "Export failed", str(error))

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

    def show_about(self) -> None:
        QMessageBox.about(self, "About kuchhe7", "<b>kuchhe7 Client Approval Demo v1.0.1</b><br>Kitchen Design & Manufacturing Platform<br><br>Interactive design, cabinet engineering and sheet nesting feasibility previews by AIZ INFOTECHS.<br>Nesting, drilling, clearances, DXF exports and construction rules are demonstration-only and not approved for production.")

