# Stage 5B image rendering adapter

The desktop capture works locally. No live AI image provider has been approved,
configured or verified in this repository. Do not describe a local PyVista PNG
as an AI render.

An approved service must accept image input, preserve the supplied layout as
closely as possible, and have acceptable privacy, retention, licensing and
commercial terms. Configure its HTTPS endpoint and token in the employee's
process environment, outside project JSON and source files:

```powershell
$env:KUCHE7_RENDER_ENDPOINT = 'https://approved-service.example/render'
$env:KUCHE7_RENDER_API_KEY = '<credential from a secure store>'
.\.venv\Scripts\python.exe -m kuchhe7
```

Local loopback HTTP is accepted for development. The adapter posts JSON with
`image_base64` (PNG), `style`, `instructions`, and `output_format: "png"`.
The service must return JSON with `image_base64` containing a valid PNG. A
90-second timeout and 20 MB image limit apply. Provider calls run in a Qt worker
thread. The application asks for confirmation before each upload, and sends no
project JSON, customer name, dimensions, BOM or price data. The image itself
may reveal the design.

This generic adapter has only mocked contract tests. Service-specific API
authentication, endpoint shape, limits and output rights must be checked with
the actual approved provider before a live integration can be claimed.
AI images may diverge from true cabinet geometry and must never be used as
measurements or manufacturing instructions.
