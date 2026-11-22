"""Lightweight procedural geometry for visual-only decorative library items."""

from __future__ import annotations

from math import cos, pi, sin

import pyvista as pv


def add_curated_prop_geometry(plotter, product, definition, x: float, y: float, z: float,
                              name: str) -> None:
    """Draw decorative meshes from the persisted size and orientation, without BOM parts."""
    w, d, h = product.width, product.depth, product.height
    cx, cy = w / 2, d / 2
    angle = product.orientation_degrees
    shifts = {0: (x, y), 90: (x + d, y), 180: (x + w, y + d), 270: (x, y + w)}
    dx, dy = shifts[angle]

    def add(part: str, mesh, colour: str, *, specular: float = 0.12) -> None:
        if angle:
            mesh.rotate_z(angle, inplace=True)
        mesh.translate((dx, dy, z), inplace=True)
        plotter.add_mesh(mesh, name=f"{name}-{part}", color=colour, show_edges=False,
                         ambient=0.34, diffuse=0.66, specular=specular,
                         specular_power=24, smooth_shading=True)

    def cylinder(part: str, u: float, v: float, bottom: float, height: float,
                 radius: float, colour: str, *, specular: float = 0.12) -> None:
        add(part, pv.Cylinder(center=(u, v, bottom + height / 2), direction=(0, 0, 1),
                              radius=radius, height=height, resolution=16), colour,
            specular=specular)

    def ellipsoid(part: str, u: float, v: float, t: float, rx: float, ry: float,
                  rz: float, colour: str, *, specular: float = 0.12) -> None:
        mesh = pv.Sphere(radius=1, theta_resolution=14, phi_resolution=10)
        mesh.scale((rx, ry, rz), inplace=True)
        mesh.translate((u, v, t), inplace=True)
        add(part, mesh, colour, specular=specular)

    def stem(part: str, a: tuple[float, float, float], b: tuple[float, float, float],
             radius: float, colour: str) -> None:
        add(part, pv.Line(a, b).tube(radius=radius, n_sides=6), colour)

    shape = definition.shape
    if shape in ("potted_green_plant", "floor_plant"):
        floor = shape == "floor_plant"
        pot_h = h * (0.26 if floor else 0.34)
        pot_r = min(w, d) * (0.29 if floor else 0.34)
        cylinder("ceramic-pot", cx, cy, 0, pot_h, pot_r, "#B9AEA0", specular=0.16)
        cylinder("pot-rim", cx, cy, pot_h - h * 0.025, h * 0.025,
                 pot_r * 1.07, "#D0C6B9", specular=0.18)
        cylinder("soil", cx, cy, pot_h, h * 0.008, pot_r * 0.82, "#4E4238")
        for index in range(7 if floor else 5):
            phi = index * 2 * pi / (7 if floor else 5)
            reach = min(w, d) * (0.28 if floor else 0.25)
            tip = (cx + cos(phi) * reach, cy + sin(phi) * reach,
                   h * (0.76 + 0.19 * (index % 3) / 2))
            stem(f"stem-{index}", (cx, cy, pot_h), tip, max(2.5, min(w, d) * 0.015), "#53684A")
            for leaf in range(2):
                fraction = 0.58 + 0.25 * leaf
                side = 1 if leaf == 0 else -1
                u = cx + (tip[0] - cx) * fraction + side * sin(phi) * reach * 0.25
                v = cy + (tip[1] - cy) * fraction - side * cos(phi) * reach * 0.25
                t = pot_h + (tip[2] - pot_h) * fraction
                ellipsoid(f"leaf-{index}-{leaf}", u, v, t,
                          min(w, d) * 0.15, min(w, d) * 0.065, h * 0.035,
                          ("#416D4C", "#628759", "#789565")[index % 3])
        return

    if shape in ("flower_vase", "decorative_vase"):
        flowers = shape == "flower_vase"
        vase_h = h * (0.48 if flowers else 0.67)
        radius = min(w, d) * (0.26 if flowers else 0.33)
        ellipsoid("vase-body", cx, cy, vase_h * 0.48, radius, radius * 0.9,
                  vase_h * 0.48, "#C7CECA" if flowers else "#B5A593", specular=0.28 if flowers else 0.13)
        cylinder("vase-neck", cx, cy, vase_h * 0.70, vase_h * 0.30,
                 radius * 0.47, "#D9DDD7" if flowers else "#C1B09D", specular=0.24)
        for index in range(5 if flowers else 4):
            phi = index * 2 * pi / (5 if flowers else 4)
            reach = min(w, d) * (0.23 if flowers else 0.30)
            tip = (cx + cos(phi) * reach, cy + sin(phi) * reach,
                   h * (0.79 + 0.16 * (index % 3) / 2))
            stem(f"branch-{index}", (cx, cy, vase_h * 0.88), tip,
                 max(1.7, min(w, d) * 0.009), "#53745A" if flowers else "#8D765E")
            if flowers:
                ellipsoid(f"flower-center-{index}", *tip, h * 0.024, h * 0.024,
                          h * 0.025, "#D6B36F")
                for petal in range(5):
                    theta = petal * 2 * pi / 5
                    ellipsoid(f"petal-{index}-{petal}",
                              tip[0] + cos(theta) * h * 0.042,
                              tip[1] + sin(theta) * h * 0.042, tip[2],
                              h * 0.038, h * 0.029, h * 0.016,
                              ("#DDB8AE", "#F0E3CE", "#C98C88")[index % 3])
                ellipsoid(f"flower-leaf-{index}",
                          (cx + tip[0]) / 2, (cy + tip[1]) / 2, vase_h + (tip[2] - vase_h) * 0.35,
                          min(w, d) * 0.105, min(w, d) * 0.045, h * 0.018, "#597A5A")
            else:
                for seed in range(3):
                    ellipsoid(f"seed-{index}-{seed}", tip[0] + (seed - 1) * reach * 0.13,
                              tip[1], tip[2] - seed * h * 0.035,
                              h * 0.012, h * 0.009, h * 0.026, "#B79E7D")
        return

    if shape == "fruit_bowl":
        ellipsoid("bowl", cx, cy, h * 0.24, w * 0.42, d * 0.42, h * 0.22,
                  "#D5C5A8", specular=0.16)
        ellipsoid("bowl-inside", cx, cy, h * 0.43, w * 0.36, d * 0.35, h * 0.06,
                  "#A89981")
        for index, (u, v, colour) in enumerate(((0.35, 0.40, "#B98550"),
                                                  (0.62, 0.38, "#9D6245"),
                                                  (0.48, 0.64, "#AEB66A"),
                                                  (0.72, 0.59, "#C2A35D"))):
            ellipsoid(f"fruit-{index}", w * u, d * v, h * 0.64,
                      min(w, d) * 0.14, min(w, d) * 0.14, h * 0.24, colour,
                      specular=0.18)
            stem(f"fruit-stem-{index}", (w * u, d * v, h * 0.83),
                 (w * u + 4, d * v, h * 0.93), 1.6, "#625942")
        return

    if shape == "utensil_holder":
        jar_h = h * 0.58
        cylinder("holder", cx, cy, 0, jar_h, min(w, d) * 0.34,
                 "#D0C5B4", specular=0.15)
        cylinder("holder-rim", cx, cy, jar_h - h * 0.025, h * 0.025,
                 min(w, d) * 0.36, "#E4D9C8")
        for index, (u, v) in enumerate(((0.35, 0.43), (0.50, 0.55), (0.64, 0.42), (0.52, 0.34))):
            x0, y0 = w * u, d * v
            top = h * (0.84 + index * 0.035)
            stem(f"utensil-shaft-{index}", (x0, y0, jar_h * 0.42),
                 (x0 + (index - 1.5) * w * 0.035, y0, top),
                 max(2.0, w * 0.018), "#A97C54")
            ellipsoid(f"utensil-head-{index}", x0 + (index - 1.5) * w * 0.035,
                      y0, top, w * (0.08 if index % 2 else 0.055),
                      d * 0.04, h * 0.045, "#B88C60")
        return

    if shape == "decorative_tray":
        tray_h = h * 0.18
        add("tray", pv.Box(bounds=(w * 0.04, w * 0.96, d * 0.06, d * 0.94,
                                    0, tray_h)), "#A89986")
        for index, u in enumerate((0.36, 0.66)):
            cylinder(f"cup-{index}", w * u, cy, tray_h, h * 0.55,
                     min(w, d) * 0.12, "#E5DFD3", specular=0.23)
            cylinder(f"cup-inside-{index}", w * u, cy, tray_h + h * 0.54,
                     h * 0.01, min(w, d) * 0.09, "#8A7B69")
        return

    if shape == "small_sculpture":
        ellipsoid("ceramic-base", cx, cy, h * 0.11, w * 0.33, d * 0.33,
                  h * 0.11, "#D7CFC3", specular=0.18)
        for index, side in enumerate((-1, 1)):
            points = [
                (cx + side * w * 0.16, cy, h * 0.19),
                (cx + side * w * 0.27, cy, h * 0.55),
                (cx + side * w * 0.11, cy, h * 0.88),
                (cx, cy, h * 0.91),
            ]
            add(f"ceramic-curve-{index}", pv.Spline(points, n_points=24).tube(
                radius=min(w, d) * 0.065, n_sides=8), "#D8D0C4", specular=0.20)
        return

    raise ValueError(f"No decorative geometry for {definition.type_id}.")
