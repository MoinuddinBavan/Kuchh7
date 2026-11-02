from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


from .catalogue import FINISHES, LEGACY_FINISH_ALIASES, get_catalogue_item, normalized_finish
from .openings import DOOR_SWINGS, OPENING_KINDS, WALL_IDS, opening_error, opening_furniture_conflict, wall_length
from .placement import placement_error, volumes_intersect


MATERIALS = FINISHES
PROJECT_TYPES = ("Kitchen", "Wardrobe", "Vanity")
MAX_CABINETS = 10


@dataclass
class Wall:
    wall_id: str
    label: str

    def validate(self) -> None:
        if self.wall_id not in WALL_IDS:
            raise ValueError(f"Unsupported wall identifier: {self.wall_id}")
        if not self.label.strip():
            raise ValueError("Wall label cannot be empty.")


def _default_walls() -> list[Wall]:
    labels = {
        "NORTH": "North / front wall",
        "EAST": "East / right wall",
        "SOUTH": "South / cabinet wall",
        "WEST": "West / left wall",
    }
    return [Wall(wall_id, labels[wall_id]) for wall_id in WALL_IDS]


@dataclass
class Opening:
    opening_id: str
    kind: str
    wall_id: str
    offset: int
    width: int
    height: int
    elevation: int = 0
    swing: str = "Left In"

    def validate(self, room: Room) -> None:
        if not self.opening_id.strip():
            raise ValueError("Opening ID cannot be empty.")
        if self.kind not in OPENING_KINDS:
            raise ValueError(f"Unsupported opening type: {self.kind}")
        if self.wall_id not in WALL_IDS:
            raise ValueError(f"Unsupported wall identifier: {self.wall_id}")
        if self.offset < 0:
            raise ValueError("Opening offset cannot be negative.")
        if not 300 <= self.width <= 3000:
            raise ValueError("Opening width must be between 300 and 3,000 mm.")
        if not 300 <= self.height <= 3000:
            raise ValueError("Opening height must be between 300 and 3,000 mm.")
        if self.elevation < 0 or self.elevation + self.height > room.height:
            raise ValueError(f"{self.opening_id} extends beyond the {room.height} mm wall height.")
        if self.offset + self.width > wall_length(room, self.wall_id):
            raise ValueError(f"{self.opening_id} extends beyond wall {self.wall_id}.")
        if self.kind == "door" and self.swing not in DOOR_SWINGS:
            raise ValueError(f"Unsupported door swing: {self.swing}")


@dataclass
class Room:
    width: int = 3600
    depth: int = 3200
    height: int = 2600
    walls: list[Wall] = field(default_factory=_default_walls)
    openings: list[Opening] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.walls = [item if isinstance(item, Wall) else Wall(**item) for item in self.walls]
        self.openings = [item if isinstance(item, Opening) else Opening(**item) for item in self.openings]

    def validate(self) -> None:
        if not 1200 <= self.width <= 20000 or not 1200 <= self.depth <= 20000:
            raise ValueError("Room dimensions must be between 1,200 and 20,000 mm.")
        if not 2100 <= self.height <= 5000:
            raise ValueError("Room height must be between 2,100 and 5,000 mm.")
        wall_ids = [wall.wall_id for wall in self.walls]
        if tuple(wall_ids) != WALL_IDS:
            raise ValueError("Rectangular rooms require NORTH, EAST, SOUTH and WEST walls in order.")
        for wall in self.walls:
            wall.validate()
        opening_ids = [opening.opening_id for opening in self.openings]
        if len(opening_ids) != len(set(opening_ids)):
            raise ValueError("Opening IDs must be unique.")
        for opening in self.openings:
            error = opening_error(self, self.openings, opening)
            if error:
                raise ValueError(error)


@dataclass
class Cabinet:
    width: int = 900
    height: int = 720
    depth: int = 600
    board_thickness: int = 18
    door_count: int = 2
    drawer_count: int = 0
    shelf_count: int = 1
    material: str = "Natural Oak"
    cabinet_id: str = "C1"
    position_x: int = 0
    position_y: int = 0
    cabinet_type_id: str = "base_2_door"
    elevation_z: int = 0

    def validate(self) -> None:
        if not 300 <= self.width <= 3000:
            raise ValueError("Cabinet width must be between 300 and 3,000 mm.")
        if not 300 <= self.height <= 3000:
            raise ValueError("Cabinet height must be between 300 and 3,000 mm.")
        if not 200 <= self.depth <= 1200:
            raise ValueError("Cabinet depth must be between 200 and 1,200 mm.")
        if not 10 <= self.board_thickness <= 50:
            raise ValueError("Board thickness must be between 10 and 50 mm.")
        if self.width <= 2 * self.board_thickness or self.height <= 2 * self.board_thickness:
            raise ValueError("Cabinet dimensions are too small for the board thickness.")
        if not 0 <= self.door_count <= 6:
            raise ValueError("Door count must be between 0 and 6.")
        if not 0 <= self.drawer_count <= 8:
            raise ValueError("Drawer count must be between 0 and 8.")
        if not 0 <= self.shelf_count <= 10:
            raise ValueError("Shelf count must be between 0 and 10.")
        if self.material not in (*MATERIALS, *LEGACY_FINISH_ALIASES):
            raise ValueError(f"Unsupported material: {self.material}")
        catalogue_item = get_catalogue_item(self.cabinet_type_id)
        if normalized_finish(self.material) not in catalogue_item.supported_finishes:
            raise ValueError(f"{self.material} is not supported by {catalogue_item.name}.")
        if not self.cabinet_id.strip():
            raise ValueError("Cabinet ID cannot be empty.")
        if self.position_x < 0 or self.position_y < 0:
            raise ValueError("Cabinet positions cannot be negative.")
        if self.elevation_z < 0:
            raise ValueError("Cabinet elevation cannot be negative.")


