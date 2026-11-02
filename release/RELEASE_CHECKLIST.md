# kuchhe7 Client Approval Demo v1.0 — release checklist

## Release evidence

- [x] Non-overwriting v0.9 source/demo backup created
- [x] Source suite passes with a writable local pytest directory
- [x] JSON persistence, BOM, XLSX and DXF regressions pass
- [x] Nesting quantity reconciliation and rectangle geometry pass
- [x] Layout freshness and placement completeness are distinct
- [x] Production-use disclaimers remain visible
- [x] PyInstaller package built successfully
- [x] Packaged executable launched outside `.venv`
- [x] Packaged release smoke sequence passed in fresh writable app-data folders
- [x] Packaged application closed and relaunched successfully
- [x] Final 1920 × 1080 screenshots visually reviewed

## Before any external distribution

- [ ] Decide between a compliant Qt LGPL distribution and Qt commercial licensing
- [ ] Review all files in the bundled `licenses` directory
- [ ] Provide the required Qt source/written offer and relinking information if LGPL is used
- [ ] Code-sign the executable and installer if required by the client
- [ ] Virus-scan the final package in the delivery environment
- [ ] Confirm client-approved naming, versioning and delivery channel

The checklist deliberately does not approve CNC, IMOS, factory machining,
production cutting or manufacturing interoperability.
