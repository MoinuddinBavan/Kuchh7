"""Small platform adaptations shared by the Windows and macOS desktop builds."""

from __future__ import annotations

import platform


def platform_name(system: str | None = None) -> str:
    """Return a stable friendly platform name without affecting project data."""
    value = system or platform.system()
    return {"Darwin": "macOS", "Windows": "Windows"}.get(value, value or "Unknown")


def is_macos(system: str | None = None) -> bool:
    return (system or platform.system()) == "Darwin"


def ui_font_family(system: str | None = None) -> str:
    """Use the native compact UI face available on each supported platform."""
    return "SF Pro Text" if is_macos(system) else "Segoe UI"


def platform_shortcut(sequence: str, system: str | None = None) -> str:
    """Map custom Ctrl shortcuts to the macOS Command key.

    Standard file/edit shortcuts use QKeySequence.StandardKey in the UI. This
    helper is only for application-specific shortcuts that have no StandardKey.
    """
    return sequence.replace("Ctrl+", "Meta+") if is_macos(system) else sequence


def delete_keys(system: str | None = None) -> tuple[str, ...]:
    """Return key names accepted by scoped canvas/tree deletion handling."""
    return ("Delete", "Backspace") if is_macos(system) else ("Delete",)
