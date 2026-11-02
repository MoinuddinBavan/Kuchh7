import json

import pytest

from kuchhe7.models import Cabinet, Project, Room
from kuchhe7.persistence import load_project, save_project


def test_project_round_trip(tmp_path):
    original = Project("Showroom Kitchen", "Kitchen", Room(4200, 3300), Cabinet(width=1200, material="Walnut"))
    path = save_project(original, tmp_path / "project.json")
    loaded = load_project(path)
    assert loaded == original
    assert loaded.cabinet.width == 1200


def test_bad_project_file_is_rejected(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"name": "Incomplete"}), encoding="utf-8")
    with pytest.raises(KeyError):
        load_project(path)
