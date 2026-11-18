# Stage 5C: OpenAI image edit for client presentation

KÜCHE7 continues to save a standard 3D PNG locally without an API key. When
configured, the Realistic Rendering workspace submits that PNG as the **input
image** to OpenAI's current Images API `/v1/images/edits` endpoint. The request
uses a GPT Image editing model, a layout-preservation prompt and one PNG output.
It does not send the project JSON, customer name, BOM, prices or dimensions as
separate fields. The image itself may reveal the client design.

Official reference: https://developers.openai.com/api/reference/resources/images/methods/edit
and https://developers.openai.com/api/docs/guides/image-generation

## Local configuration on Windows

Set the key in a trusted process environment before starting the app. Do not
paste a real key into source, project JSON, screenshots, shell history shared
with others, or a committed configuration file. `.env` and `.env.*` are ignored
by Git, but the app does not automatically load them.

```powershell
$env:KUCHE7_RENDER_PROVIDER = 'openai'
$env:OPENAI_API_KEY = '<key from a secure local store>'
$env:KUCHE7_OPENAI_IMAGE_MODEL = 'gpt-image-2.5-sunburst'
$env:KUCHE7_OPENAI_IMAGE_QUALITY = 'medium'
$env:KUCHE7_OPENAI_IMAGE_SIZE = '1536x1024'
.\.venv\Scripts\python.exe -m kuchhe7
```

The default model is `gpt-image-2.5-sunburst`. Other allowed models are
`gpt-image-2.5-flare`, `gpt-image-2.6-sunburst` and `gpt-image-2.6-flare`.
Allowed quality values are `low`, `medium`, `high`; allowed sizes are
`1024x1024`, `1536x1024`, `1024x1536`. The adapter uses HTTPS, a 90-second
timeout and validates the returned PNG. It never falls back to a standard 3D
capture while labelling it as AI output. An existing custom provider remains
available through `KUCHE7_RENDER_PROVIDER=custom` and
`KUCHE7_RENDER_ENDPOINT` as documented for Stage 5B.

Open **View → Realistic Rendering**, capture the current 3D view, select a style,
enter optional visual instructions, then choose **Generate AI render**. Confirm
the external upload. Compare the result against the source before saving.
Generation may incur API charges. A declined, failed or timed-out request leaves
the source capture available and can be retried. The generated PNG is a separate
presentation artifact and never updates design or manufacturing data.

No live OpenAI request was run without a configured API key. Mocked adapter
tests establish request shape and failure handling only; account access,
billing and live image quality remain to be verified with an authorized key.
For commercial deployment, put credentials and usage limits behind a controlled
server rather than distributing an API key inside employee desktop packages.
Review client consent, image retention and data-processing terms before sending
confidential designs. AI images cannot certify exact cabinet geometry.
