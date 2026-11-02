"""Render the repository SVG into a macOS ICNS icon using bundled PySide6."""

from __future__ import annotations

import platform
import subprocess
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer


ICON_FILES = {
    "icon_16x16.png": 16,
    "icon_16x16@2x.png": 32,
    "icon_32x32.png": 32,
    "icon_32x32@2x.png": 64,
    "icon_128x128.png": 128,
    "icon_128x128@2x.png": 256,
    "icon_256x256.png": 256,
    "icon_256x256@2x.png": 512,
    "icon_512x512.png": 512,
    "icon_512x512@2x.png": 1024,
}


def main() -> None:
    if platform.system() != "Darwin":
        raise SystemExit("ICNS generation must run on macOS because it uses iconutil.")

    release_root = Path(__file__).resolve().parent
    svg_path = release_root / "assets" / "kuche7-icon.svg"
    iconset = release_root / "assets" / "Kuche7.iconset"
    output = release_root / "assets" / "Kuche7.icns"
    iconset.mkdir(parents=True, exist_ok=True)

    application = QGuiApplication.instance() or QGuiApplication([])
    renderer = QSvgRenderer(str(svg_path))
    if not renderer.isValid():
        raise ValueError(f"Could not load icon source: {svg_path}")

    for filename, size in ICON_FILES.items():
        image = QImage(size, size, QImage.Format.Format_ARGB32)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        renderer.render(painter)
        painter.end()
        if not image.save(str(iconset / filename), "PNG"):
            raise OSError(f"Could not write {filename}")

    subprocess.run(
        ["iconutil", "--convert", "icns", "--output", str(output), str(iconset)],
        check=True,
    )
    print(output)
    application.quit()


if __name__ == "__main__":
    main()
