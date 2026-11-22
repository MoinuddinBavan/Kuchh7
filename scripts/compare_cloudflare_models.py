"""Internal, explicitly authorized comparison of Workers AI edits of one PNG.

Dry run is the default. No network call occurs without --execute --approve-usage.
The same source bytes, prompt and output dimensions are used for every model.
"""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path

from kuchhe7.rendering import (CLOUDFLARE_IMAGE_MODEL,
                              CloudflareImageEditProvider, RenderRequest,
                              save_png)


COMPARISON_PROMPT = (
    "Transform input image 0, the supplied 3D kitchen image, into a premium photorealistic "
    "architectural photograph of the same kitchen. Preserve its composition, camera view, cabinet "
    "count, placement, types, colours, wood finishes, dark countertop, sink, and original door and "
    "window positions. Keep the tall dark brown pantry as a storage cabinet, the grey and beige "
    "base cabinets, and the white wall cabinet and adjacent dark brown open shelving. Enhance only "
    "realism through believable material textures, natural lighting, physically plausible shadows, "
    "realistic reflections and professional interior photography. Do not add or remove cabinets, "
    "replace the pantry with a refrigerator, add an island, recolour furniture or change the room."
)
COMPARISON_MODELS = (
    CLOUDFLARE_IMAGE_MODEL,
    "@cf/black-forest-labs/flux-2-dev",
)
OPTIONAL_MODEL = "@cf/black-forest-labs/flux-2-klein-9b"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True, help="One complete-room PNG capture")
    parser.add_argument("--output-dir", type=Path, default=Path("demo_output/cloudflare-model-comparison"))
    parser.add_argument("--include-9b", action="store_true", help="Include the optional, separately priced model")
    parser.add_argument("--execute", action="store_true", help="Allow live Workers AI requests")
    parser.add_argument("--approve-usage", action="store_true", help="Confirm API usage and possible charges")
    args = parser.parse_args(argv)
    source = args.source.read_bytes()
    request = RenderRequest(source, "Luxury kitchen presentation")
    request.validate()
    models = (*COMPARISON_MODELS, OPTIONAL_MODEL) if args.include_9b else COMPARISON_MODELS
    print(f"Source SHA-256: {hashlib.sha256(source).hexdigest()}")
    print(f"Models: {', '.join(model.rsplit('/', 1)[-1] for model in models)}")
    if not args.execute:
        print("Dry run: no images generated and no API requests sent.")
        return 0
    if not args.approve_usage:
        parser.error("Live comparison requires --approve-usage.")
    account_id = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "").strip()
    api_token = os.environ.get("CLOUDFLARE_API_TOKEN", "").strip()
    if not account_id or not api_token:
        parser.error("Set CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN in the environment.")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    save_png(source, args.output_dir / "source.png")
    for model in models:
        provider = CloudflareImageEditProvider(account_id, api_token, model=model,
                                               comparison_prompt=COMPARISON_PROMPT,
                                               timeout_seconds=180)
        try:
            result = provider.render(request)
        except RuntimeError as error:
            print(f"{model.rsplit('/', 1)[-1]}: failed: {error}")
            return 1  # No automatic retry or additional paid call.
        destination = args.output_dir / f"{model.rsplit('/', 1)[-1]}.png"
        save_png(result, destination)
        print(f"{model.rsplit('/', 1)[-1]}: saved {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
