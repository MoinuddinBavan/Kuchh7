import pytest

from kuchhe7.bom import generate_bom
from kuchhe7.models import Cabinet


def test_default_cabinet_bom_dimensions_and_quantities():
    items = {item.name: item for item in generate_bom(Cabinet())}
    assert items["Left side panel"].length_mm == 720
    assert items["Top panel"].length_mm == 864
    assert items["Shelf"].quantity == 1
    assert items["Door"].quantity == 2
    assert items["Door"].width_mm == pytest.approx(447)
    assert items["Concealed hinge"].quantity == 4


def test_1200_wide_cabinet_updates_component_sizes():
    items = {item.name: item for item in generate_bom(Cabinet(width=1200))}
    assert items["Top panel"].length_mm == 1164
    assert items["Door"].width_mm == pytest.approx(597)


def test_invalid_dimensions_are_rejected():
    with pytest.raises(ValueError, match="width"):
        generate_bom(Cabinet(width=200))


def test_zero_shelves_omits_shelf_line():
    assert "Shelf" not in {item.name for item in generate_bom(Cabinet(shelf_count=0))}

