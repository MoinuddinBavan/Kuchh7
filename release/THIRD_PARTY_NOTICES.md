# Third-party licensing notice — kuchhe7 Client Approval Demo v1.0

This file is release-engineering guidance, not legal advice. AIZ INFOTECHS must
complete its own license review before distributing the package commercially.

## Qt for Python / PySide6

The current development environment contains the Community Edition package
`PySide6_Essentials 6.12.0`, whose installed metadata identifies it as
`LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only`. Qt for Python is dual-licensed:
commercial Qt packages are also available.

For an LGPL distribution, the release owner must satisfy all applicable LGPLv3
conditions. Qt's published guidance includes providing license notices and the
corresponding Qt source or a controlled written offer, preserving the recipient's
right to replace/relink the dynamically shipped Qt libraries, permitting the
required reverse engineering for that purpose, and avoiding incompatible DRM or
distribution restrictions. Do not replace the one-directory package with a
statically linked or locked-down distribution without a fresh legal review.

If those obligations do not match the intended commercial distribution model,
obtain and build with the appropriate Qt commercial packages rather than the
Community Edition wheels.

Authoritative references:

- https://doc.qt.io/qtforpython-6/commercial/index.html
- https://doc.qt.io/qtforpython-6/licenses.html
- https://www.qt.io/development/open-source-lgpl-obligations

## PyInstaller and other libraries

PyInstaller is a build tool and its bootloader exception permits bundled
commercial applications; verify the version-specific license included with the
installed tool. PyVistaQt is MIT licensed and VTK is BSD licensed according to
their installed package metadata. Other runtime dependencies retain their own
licenses and notices.

The `licenses` directory included beside the executable is generated from the
installed distributions by `release/collect_licenses.py`. Review its manifest
and every bundled notice before external distribution. Re-run the collector
whenever dependency versions change.

- https://pyinstaller.org/en/stable/license.html
