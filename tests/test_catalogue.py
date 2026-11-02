import ezdxf

from kuchhe7.bom import generate_bom
from kuchhe7.catalogue import CATEGORIES, CATALOGUE, FINISHES, create_catalogue_cabinet, get_catalogue_item
from kuchhe7.exports import export_front_elevation_dxf
from kuchhe7.models import Project
from kuchhe7.persistence import load_project, save_project


def test_catalogue_contains_all_requested_furniture_families():
    assert len(CATALOGUE) == 15
    assert CATEGORIES == ("Base Cabinets", "Wall Cabinets", "Tall Units", "Vanity")
    assert len({item.type_id for item in CATALOGUE}) == 15
    assert all(item.supported_finishes for item in CATALOGUE)
    assert FINISHES == ("Warm White", "Cashmere", "Natural Oak", "Walnut", "Graphite")
    assert {item.name for item in CATALOGUE} == {
        "2-Door Base Cabinet", "3-Drawer Base Cabinet", "4-Drawer Base Cabinet",
        "Sink Base Cabinet", "Open Shelf Base Cabinet", "Corner Base Cabinet",
        "2-Door Wall Cabinet", "Lift-up Wall Cabinet", "Open Shelf Wall Unit",
        "Corner Wall Cabinet", "Tall Pantry Cabinet", "Oven / Appliance Tall Unit",
        "Utility Tall Cabinet", "Vanity Base Cabinet", "Vanity Drawer Unit",
    }


def test_type_specific_defaults_and_bom_components():
    drawers = create_catalogue_cabinet("base_3_drawer", "C1")
    assert drawers.drawer_count == 3 and drawers.door_count == 0
    drawer_parts = {item.name for item in generate_bom(drawers)}
    assert {"Drawer front", "Drawer box side", "Drawer runner pair"} <= drawer_parts
    assert "Door" not in drawer_parts

    open_unit = create_catalogue_cabinet("wall_open_shelf", "C2")
    open_parts = {item.name for item in generate_bom(open_unit)}
    assert "Shelf" in open_parts and "Door" not in open_parts
    assert open_unit.elevation_z == 1400


def test_v04_catalogue_fields_round_trip(tmp_path):
    cabinet = create_catalogue_cabinet("vanity_drawer", "C1", position_x=1200, position_y=2700)
    project = Project(name="Vanity Demo", project_type="Vanity", cabinet=cabinet)
    reopened = load_project(save_project(project, tmp_path / "catalogue.json"))
    assert reopened.cabinet.cabinet_type_id == "vanity_drawer"
    assert reopened.cabinet.drawer_count == 2
    assert reopened.cabinet.material == "Warm White"

    mixed = Project.sample_kitchen("Mixed Catalogue")
    mixed_reopened = load_project(save_project(mixed, tmp_path / "mixed-catalogue.json"))
    assert [item.cabinet_type_id for item in mixed_reopened.cabinets] == [
        "base_2_door", "wall_lift_up", "tall_pantry"
    ]
    assert [item.elevation_z for item in mixed_reopened.cabinets] == [0, 1400, 0]


def test_drawer_dxf_uses_horizontal_front_divisions(tmp_path):
    cabinet = create_catalogue_cabinet("base_4_drawer", "C1", position_x=0, position_y=2600)
    project = Project(cabinet=cabinet)
    document = ezdxf.readfile(export_front_elevation_dxf(project, tmp_path / "drawers.dxf"))
    lines = list(document.modelspace().query("LINE"))
    assert len(lines) == 3
    assert all(line.dxf.start.y == line.dxf.end.y for line in lines)


def test_premium_sample_spans_base_wall_and_tall_categories():
    project = Project.sample_kitchen()
    assert [get_catalogue_item(item.cabinet_type_id).category for item in project.cabinets] == [
        "Base Cabinets", "Wall Cabinets", "Tall Units"
    ]
    assert project.cabinets[1].elevation_z > 0
    assert project.cabinets[2].height == 2100
    assert [item.material for item in project.cabinets] == ["Cashmere", "Warm White", "Walnut"]


def test_legacy_finish_name_is_preserved_on_round_trip(tmp_path):
    project = Project()
    project.cabinet.material = "White Matte"
    reopened = load_project(save_project(project, tmp_path / "legacy-finish.json"))
    assert reopened.cabinet.material == "White Matte"
