# Cloudflare Workers AI rendering

The existing **View → Realistic Rendering** workspace can use Cloudflare Workers AI alongside OpenAI and Gemini. Select **Cloudflare Workers AI**, capture the actual 3D design, choose a style, then use **Generate AI render**. The existing confirmation prompt appears before the image leaves the computer. The returned image appears in the before/after preview and can be saved as PNG.

Set `CLOUDFLARE_ACCOUNT_ID` and `CLOUDFLARE_API_TOKEN` in the process environment from a secure local store before launching KÜCHE7. A token needs the appropriate Workers AI permission. Do not copy credentials from the temporary demo module into source files, project JSON, Git, screenshots, logs or command examples. The application never imports that module. With no Cloudflare credentials, normal 3D capture and PNG export remain available.

The adapter uses Cloudflare's hosted `@cf/black-forest-labs/flux-2-klein-4b` image-editing model. It sends the existing 3D PNG, reduced to fit within a 500 × 500 pixel reference frame, as multipart `input_image_0` with a design-preserving style prompt. The prompt also includes a compact snapshot of cabinet finishes, dimensions and positions, plus room-opening locations and sizes; it excludes customer names, prices and manufacturing records. The confirmation dialog identifies this information before upload. The workspace defaults to KÜCHE7's complete-room Presentation camera, temporarily showing the presentation environment for capture and then restoring the prior CAD view. It requests a supported 1536 × 864 (16:9) image to match the source framing and converts supported image responses to PNG for the current preview. Rendering stays on the workspace's existing background thread. AI results are presentation images and may not preserve exact cabinet geometry; they never change project, BOM, quotation, nesting or engineering data.

Cloudflare documents the [FLUX.2 Klein model](https://developers.cloudflare.com/workers-ai/models/flux-2-klein-4b/) and its [multipart reference-image request](https://developers.cloudflare.com/changelog/post/2026-01-15-flux-2-klein-4b-workers-ai/). API usage may incur charges. For a distributed desktop product, protect credentials with a server-side service and usage controls rather than shipping an API token to users.

## Internal model comparison

The normal workspace still defaults to Klein 4B. For an internal trial, set `KUCHE7_CLOUDFLARE_IMAGE_MODEL` to `@cf/black-forest-labs/flux-2-dev` or `@cf/black-forest-labs/flux-2-klein-9b`; no model selector was added to the UI. The adapter sends a 500-pixel reference image, below Cloudflare's 512-by-512 input limit, and requests 1536-by-864 output. Dev alone receives 25 inference steps, matching Cloudflare's documented example; Klein 4B and 9B use their fixed four-step process.

To compare the same source and concise prompt without changing the current project, run this dry run from the project root:

```powershell
.\.venv\Scripts\python.exe -m scripts.compare_cloudflare_models --source "demo_output\rendering-quality-20261119\sample-kitchen-presentation-source.png"
```

With valid environment credentials and explicit usage approval, add `--execute --approve-usage`. Add `--include-9b` only if the extra model and its pricing are accepted. Results are written separately under `demo_output/cloudflare-model-comparison`; no automatic retries occur. Visually compare cabinet counts, colours, pantry identity, openings, countertop, sink and photographic quality before choosing a model. A model cannot be recommended from documentation or mocked tests alone.

See Cloudflare's [Dev](https://developers.cloudflare.com/changelog/post/2025-11-25-flux-2-dev-workers-ai/), [Klein 9B](https://developers.cloudflare.com/changelog/post/2026-01-28-flux-2-klein-9b-workers-ai/) and [current image pricing](https://developers.cloudflare.com/workers-ai/platform/pricing/) documentation.
