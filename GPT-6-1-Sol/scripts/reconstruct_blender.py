"""Rebuild Kenney isometric sprites as closed low-poly Blender shadow proxies.

Run: blender --background --python scripts/reconstruct_blender.py
The production depth buffers are triangle-rasterized from Blender's evaluated
meshes, so their precision does not depend on display colour management.
"""
from __future__ import annotations
import argparse
import json
import math
import struct
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "generated"
W, H, LAYERS = 918, 515, 4
ORIGIN = np.array([W / 2, H / 2], dtype=np.float64)
RIGHT = np.array([1 / math.sqrt(2), -1 / math.sqrt(2), 0.0])
DOWN = np.array([1 / math.sqrt(8), 1 / math.sqrt(8), -math.sqrt(3) / 2])
TOWARD = np.array([math.sqrt(3 / 8), math.sqrt(3 / 8), 0.5])
BASIS = np.stack([RIGHT, DOWN, TOWARD])
SCALE = 0.8
STORY = 35 * SCALE / (math.sqrt(3) / 2)
objects = []
materials = {}


def mat(name, color):
    if name not in materials:
        m = bpy.data.materials.new(name)
        m.diffuse_color = (*color, 1)
        materials[name] = m
    return materials[name]


def world_at(screen_x, screen_y, z=0):
    qx, qy = screen_x - ORIGIN[0], screen_y - ORIGIN[1]
    total = (qy + math.sqrt(3) * z / 2) * math.sqrt(8)
    return np.array([(total + qx * math.sqrt(2)) / 2,
                     (total - qx * math.sqrt(2)) / 2, z])