def _default_project_cabinet() -> Cabinet:
    return Cabinet(cabinet_id="C1", position_x=1350, position_y=2600)


@dataclass
class Project:
    name: str = "Client Demo Kitchen"
    project_type: str = "Kitchen"
    room: Room = field(default_factory=Room)
    # ``cabinet`` remains the selected-cabinet alias for v0.2 API compatibility.
    cabinet: Cabinet | None = field(default_factory=_default_project_cabinet)
    cabinets: list[Cabinet] = field(default_factory=list)
    selected_cabinet_id: str | None = "C1"
    selected_opening_id: str | None = None

    def __post_init__(self) -> None:
        if not self.cabinets and self.cabinet is not None:
            if not self.cabinet.cabinet_id:
                self.cabinet.cabinet_id = "C1"
            self.cabinets = [self.cabinet]
        if self.cabinets:
            self.select_cabinet(self.selected_cabinet_id if any(
                item.cabinet_id == self.selected_cabinet_id for item in self.cabinets
            ) else self.cabinets[0].cabinet_id)
        else:
            self.cabinet = None
            self.selected_cabinet_id = None

    @property
    def selected_cabinet(self) -> Cabinet | None:
        return self.cabinet

    def select_cabinet(self, cabinet_id: str) -> Cabinet:
        for cabinet in self.cabinets:
            if cabinet.cabinet_id == cabinet_id:
                self.selected_cabinet_id = cabinet_id
                self.cabinet = cabinet
                return cabinet
        raise ValueError(f"Cabinet {cabinet_id!r} does not exist.")

    def next_cabinet_id(self) -> str:
        used = {cabinet.cabinet_id for cabinet in self.cabinets}
        for number in range(1, 100):
            candidate = f"C{number}"
            if candidate not in used:
                return candidate
        raise ValueError("Could not allocate a cabinet ID.")

    @property
    def selected_opening(self) -> Opening | None:
        return next((item for item in self.room.openings if item.opening_id == self.selected_opening_id), None)

    def select_opening(self, opening_id: str | None) -> Opening | None:
        if opening_id is None:
            self.selected_opening_id = None
            return None
        for opening in self.room.openings:
            if opening.opening_id == opening_id:
                self.selected_opening_id = opening_id
                return opening
        raise ValueError(f"Opening {opening_id!r} does not exist.")

    def next_opening_id(self, kind: str) -> str:
        prefix = "D" if kind == "door" else "W"
        used = {item.opening_id for item in self.room.openings}
        for number in range(1, 100):
            candidate = f"{prefix}{number}"
            if candidate not in used:
                return candidate
        raise ValueError("Could not allocate an opening ID.")

    def validate_opening(self, opening: Opening) -> None:
        error = opening_error(self.room, self.room.openings, opening)
        if error:
            raise ValueError(error)
        for cabinet in self.cabinets:
            conflict = opening_furniture_conflict(self.room, opening, cabinet)
            if conflict:
                raise ValueError(conflict)

    def add_opening(self, opening: Opening) -> Opening:
        if any(item.opening_id == opening.opening_id for item in self.room.openings):
            raise ValueError(f"Opening ID {opening.opening_id!r} is already in use.")
        self.validate_opening(opening)
        self.room.openings.append(opening)
        self.selected_opening_id = opening.opening_id
        return opening

    def replace_opening(self, opening: Opening) -> Opening:
        self.validate_opening(opening)
        for index, current in enumerate(self.room.openings):
            if current.opening_id == opening.opening_id:
                self.room.openings[index] = opening
                self.selected_opening_id = opening.opening_id
                return opening
        raise ValueError(f"Opening {opening.opening_id!r} does not exist.")

    def remove_opening(self, opening_id: str) -> Opening:
        for index, opening in enumerate(self.room.openings):
            if opening.opening_id == opening_id:
                removed = self.room.openings.pop(index)
                self.selected_opening_id = self.room.openings[0].opening_id if self.room.openings else None
                return removed
        raise ValueError(f"Opening {opening_id!r} does not exist.")

    def add_cabinet(self, cabinet: Cabinet) -> Cabinet:
        if len(self.cabinets) >= MAX_CABINETS:
            raise ValueError(f"This demo supports a maximum of {MAX_CABINETS} cabinets.")
        if any(item.cabinet_id == cabinet.cabinet_id for item in self.cabinets):
            raise ValueError(f"Cabinet ID {cabinet.cabinet_id!r} is already in use.")
        self.validate_cabinet_placement(cabinet)
        self.cabinets.append(cabinet)
        return self.select_cabinet(cabinet.cabinet_id)

    def remove_cabinet(self, cabinet_id: str) -> Cabinet:
        for index, cabinet in enumerate(self.cabinets):
            if cabinet.cabinet_id != cabinet_id:
                continue
            removed = self.cabinets.pop(index)
            if self.cabinets:
                next_index = min(index, len(self.cabinets) - 1)
                self.select_cabinet(self.cabinets[next_index].cabinet_id)
            else:
                self.cabinet = None
                self.selected_cabinet_id = None
            return removed
        raise ValueError(f"Cabinet {cabinet_id!r} does not exist.")

    def restore_cabinet(self, cabinet: Cabinet, index: int) -> Cabinet:
        """Restore an undo snapshot at its original list position."""
        if len(self.cabinets) >= MAX_CABINETS:
            raise ValueError(f"This demo supports a maximum of {MAX_CABINETS} cabinets.")
        if any(item.cabinet_id == cabinet.cabinet_id for item in self.cabinets):
            raise ValueError(f"Cabinet ID {cabinet.cabinet_id!r} is already in use.")
        self.validate_cabinet_placement(cabinet)
        self.cabinets.insert(max(0, min(index, len(self.cabinets))), cabinet)
        return self.select_cabinet(cabinet.cabinet_id)

    @staticmethod
    def cabinets_overlap(first: Cabinet, second: Cabinet) -> bool:
        return volumes_intersect(first, second)

    def validate_cabinet_placement(self, cabinet: Cabinet) -> None:
        cabinet.validate()
        error = placement_error(self.room, self.cabinets, cabinet)
        if error:
            raise ValueError(error)

    def find_available_back_wall_position(
        self,
        width: int = 600,
        depth: int = 600,
        *,
        height: int = 720,
        elevation_z: int = 0,
        cabinet_type_id: str = "base_2_door",
    ) -> tuple[int, int]:
        y = self.room.depth - depth
        candidates = [0, *sorted(item.position_x + item.width for item in self.cabinets)]
        for x in candidates:
            candidate = Cabinet(
                width=width,
                height=height,
                depth=depth,
                cabinet_id="candidate",
                cabinet_type_id=cabinet_type_id,
                position_x=x,
                position_y=y,
                elevation_z=elevation_z,
            )
            try:
                self.validate_cabinet_placement(candidate)
                return x, y
            except ValueError:
                continue
        raise ValueError("There is no free back-wall space for another 600 mm cabinet.")

    def validate(self) -> None:
        if not self.name.strip():
            raise ValueError("Project name cannot be empty.")
        if self.project_type not in PROJECT_TYPES:
            raise ValueError(f"Unsupported project type: {self.project_type}")
        self.room.validate()
        if len(self.cabinets) > MAX_CABINETS:
            raise ValueError(f"A project may contain at most {MAX_CABINETS} cabinets.")
        identifiers = [cabinet.cabinet_id for cabinet in self.cabinets]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("Cabinet IDs must be unique.")
        for cabinet in self.cabinets:
            self.validate_cabinet_placement(cabinet)
        if self.cabinets:
            selected_id = self.selected_cabinet_id
            if not any(item.cabinet_id == selected_id for item in self.cabinets):
                selected_id = self.cabinets[0].cabinet_id
            self.select_cabinet(selected_id)
        else:
            self.cabinet = None
            self.selected_cabinet_id = None
        if self.selected_opening_id and not self.selected_opening:
            self.selected_opening_id = None

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "schema_version": 6,
            "name": self.name,
            "project_type": self.project_type,
            "room": asdict(self.room),
            "cabinets": [asdict(cabinet) for cabinet in self.cabinets],
            "selected_cabinet_id": self.selected_cabinet_id,
            "selected_opening_id": self.selected_opening_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Project":
        room_data = dict(data["room"])
        room_data.setdefault("height", 2600)
        room_data.setdefault("walls", _default_walls())
        room_data.setdefault("openings", [])
        room = Room(**room_data)
        if "cabinets" in data:
            cabinets = [Cabinet(**item) for item in data["cabinets"]]
            selected_value = data.get("selected_cabinet_id")
            selected_id = str(selected_value) if selected_value is not None else None
            if cabinets and selected_id is None:
                selected_id = cabinets[0].cabinet_id
        else:
            # v0.2 migration: retain all cabinet values and place it safely on the back wall.
            cabinet_data = dict(data["cabinet"])
            cabinet_data.setdefault("cabinet_id", "C1")
            cabinet_data.setdefault("position_x", max(0, (room.width - int(cabinet_data.get("width", 900))) // 2))
            cabinet_data.setdefault("position_y", max(0, room.depth - int(cabinet_data.get("depth", 600))))
            cabinets = [Cabinet(**cabinet_data)]
            selected_id = cabinets[0].cabinet_id
        project = cls(
            name=str(data["name"]),
            project_type=str(data["project_type"]),
            room=room,
            cabinet=next((item for item in cabinets if item.cabinet_id == selected_id), cabinets[0] if cabinets else None),
            cabinets=cabinets,
            selected_cabinet_id=selected_id,
            selected_opening_id=data.get("selected_opening_id"),
        )
        project.validate()
        return project

    @classmethod
    def empty(cls, name: str = "Client Demo Kitchen", project_type: str = "Kitchen") -> "Project":
        """Create a valid blank design without furniture or room openings."""
        project = cls(
            name=name,
            project_type=project_type,
            room=Room(),
            cabinet=None,
            cabinets=[],
            selected_cabinet_id=None,
            selected_opening_id=None,
        )
        project.validate()
        return project

    @classmethod
    def sample_kitchen(cls, name: str = "Sample Kitchen") -> "Project":
        room = Room(openings=[
            Opening("D1", "door", "WEST", 500, 900, 2100, 0, "Left In"),
            Opening("W1", "window", "WEST", 1500, 900, 900, 1050, "Left In"),
        ])
        cabinets = [
            Cabinet(width=900, height=720, depth=600, door_count=2, shelf_count=1, material="Cashmere",
                    cabinet_id="C1", cabinet_type_id="base_2_door", position_x=650, position_y=2600),
            Cabinet(width=600, height=600, depth=350, door_count=1, shelf_count=1, material="Warm White",
                    cabinet_id="C2", cabinet_type_id="wall_lift_up", position_x=800, position_y=2850, elevation_z=1400),
            Cabinet(width=800, height=2100, depth=600, door_count=2, shelf_count=1, material="Walnut",
                    cabinet_id="C3", cabinet_type_id="tall_pantry", position_x=2150, position_y=2600),
        ]
        project = cls(name=name, project_type="Kitchen", room=room, cabinet=cabinets[0], cabinets=cabinets)
        project.validate()
        return project

    @classmethod
    def complete_kitchen_demo(cls, name: str = "Complete Kitchen Demo") -> "Project":
        """Return the coordinated six-unit v0.7 presentation layout."""
        room = Room(
            width=3600,
            depth=3200,
            height=2600,
            openings=[
                Opening("D1", "door", "WEST", 500, 900, 2100, 0, "Left In"),
                Opening("W1", "window", "WEST", 1500, 900, 900, 1050, "Left In"),
            ],
        )
        cabinets = [
            Cabinet(
                width=800, height=720, depth=600, door_count=2, shelf_count=1,
                material="Cashmere", cabinet_id="C1", cabinet_type_id="base_2_door",
                position_x=250, position_y=2600,
            ),
            Cabinet(
                width=600, height=720, depth=600, door_count=0, drawer_count=3, shelf_count=0,
                material="Warm White", cabinet_id="C2", cabinet_type_id="base_3_drawer",
                position_x=1050, position_y=2600,
            ),
            Cabinet(
                width=800, height=720, depth=600, door_count=2, shelf_count=0,
                material="Cashmere", cabinet_id="C3", cabinet_type_id="sink_base",
                position_x=1650, position_y=2600,
            ),
            Cabinet(
                width=800, height=720, depth=350, door_count=2, shelf_count=1,
                material="Warm White", cabinet_id="C4", cabinet_type_id="wall_2_door",
                position_x=250, position_y=2850, elevation_z=1400,
            ),
            Cabinet(
                width=600, height=720, depth=350, door_count=0, shelf_count=2,
                material="Walnut", cabinet_id="C5", cabinet_type_id="wall_open_shelf",
                position_x=1050, position_y=2850, elevation_z=1400,
            ),
            Cabinet(
                width=600, height=2100, depth=600, door_count=2, shelf_count=4,
                material="Walnut", cabinet_id="C6", cabinet_type_id="tall_pantry",
                position_x=2750, position_y=2600,
            ),
        ]
        project = cls(name=name, project_type="Kitchen", room=room, cabinet=cabinets[0], cabinets=cabinets)
        project.validate()
        return project

