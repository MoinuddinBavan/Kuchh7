from __future__ import annotations

from copy import deepcopy
from typing import Callable

from PySide6.QtGui import QUndoCommand

from ..models import Cabinet, Opening


class MoveCabinetCommand(QUndoCommand):
    COMMAND_ID = 501

    def __init__(
        self,
        cabinet_id: str,
        old_position: tuple[int, int],
        new_position: tuple[int, int],
        apply_position: Callable[[str, int, int], None],
    ) -> None:
        super().__init__(f"Move {cabinet_id}")
        self.cabinet_id = cabinet_id
        self.old_position = old_position
        self.new_position = new_position
        self._apply_position = apply_position

    def id(self) -> int:
        return self.COMMAND_ID

    def mergeWith(self, other: QUndoCommand) -> bool:  # noqa: N802
        if not isinstance(other, MoveCabinetCommand) or other.cabinet_id != self.cabinet_id:
            return False
        self.new_position = other.new_position
        self.setText(f"Move {self.cabinet_id}")
        return True

    def undo(self) -> None:
        self._apply_position(self.cabinet_id, *self.old_position)

    def redo(self) -> None:
        self._apply_position(self.cabinet_id, *self.new_position)


class AddCabinetCommand(QUndoCommand):
    def __init__(self, cabinet: Cabinet, apply_addition: Callable[[Cabinet, bool], None]) -> None:
        super().__init__(f"Place {cabinet.cabinet_id}")
        self.cabinet = deepcopy(cabinet)
        self._apply_addition = apply_addition

    def undo(self) -> None:
        self._apply_addition(deepcopy(self.cabinet), False)

    def redo(self) -> None:
        self._apply_addition(deepcopy(self.cabinet), True)


class RemoveCabinetCommand(QUndoCommand):
    """Undoable removal that preserves the cabinet snapshot, index, and ID."""

    def __init__(
        self,
        cabinet: Cabinet,
        index: int,
        apply_removal: Callable[[Cabinet, int, bool], None],
    ) -> None:
        super().__init__(f"Remove {cabinet.cabinet_id}")
        self.cabinet = deepcopy(cabinet)
        self.index = index
        self._apply_removal = apply_removal

    def undo(self) -> None:
        self._apply_removal(deepcopy(self.cabinet), self.index, False)

    def redo(self) -> None:
        self._apply_removal(deepcopy(self.cabinet), self.index, True)


class OpeningChangeCommand(QUndoCommand):
    """Undoable add, edit, move, or removal of one room opening."""

    COMMAND_ID = 601

    def __init__(
        self,
        opening_id: str,
        before: Opening | None,
        after: Opening | None,
        apply_state: Callable[[str, Opening | None], None],
        text: str,
        *,
        merge_moves: bool = False,
    ) -> None:
        super().__init__(text)
        self.opening_id = opening_id
        self.before = deepcopy(before)
        self.after = deepcopy(after)
        self._apply_state = apply_state
        self._merge_moves = merge_moves

    def id(self) -> int:
        return self.COMMAND_ID if self._merge_moves else -1

    def mergeWith(self, other: QUndoCommand) -> bool:  # noqa: N802
        if (
            not self._merge_moves
            or not isinstance(other, OpeningChangeCommand)
            or not other._merge_moves
            or other.opening_id != self.opening_id
        ):
            return False
        self.after = deepcopy(other.after)
        return True

    def undo(self) -> None:
        self._apply_state(self.opening_id, deepcopy(self.before))

    def redo(self) -> None:
        self._apply_state(self.opening_id, deepcopy(self.after))