def box_mesh(name, sx, sy, sz, center=(0, 0, 0), material=None, collection=None,
             track=True):
    x, y, z = center
    vertices = [(x + a * sx / 2, y + b * sy / 2, z + c * sz / 2)
                for c in (-1, 1) for b in (-1, 1) for a in (-1, 1)]
    faces = [(0, 2, 3, 1), (4, 5, 7, 6), (0, 1, 5, 4),
             (2, 6, 7, 3), (0, 4, 6, 2), (1, 3, 7, 5)]
    mesh = bpy.data.meshes.new(name + "_mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    ob = bpy.data.objects.new(name, mesh)
    (collection or bpy.context.scene.collection).objects.link(ob)
    if material:
        ob.data.materials.append(material)
    if track:
        objects.append(ob)
    return ob


def polygon_prism(name, points, height, material, top_z=0):
    """Closed ground island; input points are projected vertices of its top."""
    vertices = [tuple(world_at(x, y, top_z)) for x, y in points]
    vertices += [tuple(np.array(v) - np.array([0, 0, height])) for v in vertices]
    n = len(points)
    # Ear-clipping handles the concave pavement outline before export.
    from mathutils.geometry import tessellate_polygon
    top = [Vector(v) for v in vertices[:n]]
    faces = []
    for tri in tessellate_polygon([top]):
        ids = [int(v) if isinstance(v, int) else min(range(n), key=lambda i: (top[i] - v).length_squared) for v in tri]
        faces.append(tuple(ids))
        faces.append(tuple(i + n for i in reversed(ids)))
    faces.extend((i, (i + 1) % n, (i + 1) % n + n, i + n) for i in range(n))
    mesh = bpy.data.meshes.new(name + "_mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    ob = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(ob)
    ob.data.materials.append(material)
    objects.append(ob)
    return ob


def native_size(path):
    with path.open("rb") as f:
        f.seek(16)
        return struct.unpack(">II", f.read(8))


def asset_kind(index, width, height):
    if index == 78:
        return "chimney"
    if height >= 85:
        return "base" if width >= 130 else "story"
    return "roof"


def make_asset_library():
    coll = bpy.data.collections.new("Reusable asset proxy library (all 129 sprites)")
    bpy.context.scene.collection.children.link(coll)
    coll.hide_render = True
    coll.hide_viewport = True
    catalog = []
    for path in sorted((ROOT / "assets").glob("*.png")):
        index = int(path.stem.split("_")[-1])
        width, height = native_size(path)
        kind = asset_kind(index, width, height)
        asset_collection = bpy.data.collections.new(path.stem + " reusable geometry")
        coll.children.link(asset_collection)
        start = len(objects)
        create_sprite_geometry({"asset": path.name, "id": path.stem + "_prototype",
                                "x": ORIGIN[0] - width / 2,
                                "y": ORIGIN[1] - 60, "scale": 1.0}, 0)
        prototype_objects = objects[start:]
        for ob in prototype_objects:
            bpy.context.scene.collection.objects.unlink(ob)
            asset_collection.objects.link(ob)
            ob["sprite"] = path.name
            ob["native_width"], ob["native_height"] = width, height
            ob["reconstruction"] = "closed orthographic low-poly proxy"
        del objects[start:]
        catalog.append({"asset": path.name, "kind": kind, "width": width,
                        "height": height, "meshes": [ob.data.name for ob in prototype_objects]})
    (OUT / "asset-proxy-catalog.json").write_text(json.dumps(catalog, indent=2))


def color_for(index):
    if index in {1, 2, 9, 10, 16, 17, 18, 23, 25, 26, 30, 33, 34, 36,
                 40, 41, 45, 46, 49, 52, 54, 92, 99, 106, 113, 114, 122, 123}:
        return (0.57, 0.23, 0.23)
    if index in {14, 21, 32, 38, 43, 47}:
        return (0.58, 0.44, 0.29)
    return (0.69, 0.68, 0.45)


def roof_ring(label, center, side, roof_z, scale):
    thickness, height = 4 * scale, 4 * scale
    for axis in range(2):
        for sign in (-1, 1):
            c = np.array(center).copy()
            c[axis] += sign * (side - thickness) / 2
            c[2] = roof_z + height / 2
            sizes = [side, side, height]
            sizes[axis] = thickness
            box_mesh(label + f"_parapet_{axis}_{sign}", *sizes, center=c,
                     material=mat("Roof parapet", (0.82, 0.81, 0.72)))


def create_sprite_geometry(sprite, z_bottom, include_foundation=True):
    asset = sprite["asset"]
    if isinstance(asset, int):
        asset = f"buildingTiles_{asset:03d}.png"
    asset = Path(asset).name
    index = int(Path(asset).stem.split("_")[-1])
    native_w, native_h = native_size(ROOT / "assets" / asset)
    scale = float(sprite.get("scale", SCALE))
    x, y = float(sprite["x"]), float(sprite["y"])
    kind = asset_kind(index, native_w, native_h)
    side = min(native_w, 99) * scale / math.sqrt(2)
    label = str(sprite.get("id", f"sprite_{len(objects)}"))
    if kind == "chimney":
        c = world_at(x + native_w * scale / 2, y + native_h * scale, z_bottom)
        c[2] += 12 * scale
        box_mesh(label, 12 * scale, 12 * scale, 24 * scale, center=c,
                 material=mat("Chimney turquoise", (0.36, 0.65, 0.71)))
        return
    if kind == "roof":
        if native_h >= 60:
            # The sample's dark small-shop roof is a closed shed roof. Its
            # four projected corners follow the source sprite rather than
            # expanding its shadow to an axis-aligned screen rectangle.
            points = [(0, 0.41 * native_h), (0.25 * native_w, 0),
                      (native_w, 0.60 * native_h), (0.75 * native_w, native_h)]
            heights = [z_bottom, z_bottom + 14 * scale,
                       z_bottom + 14 * scale, z_bottom]
            v = [tuple(world_at(x + px * scale, y + py * scale, zz))
                 for (px, py), zz in zip(points, heights)]
            v += [tuple(np.array(a) - np.array([0, 0, 3 * scale])) for a in v]
            faces = [(0, 1, 2, 3), (7, 6, 5, 4), (0, 4, 5, 1),
                     (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0)]
            mesh = bpy.data.meshes.new(label + "_shed_mesh")
            mesh.from_pydata(v, [], faces)
            mesh.update()
            ob = bpy.data.objects.new(label + "_shed_roof", mesh)
            bpy.context.scene.collection.objects.link(ob)
            ob.data.materials.append(mat("Shed roof", (0.43, 0.44, 0.43)))
            objects.append(ob)
            return
        center = world_at(x + native_w * scale / 2, y + 25 * scale, z_bottom)
        center[2] += 1.5 * scale
        box_mesh(label + "_roof_slab", side, side, 3 * scale, center=center,
                 material=mat("Roof slab", (0.76, 0.75, 0.65)))
        roof_ring(label, center, side, z_bottom + 3 * scale, scale)
        return
    center = world_at(x + native_w * scale / 2, y + 60 * scale, z_bottom)
    height = 35 * scale / (math.sqrt(3) / 2)
    wall_center = center.copy()
    wall_height = height - 4 * scale
    wall_center[2] += wall_height / 2
    ob = box_mesh(label + "_walls", side, side, wall_height, center=wall_center,
                  material=mat("Wall " + str(index), color_for(index)))
    ob["sprite"], ob["z_bottom"] = asset, z_bottom
    roof_ring(label, center, side, z_bottom + height - 4 * scale, scale)
    if kind == "base" and include_foundation:
        tile_center = world_at(x + native_w * scale / 2, y + 59 * scale, z_bottom)
        tile_height = 35 * scale / (math.sqrt(3) / 2)
        tile_center[2] -= tile_height / 2
        box_mesh(label + "_sidewalk_foundation", 132 * scale / math.sqrt(2),
                 132 * scale / math.sqrt(2), tile_height, center=tile_center,
                 material=mat("Sandstone foundation", (0.66, 0.56, 0.4)))


def assign_story_heights(sprites):
    """Use explicit heights when supplied; otherwise group aligned story centers."""
    groups = []
    for s in sprites:
        a = s["asset"]
        name = f"buildingTiles_{a:03d}.png" if isinstance(a, int) else Path(a).name
        nw, nh = native_size(ROOT / "assets" / name)
        if asset_kind(int(Path(name).stem.split("_")[-1]), nw, nh) not in {"base", "story"}:
            continue
        scale = float(s.get("scale", SCALE))
        cx = s["x"] + nw * scale / 2
        key = s.get("building")
        found = next((g for g in groups if (key and g["key"] == key) or
                      (not key and abs(g["x"] - cx) < 4)), None)
        if found is None:
            found = {"key": key, "x": cx, "sprites": []}
            groups.append(found)
        found["sprites"].append(s)
    for g in groups:
        floor_sprites = sorted(g["sprites"], key=lambda s: s["y"], reverse=True)
        for i, s in enumerate(floor_sprites):
            local_story = 35 * float(s.get("scale", SCALE)) / (math.sqrt(3) / 2)
            s["_z"] = float(s.get("zBottom", s.get("z_bottom", i * local_story)))
    for s in sprites:
        if "_z" in s:
            continue
        g = next((g for g in groups if g["key"] == s.get("building")), None)
        if g:
            local_story = 35 * float(s.get("scale", SCALE)) / (math.sqrt(3) / 2)
            s["_z"] = max(a["_z"] for a in g["sprites"]) + local_story


def create_tree(label, x, y, crown=24 / math.sqrt(2)):
    c = world_at(x, y, 0)
    c[2] = 12
    box_mesh(label + "_trunk", 4, 4, 24, center=c,
             material=mat("Tree bark", (0.38, 0.28, 0.16)))
    c[2] = 21 / (math.sqrt(3) / 2)
    box_mesh(label + "_crown", crown, crown, 14 / (math.sqrt(3) / 2), center=c,
             material=mat("Tree green", (0.4, 0.62, 0.17)))


def create_lamp(label, x, y):
    c = world_at(x, y, 0)
    c[2] = 19
    box_mesh(label + "_pole", 2, 2, 38, center=c,
             material=mat("Lamp metal", (0.58, 0.6, 0.58)))
    pole_top = world_at(x, y - 33, 38)
    head = world_at(x + 14, y - 30, 38)
    arm_delta = head - pole_top
    arm = box_mesh(label + "_arm", float(np.linalg.norm(arm_delta)), 2, 2,
                   center=(head + pole_top) / 2,
                   material=mat("Lamp metal", (0.58, 0.6, 0.58)))
    arm.rotation_euler.z = math.atan2(arm_delta[1], arm_delta[0])
    # The mesh was created in world coordinates, so rotate about its midpoint.
    mid = (head + pole_top) / 2
    for vertex in arm.data.vertices:
        vertex.co -= Vector(tuple(mid))
    arm.location = Vector(tuple(mid))
    box_mesh(label + "_head", 5, 4, 2, center=head,
             material=mat("Lamp white", (0.83, 0.83, 0.75)))


def create_roof_terrace():
    polygon_prism("Paved platform beneath terrace and vent",
                  [[616, 191], [720, 243], [720, 268], [668, 294], [616, 267]],
                  28 / (math.sqrt(3) / 2), mat("Terrace paving", (0.78, 0.77, 0.67)))
    wall_h = 21 / (math.sqrt(3) / 2)
    corners = [world_at(x, y, wall_h) for x, y in [(616, 247), (668, 273), (721, 247)]]
    for i, (a, b) in enumerate(zip(corners, corners[1:])):
        center = (a + b) / 2
        center[2] = wall_h / 2
        delta = np.abs(b - a)
        sizes = [max(delta[0], 3.8), max(delta[1], 3.8), wall_h]
        box_mesh(f"Terrace red wall {i + 1}", *sizes, center=center,
                 material=mat("Terrace red", (0.58, 0.22, 0.23)))
        center[2] = wall_h
        box_mesh(f"Terrace cream coping {i + 1}", sizes[0] + 1.5, sizes[1] + 1.5,
                 3.0, center=center, material=mat("Roof parapet", (0.82, 0.81, 0.72)))
    # Low plinth and the small cyan ventilation cube visible above the terrace.
    c = world_at(667, 217, 0)
    plinth_h = 4 / (math.sqrt(3) / 2)
    c[2] = plinth_h / 2
    box_mesh("Vent cream plinth", 50 / math.sqrt(2), 50 / math.sqrt(2), plinth_h,
             center=c, material=mat("Roof parapet", (0.82, 0.81, 0.72)))
    c = world_at(667, 214, plinth_h)
    vent_h = 16 / (math.sqrt(3) / 2)
    c[2] += vent_h / 2
    box_mesh("Cyan rooftop vent", 19 / math.sqrt(2), 19 / math.sqrt(2), vent_h,
             center=c, material=mat("Vent cyan", (0.41, 0.66, 0.71)))


def raster_object(ob):
    deps = bpy.context.evaluated_depsgraph_get()
    evaluated = ob.evaluated_get(deps)
    mesh = evaluated.to_mesh()
    mesh.calc_loop_triangles()
    verts = np.array([tuple(ob.matrix_world @ v.co) for v in mesh.vertices], dtype=np.float64)
    projected = verts @ BASIS.T
    projected[:, :2] += ORIGIN
    front = np.full((H, W), -np.inf, np.float32)
    back = np.full((H, W), np.inf, np.float32)
    normals = np.zeros((H, W, 3), np.float32)
    for triangle in mesh.loop_triangles:
        ids = list(triangle.vertices)
        p = projected[ids]
        xmin, xmax = max(0, int(math.floor(p[:, 0].min()))), min(W - 1, int(math.ceil(p[:, 0].max())))
        ymin, ymax = max(0, int(math.floor(p[:, 1].min()))), min(H - 1, int(math.ceil(p[:, 1].max())))
        if xmin > xmax or ymin > ymax:
            continue
        ax, ay = p[0, :2]
        bx, by = p[1, :2]
        cx, cy = p[2, :2]
        denominator = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
        if abs(denominator) < 1e-8:
            continue
        yy, xx = np.mgrid[ymin:ymax + 1, xmin:xmax + 1]
        xx, yy = xx + 0.5, yy + 0.5
        a = ((by - cy) * (xx - cx) + (cx - bx) * (yy - cy)) / denominator
        b = ((cy - ay) * (xx - cx) + (ax - cx) * (yy - cy)) / denominator
        c = 1 - a - b
        inside = (a >= -1e-7) & (b >= -1e-7) & (c >= -1e-7)
        depth = a * p[0, 2] + b * p[1, 2] + c * p[2, 2]
        f = front[ymin:ymax + 1, xmin:xmax + 1]
        bk = back[ymin:ymax + 1, xmin:xmax + 1]
        nearer = inside & (depth > f)
        f[nearer] = depth[nearer]
        bk[inside] = np.minimum(bk[inside], depth[inside])
        n = np.cross(verts[ids[1]] - verts[ids[0]], verts[ids[2]] - verts[ids[0]])
        length = np.linalg.norm(n)
        if length > 0:
            n = (n / length) @ BASIS.T
            # Source winding in concave ground tessellation can differ.
            if n[2] < 0:
                n *= -1
            normals[ymin:ymax + 1, xmin:xmax + 1][nearer] = n
    evaluated.to_mesh_clear()
    good = np.isfinite(front) & np.isfinite(back)
    back[~good] = -np.inf
    return front, back, normals


def save_png(name, pixels):
    rgba = np.asarray(pixels, np.float32)
    if rgba.shape[-1] == 3:
        rgba = np.concatenate([rgba, np.ones((*rgba.shape[:2], 1), np.float32)], axis=2)
    image = bpy.data.images.new(name, width=W, height=H, alpha=True)
    image.colorspace_settings.name = "Non-Color"
    image.pixels.foreach_set(np.ascontiguousarray(rgba[::-1]).ravel())
    image.filepath_raw = str(OUT / name)
    image.file_format = "PNG"
    image.save()
    bpy.data.images.remove(image)


def export_buffers():
    fronts, backs = [], []
    top_depth = np.full((H, W), -np.inf, np.float32)
    top_normals = np.zeros((H, W, 4), np.float32)
    top_material = np.zeros((H, W, 4), np.float32)
    object_table = []
    for i, ob in enumerate(objects, 1):
        f, b, n = raster_object(ob)
        fronts.append(f)
        backs.append(b)
        closer = f > top_depth
        top_depth[closer] = f[closer]
        top_normals[closer, :3] = n[closer]
        top_normals[closer, 3] = 1
        color = tuple(ob.data.materials[0].diffuse_color[:3])
        top_material[closer, :3] = color
        top_material[closer, 3] = 1
        object_table.append({"id": i, "name": ob.name, "material": ob.data.materials[0].name})
    f = np.stack(fronts)
    b = np.stack(backs)
    del fronts, backs
    order = np.argsort(-f, axis=0, kind="stable")
    f = np.take_along_axis(f, order, axis=0)
    b = np.take_along_axis(b, order, axis=0)
    ids = order + 1
    intervals = np.zeros((LAYERS, H, W, 4), np.float32)
    count = np.zeros((H, W), np.uint8)
    current_f, current_b, current_id = f[0].copy(), b[0].copy(), ids[0].copy()
    iy, ix = np.mgrid[:H, :W]
    for k in range(1, len(objects) + 1):
        next_f = f[k] if k < len(objects) else np.full((H, W), -np.inf)
        next_b = b[k] if k < len(objects) else np.full((H, W), -np.inf)
        next_id = ids[k] if k < len(objects) else np.zeros((H, W), np.int32)
        current_good = np.isfinite(current_f)
        next_good = np.isfinite(next_f)
        overlaps = current_good & next_good & (next_f >= current_b - 0.3)
        current_b[overlaps] = np.minimum(current_b[overlaps], next_b[overlaps])
        flush = current_good & ~overlaps
        store = flush & (count < LAYERS)
        layer = count[store]
        intervals[layer, iy[store], ix[store], 0] = current_f[store]
        intervals[layer, iy[store], ix[store], 1] = current_b[store]
        intervals[layer, iy[store], ix[store], 2] = current_id[store]
        intervals[layer, iy[store], ix[store], 3] = 1
        count[flush] += 1
        replace = ~overlaps
        current_f[replace] = next_f[replace]
        current_b[replace] = next_b[replace]
        current_id[replace] = next_id[replace]
    intervals.astype("<f4").tofile(OUT / "shadow-intervals.f32")
    top_normals.astype("<f4").tofile(OUT / "shadow-normals.f32")
    top_material.astype("<f4").tofile(OUT / "shadow-materials.f32")
    valid = intervals[0, :, :, 3] > 0
    dmin, dmax = float(intervals[0, :, :, 0][valid].min()), float(intervals[0, :, :, 0][valid].max())
    gray = np.zeros((H, W, 4), np.float32)
    gray[:, :, :3] = ((intervals[0, :, :, 0] - dmin) / (dmax - dmin))[:, :, None]
    gray[:, :, 3] = valid
    save_png("depth-front.png", gray)
    gray[:, :, :3] = ((intervals[0, :, :, 1] - dmin) / (dmax - dmin))[:, :, None]
    save_png("depth-back.png", gray)
    thick = np.maximum(intervals[0, :, :, 0] - intervals[0, :, :, 1], 0)
    tmax = float(thick.max())
    gray[:, :, :3] = (thick / tmax)[:, :, None]
    save_png("thickness.png", gray)
    normals_png = top_normals.copy()
    normals_png[:, :, :3] = normals_png[:, :, :3] * 0.5 + 0.5
    save_png("normals.png", normals_png)
    save_png("materials.png", top_material)
    validity = np.repeat(valid[:, :, None].astype(np.float32), 4, axis=2)
    validity[:, :, 3] = 1
    save_png("validity.png", validity)
    # A non-colour-managed diagnostic of exact triangle visibility.
    light = np.array([-0.25, -0.45, 0.86])
    diffuse = np.maximum(np.sum(top_normals[:, :, :3] * light, axis=2), 0)
    preview = top_material.copy()
    preview[:, :, :3] *= (0.4 + 0.6 * diffuse[:, :, None])
    preview[~valid] = [0.26, 0.49, 0.70, 1]
    save_png("geometry-preview.png", preview)
    metadata = {
        "width": W, "height": H, "layers": LAYERS, "floatFormat": "IEEE754 float32 little endian",
        "blenderVersion": bpy.app.version_string,
        "rowOrder": "top-to-bottom", "pixelSample": "pixel center (x+0.5,y+0.5)",
        "intervalFile": "shadow-intervals.f32", "intervalLayout": "layer-major, then row-major RGBA",
        "intervalChannels": ["frontDepthTowardCamera", "backDepthTowardCamera", "objectId", "validity"],
        "normalFile": "shadow-normals.f32", "normalChannels": ["right", "down", "towardCamera", "validity"],
        "materialFile": "shadow-materials.f32", "materialChannels": ["linearR", "linearG", "linearB", "validity"],
        "origin": ORIGIN.tolist(), "right": RIGHT.tolist(), "down": DOWN.tolist(), "toward": TOWARD.tolist(),
        "worldToView": BASIS.tolist(), "worldUnits": "one screen pixel along an orthonormal camera basis",
        "screenToWorld": "(x-origin.x)*right + (y-origin.y)*down + depth*toward",
        "groundDepth": "sqrt(3)*(y-origin.y) for world Z=0",
        "depthRange": [dmin, dmax], "thicknessPreviewMax": tmax,
        "occupiedDepthRange": [float(intervals[:, :, :, 1][intervals[:, :, :, 3] > 0].min()),
                               float(intervals[:, :, :, 0][intervals[:, :, :, 3] > 0].max())],
        "intervalMergeTolerance": 0.3, "overflowPixels": int((count > LAYERS).sum()),
        "validPixels": int(valid.sum()), "objectCount": len(objects), "objects": object_table,
        "limitation": "Closed low-poly geometry approximates sprite silhouettes; four separated occupied intervals retained, no invented volume across air gaps.",
    }
    (OUT / "shadow-buffers.json").write_text(json.dumps(metadata, indent=2))
    (OUT / "bake-metadata.json").write_text(json.dumps(metadata, indent=2))
    print("BUFFERS", json.dumps({k: metadata[k] for k in ("validPixels", "objectCount", "overflowPixels", "depthRange")}))


def main():
    OUT.mkdir(exist_ok=True)
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    make_asset_library()
    layout_path = OUT / "scene-layout.json"
    if not layout_path.exists():
        raise RuntimeError("Scene template matching must create generated/scene-layout.json first")
    layout = json.loads(layout_path.read_text())
    sprites = layout["sprites"]
    assign_story_heights(sprites)
    ground = layout.get("groundPolygon", [
        [408, 112], [720, 268], [772, 294], [720, 320], [668, 294],
        [668, 346], [616, 372], [564, 346], [512, 372], [460, 346],
        [408, 372], [148, 242], [148, 190], [200, 164], [252, 190],
        [304, 164], [356, 138],
    ])
    composed_geometry = OUT / "scenery-geometry.json"
    if composed_geometry.exists():
        ground = json.loads(composed_geometry.read_text())["outline"]
    polygon_prism("Island pavement and foundation", ground, 28 / (math.sqrt(3) / 2),
                  mat("Pavement", (0.69, 0.68, 0.59)))
    for sprite in sprites:
        # The composed scene clips native base-tile artwork and uses one
        # shared terrain slab. Keep those foundations in the reusable library.
        create_sprite_geometry(sprite, sprite.get("_z", 0), include_foundation=False)
    for i, (x, y) in enumerate([(388, 181), (595, 356), (634, 336), (427, 198)]):
        create_tree(f"Street tree {i + 1}", x, y)
    for i, (x, y) in enumerate([(261, 252), (572, 205), (633, 214)]):
        create_lamp(f"Street lamp {i + 1}", x, y)
    create_roof_terrace()
    # Visible detached road ramp in the foreground.
    polygon_prism("Detached road ramp", [[408, 372], [460, 372], [502, 422], [428, 435]], 12,
                  mat("Road ramp", (0.45, 0.45, 0.42)), top_z=0)
    camera_data = bpy.data.cameras.new("Isometric reference camera")
    camera = bpy.data.objects.new("Isometric reference camera", camera_data)
    bpy.context.scene.collection.objects.link(camera)
    camera.location = Vector(tuple(TOWARD * 1600))
    camera.rotation_euler = (-camera.location).to_track_quat("-Z", "Y").to_euler()
    # Pixel coordinates use a Y-down basis, which has mirrored handedness
    # relative to Blender's camera film. Match the source's horizontal axis.
    camera.scale.x = -1
    camera_data.type = "ORTHO"
    camera_data.ortho_scale = W
    camera_data.clip_end = 10000
    bpy.context.scene.camera = camera
    scene = bpy.context.scene
    scene.render.resolution_x, scene.render.resolution_y = W, H
    scene.render.resolution_percentage = 100
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.display.shading.light = "STUDIO"
    scene.display.shading.color_type = "MATERIAL"
    scene.display.shading.show_shadows = False
    scene.display.shading.show_cavity = True
    scene.display.shading.background_type = "WORLD"
    scene.world.color = (0.26, 0.49, 0.7)
    scene["Buffer encoding"] = "See generated/shadow-buffers.json. Float32, top-down rows, positive depth points toward camera."
    scene["Reference sprite scale"] = SCALE
    export_buffers()
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT / "reconstructed-scene.blend"))
    scene.render.filepath = str(OUT / "blender-preview.png")
    bpy.ops.render.render(write_still=True)


if __name__ == "__main__":
    main()
