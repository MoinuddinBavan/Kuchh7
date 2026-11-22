"""Small deterministic presentation textures; no manufacturing data or assets.

The textures describe only the visible surfaces of existing 3D meshes.  They
are cached so changing selection or orbiting the kitchen does not regenerate
images.  Colours remain tied to the project's selected finish names.
"""

from __future__ import annotations

from functools import lru_cache

import numpy as np
import pyvista as pv


_WOOD_BASE = {
    "Walnut": (111, 80, 62),
    "Natural Oak": (178, 148, 113),
}


def _texture(rgb: np.ndarray) -> pv.Texture:
    return pv.numpy_to_texture(np.ascontiguousarray(np.clip(rgb, 0, 255).astype(np.uint8)))


@lru_cache(maxsize=4)
def wood_texture(finish: str) -> pv.Texture:
    """Quiet longitudinal grain for actual wood finishes, without orange casts."""
    base = np.asarray(_WOOD_BASE[finish], dtype=np.float32)
    size = 256
    u, v = np.meshgrid(np.linspace(0, 1, size), np.linspace(0, 1, size), indexing="ij")
    rng = np.random.default_rng(71 if finish == "Walnut" else 29)
    drift = 0.009 * np.sin(2 * np.pi * (1.7 * u + 0.25 * np.sin(3 * np.pi * u)))
    grain = v + drift + 0.004 * np.sin(2 * np.pi * (3 * u + 2 * v))
    bands = (0.037 * np.sin(2 * np.pi * (10 * grain))
             + 0.016 * np.sin(2 * np.pi * (25 * grain + 0.14 * u))
             + 0.009 * np.sin(2 * np.pi * (55 * grain + 0.3 * u)))
    slow = 0.035 * np.sin(2 * np.pi * (1.2 * u + 0.7 * v))
    fine = rng.normal(0, 0.008, (size, size))
    tone = (1.0 + bands + slow + fine)[..., None]
    return _texture(base[None, None, :] * tone)


@lru_cache(maxsize=2)
def door_wood_texture(tone: str = "panel") -> pv.Texture:
    """Warm, softly varied oak for an opening leaf with no saved finish field."""
    if tone not in ("panel", "frame"):
        raise ValueError(f"Unknown door texture tone: {tone}")
    size = 512
    along, across = np.meshgrid(np.linspace(0, 1, size), np.linspace(0, 1, size), indexing="ij")
    rng = np.random.default_rng(313)
    grain = across + 0.008 * np.sin(2 * np.pi * (1.7 * along + across * 0.8))
    broad = 0.052 * np.sin(2 * np.pi * (7.5 * grain + 0.3 * along))
    narrow = 0.018 * np.sin(2 * np.pi * (31 * grain + 0.4 * along))
    fibre = rng.normal(0, 0.008, (size, size))
    base = np.asarray((157, 116, 83) if tone == "panel" else (134, 95, 68), dtype=np.float32)
    return _texture(base[None, None, :] * (1 + broad + narrow + fibre)[..., None])


@lru_cache(maxsize=1)
def stone_texture() -> pv.Texture:
    """Dark neutral stone with restrained irregular veins for the countertop."""
    size = 512
    u, v = np.meshgrid(np.linspace(0, 1, size), np.linspace(0, 1, size), indexing="ij")
    rng = np.random.default_rng(107)
    base = np.asarray((59, 57, 55), dtype=np.float32)
    mottling = (3.5 * np.sin(2 * np.pi * (2.4 * u + 1.3 * v))
                + 2.4 * np.sin(2 * np.pi * (6.3 * u - 4.1 * v))
                + rng.normal(0, 1.8, (size, size)))
    vein_path = u - (0.36 + 0.11 * np.sin(2 * np.pi * (v * 1.7 + 0.10)))
    vein = np.exp(-((vein_path / 0.004) ** 2)) * 26
    vein2_path = v - (0.70 - 0.19 * u + 0.018 * np.sin(17 * u))
    vein += np.exp(-((vein2_path / 0.0025) ** 2)) * 17
    return _texture(base[None, None, :] + mottling[..., None] + vein[..., None])


@lru_cache(maxsize=1)
def floor_texture() -> pv.Texture:
    """Warm porcelain tiles at demonstration scale, including subtle grout."""
    size = 512
    u, v = np.meshgrid(np.linspace(0, 1, size), np.linspace(0, 1, size), indexing="ij")
    rng = np.random.default_rng(53)
    base = np.asarray((215, 208, 197), dtype=np.float32)
    cloud = (6.5 * np.sin(2 * np.pi * (2.1 * u + 1.3 * v))
             + 3.4 * np.sin(2 * np.pi * (4.8 * u - 3.1 * v))
             + rng.normal(0, 1.3, (size, size)))
    grout = ((np.mod(u * 5, 1) < 0.007) | (np.mod(v * 5, 1) < 0.007))
    colour = base[None, None, :] + cloud[..., None]
    colour[grout] -= 10
    return _texture(colour)


