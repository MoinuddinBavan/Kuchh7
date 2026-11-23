"""New independent client-visual project; existing sample fixtures stay unchanged."""

from copy import deepcopy

from kuchhe7.bom import generate_project_bom
from kuchhe7.complete_kitchen_dxf import associate_cabinets_to_walls
from kuchhe7.cut_list import generate_cut_list
from kuchhe7.nesting import nest_project
from kuchhe7.persistence import load_project, save_project
from kuchhe7.quotation import calculate_quotation
from scripts.create_luxury_island_demo import build_luxury_kitchen


def test_luxury_kitchen_has_real_l_layout_island_and_valid_openings():
    project = build_luxury_kitchen()
    assert (project.room.width, project.room.depth, project.room.height) == (6500, 5400, 2800)
    assert len(project.cabinets) == 10
    assert {opening.kind for opening in project.room.openings} == {"door", "window"}
    west = [cabinet for cabinet in project.cabinets if cabinet.orientation_degrees == 90]
    south = [cabinet for cabinet in project.cabinets if cabinet.position_y == 4800]
    assert len(west) == 2 and len(south) == 4
    island = {cabinet.cabinet_id: cabinet for cabinet in project.cabinets if cabinet.cabinet_id in ("C9", "C10")}
    assert len(island) == 2
    assert island["C9"].position_x + island["C9"].width == island["C10"].position_x
    assert island["C9"].depth == island["C10"].depth == 900
    assert min(cabinet.position_y for cabinet in south) - max(
        cabinet.position_y + cabinet.footprint_depth for cabinet in island.values()
    ) == 1200
    assert all(associate_cabinets_to_walls(project)[cabinet_id].wall_id is None
               for cabinet_id in island)
    project.validate()


def test_luxury_kitchen_props_are_visual_only_and_island_panels_remain_in_manufacturing():
    project = build_luxury_kitchen()
    bare = deepcopy(project)
    bare.placed_products = [item for item in bare.placed_products if not item.item_id.startswith("P")]
    assert generate_project_bom(project) == generate_project_bom(bare)
    assert generate_cut_list(project) == generate_cut_list(bare)
    assert nest_project(project) == nest_project(bare)
    assert calculate_quotation(project) == calculate_quotation(bare)
    assert {row.cabinet_id for row in generate_cut_list(project)} >= {"C9", "C10"}


def test_luxury_kitchen_save_and_reopen_preserves_every_object(tmp_path):
    original = build_luxury_kitchen()
    reopened = load_project(save_project(original, tmp_path / "luxury.json"))
    assert reopened.to_dict() == original.to_dict()
    assert reopened.selected_cabinet_id == "C9"
    assert len(reopened.placed_products) == 8


def test_island_position_remains_editable_without_changing_bom(tmp_path):
    project = build_luxury_kitchen()
    original_bom = generate_project_bom(project)
    project.select_cabinet("C9").position_y = 2600
    project.validate()
    reopened = load_project(save_project(project, tmp_path / "moved-island.json"))
    assert reopened.select_cabinet("C9").position_y == 2600
    assert generate_project_bom(reopened) == original_bom
