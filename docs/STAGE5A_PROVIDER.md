# Stage 5A prompt-to-JSON provider contract

The built-in design assistant uses a **local rule-based demonstration**, not an
AI model. It proposes existing KÜCHE7 catalogue models with their unchanged
default dimensions. Cabinet orientation is fixed by the current project model.
An L-footprint proposal is therefore not a fully rotated L-shaped installation.

An optional service adapter can be configured through process environment
variables. No credential is stored in project JSON or source code:

```powershell
$env:KUCHE7_AI_ENDPOINT = "https://your-approved-service.example/design"
$env:KUCHE7_AI_API_KEY = "<set securely in your local environment>"
```

The endpoint must use HTTPS or local loopback HTTP. The desktop application
sends a POST JSON body with `prompt`, `room_mm`, `openings`,
`catalogue_type_ids`, and an `instructions` string. It expects JSON such as:

```json
{
  "layout": "Straight",
  "items": [
    {"type_id": "base_2_door", "x": 200, "y": 2600, "finish": "Cashmere", "orientation_degrees": 0}
  ],
  "warnings": [],
  "explanation": "Uses supported catalogue furniture."
}
```

The remote response is **untrusted interpretation**, not project geometry.
KÜCHE7 ignores any supplied custom width, height, depth or board thickness;
requires existing catalogue IDs and finishes; rejects unsupported rotations;
checks actual room, opening, cabinet and product collisions; and validates the
resulting project before enabling Apply. Explicit remote positions are not
silently moved. If the service fails, the UI labels the fallback as local
rule-based demonstration and shows a warning.

Before live use, the client must choose and approve a model/provider, endpoint,
data handling policy, authentication arrangement, prompt/response contract,
service availability expectations, and human acceptance criteria. API calls
have not been tested against a real service in this milestone; automated tests
use a mocked response.