@lru_cache(maxsize=1)
def plaster_texture() -> pv.Texture:
    """Subtle warm mineral plaster; no structural or project material meaning."""
    size = 256
    u, v = np.meshgrid(np.linspace(0, 1, size), np.linspace(0, 1, size), indexing="ij")
    rng = np.random.default_rng(211)
    base = np.asarray((230, 222, 210), dtype=np.float32)
    cloud = (0.8 * np.sin(2 * np.pi * (1.3 * u + 0.8 * v))
             + 0.6 * np.sin(2 * np.pi * (2.1 * v - 1.7 * u))
             + rng.normal(0, 0.45, (size, size)))
    return _texture(base[None, None, :] + cloud[..., None])


@lru_cache(maxsize=1)
def backsplash_texture() -> pv.Texture:
    """Quiet greige stone surface for the existing presentation backsplash."""
    size = 256
    u, v = np.meshgrid(np.linspace(0, 1, size), np.linspace(0, 1, size), indexing="ij")
    rng = np.random.default_rng(223)
    base = np.asarray((207, 197, 184), dtype=np.float32)
    cloud = (3.0 * np.sin(2 * np.pi * (1.9 * u + 1.2 * v))
             + 1.9 * np.sin(2 * np.pi * (4.2 * u - 3.0 * v))
             + rng.normal(0, 1.1, (size, size)))
    vein = np.exp(-(((v - 0.42 - 0.05 * np.sin(6 * u)) / 0.006) ** 2)) * 11
    return _texture(base[None, None, :] + cloud[..., None] + vein[..., None])


@lru_cache(maxsize=1)
def garden_texture() -> pv.Texture:
    """Soft, distant greenery seen through an existing saved window opening."""
    size = 256
    yy, xx = np.mgrid[:size, :size]
    sky = np.asarray((207, 218, 215), dtype=np.float32)
    colour = np.broadcast_to(sky, (size, size, 3)).copy()
    colour -= (yy / size)[..., None] * np.asarray((25, 17, 21), dtype=np.float32)
    rng = np.random.default_rng(139)
    for _ in range(42):
        cx, cy = int(rng.integers(-20, size + 20)), int(rng.integers(93, size + 35))
        rx, ry = int(rng.integers(15, 48)), int(rng.integers(18, 55))
        radius = ((xx - cx) / rx) ** 2 + ((yy - cy) / ry) ** 2
        alpha = np.clip((1.2 - radius) * 0.55, 0, 0.60)
        shade = rng.integers(-12, 13)
        leaf = np.asarray((93 + shade, 124 + shade, 82 + shade), dtype=np.float32)
        colour = colour * (1 - alpha[..., None]) + leaf * alpha[..., None]
    for _ in range(150):
        cx, cy = int(rng.integers(0, size)), int(rng.integers(82, size))
        rx, ry = int(rng.integers(3, 11)), int(rng.integers(5, 15))
        radius = ((xx - cx) / rx) ** 2 + ((yy - cy) / ry) ** 2
        alpha = np.clip((1.0 - radius) * 0.42, 0, 0.42)
        shade = rng.integers(-13, 14)
        leaf = np.asarray((80 + shade, 109 + shade, 69 + shade), dtype=np.float32)
        colour = colour * (1 - alpha[..., None]) + leaf * alpha[..., None]
    # Diffuse exterior focus keeps foliage from resembling flat vector circles.
    for _ in range(1):
        colour = (4 * colour + np.roll(colour, 1, axis=0) + np.roll(colour, -1, axis=0)
                  + np.roll(colour, 1, axis=1) + np.roll(colour, -1, axis=1)) / 8
    return _texture(colour)


def map_surface(
    mesh: pv.PolyData,
    orientation: str,
    extent: tuple[float, float, float, float, float, float] | None = None,
) -> pv.PolyData:
    """Attach texture coordinates in model millimetres to an existing box."""
    x0, x1, y0, y1, z0, z1 = extent or mesh.bounds
    if orientation == "top":
        origin, u, v = (x0, y0, z1), (x1, y0, z1), (x0, y1, z1)
    elif orientation == "side":
        origin, u, v = (x0, y0, z0), (x0, y1, z0), (x0, y0, z1)
    else:
        origin, u, v = (x0, y0, z0), (x1, y0, z0), (x0, y0, z1)
    return mesh.texture_map_to_plane(origin=origin, point_u=u, point_v=v)
