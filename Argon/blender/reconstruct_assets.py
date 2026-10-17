import bpy
import bmesh
import math
import mathutils
from mathutils import Vector, Matrix, Euler
from mathutils.bvhtree import BVHTree
import numpy as np
import json
import os
import struct
import zlib

# ==============================================================================
# Fast Pure-Python PNG Reader / Writer (Zero External Dependencies in Blender)
# ==============================================================================
def write_png_rgba8(filepath, rgba_uint8):
    """Write an (H, W, 4) uint8 numpy array to a PNG file."""
    h, w, c = rgba_uint8.shape
    assert c == 4
    raw_data = b"".join(b"\x00" + rgba_uint8[y].tobytes() for y in range(h))
    compressed = zlib.compress(raw_data, level=6)

    def make_chunk(chunk_type, data):
        chunk = chunk_type + data
        return struct.pack("!I", len(data)) + chunk + struct.pack("!I", zlib.crc32(chunk) & 0xFFFFFFFF)

    ihdr = struct.pack("!IIBBBBB", w, h, 8, 6, 0, 0, 0)
    png_bytes = (
        b"\x89PNG\r\n\x1a\n"
        + make_chunk(b"IHDR", ihdr)
        + make_chunk(b"IDAT", compressed)
        + make_chunk(b"IEND", b"")
    )
    with open(filepath, "wb") as f:
        f.write(png_bytes)


def read_png_rgba8(filepath):
    """Read a PNG file into an (H, W, 4) uint8 numpy array using Blender's image loader."""
    img = bpy.data.images.load(os.path.abspath(filepath), check_existing=False)
    w, h = img.size
    pixels = np.empty(w * h * 4, dtype=np.float32)
    img.pixels.foreach_get(pixels)
    bpy.data.images.remove(img)
    pixels = pixels.reshape((h, w, 4))
    # Flip vertically (Blender images are bottom-to-top)
    pixels = pixels[::-1, :, :]
    return np.clip(np.round(pixels * 255.0), 0, 255).astype(np.uint8)


# ==============================================================================
# Calibrated Isometric Camera & Coordinate Constants
# ==============================================================================
# Euler XYZ = (60 deg, 0 deg, 45 deg)
CAM_EULER = Euler((math.radians(60.0), 0.0, math.radians(45.0)), 'XYZ')
CAM_MAT = CAM_EULER.to_matrix()
R_CAM = CAM_MAT @ Vector((1.0, 0.0, 0.0))  # (+0.707107, +0.707107, 0.0)
U_CAM = CAM_MAT @ Vector((0.0, 1.0, 0.0))  # (-0.353553, +0.353553, +0.866025)
F_CAM = CAM_MAT @ Vector((0.0, 0.0, 1.0))  # (+0.612372, -0.612372, +0.500000)

# In asset space, 1.0 world unit (ground block side length) projects to 130.0 px horizontally:
ASSET_PX_PER_DIAG = 130.0
ASSET_S_PX = ASSET_PX_PER_DIAG / math.sqrt(2.0)  # 91.92388 px per world unit in asset space

# In sample.png space, 1.0 world unit projects to 104.0 px horizontally (dx=52, dy=26):
SAMPLE_PX_PER_DIAG = 104.0
SAMPLE_S_PX = SAMPLE_PX_PER_DIAG / math.sqrt(2.0)  # 73.539105 px per world unit in sample.png space

# World Z heights (where 1.0 unit = ground block width):
# In asset space, vertical Z projects to dy_px = Z * ASSET_S_PX * sin(60 deg) = Z * 79.6084
Z_PER_ASSET_YPX = 1.0 / (ASSET_S_PX * math.sin(math.radians(60.0)))  # 0.0125615 world units per vertical asset px
H_SIDEWALK = 19.5 * Z_PER_ASSET_YPX   # 0.24495 world units
H_DIRT     = 14.5 * Z_PER_ASSET_YPX   # 0.18214 world units
H_FLOOR    = 34.6 * Z_PER_ASSET_YPX   # 0.43463 world units (27.68 px in sample.png)
H_CURB     = 3.5  * Z_PER_ASSET_YPX   # 0.04397 world units (recessed road depth)
H_RIM      = 4.2  * Z_PER_ASSET_YPX   # 0.05276 world units (flat roof parapet rim)


# ==============================================================================
# BMesh 3D Geometry Builders (Constructing Closed Manifold Components)
# ==============================================================================
def add_box(bm, x0, x1, y0, y1, z0, z1):
    """Add an axis-aligned 3D box [x0,x1] x [y0,y1] x [z0,z1] to a BMesh."""
    verts = [
        bm.verts.new((x0, y0, z0)),
        bm.verts.new((x1, y0, z0)),
        bm.verts.new((x1, y1, z0)),
        bm.verts.new((x0, y1, z0)),
        bm.verts.new((x0, y0, z1)),
        bm.verts.new((x1, y0, z1)),
        bm.verts.new((x1, y1, z1)),
        bm.verts.new((x0, y1, z1)),
    ]
    faces = [
        (0, 3, 2, 1),  # -Z bottom
        (4, 5, 6, 7),  # +Z top
        (0, 1, 5, 4),  # -Y front-left
        (2, 3, 7, 6),  # +Y back-right
        (0, 4, 7, 3),  # -X back-left
        (1, 2, 6, 5),  # +X front-right
    ]
    for f in faces:
        bm.faces.new([verts[i] for i in f])


def add_pitched_gable_x(bm, hw, z0, z_peak):
    """Add a pitched roof with ridge running along Y_w (sloping toward -X_w and +X_w) or along X_w."""
    # Ridge along X_w (from -hw to +hw at y=0, z=z_peak; eaves at y=-hw and y=+hw, z=z0)
    v = [
        bm.verts.new((-hw, -hw, z0)),
        bm.verts.new((+hw, -hw, z0)),
        bm.verts.new((+hw, +hw, z0)),
        bm.verts.new((-hw, +hw, z0)),
        bm.verts.new((-hw, 0.0, z_peak)),
        bm.verts.new((+hw, 0.0, z_peak)),
    ]
    bm.faces.new([v[0], v[3], v[2], v[1]])  # bottom
    bm.faces.new([v[0], v[1], v[5], v[4]])  # -Y slope (front-left)
    bm.faces.new([v[2], v[3], v[4], v[5]])  # +Y slope (back-right)
    bm.faces.new([v[0], v[4], v[3]])        # -X triangle
    bm.faces.new([v[1], v[2], v[5]])        # +X triangle


def add_pitched_gable_y(bm, hw, z0, z_peak):
    """Ridge along Y_w (from y=-hw to +hw at x=0, z=z_peak; eaves at x=-hw and x=+hw, z=z0)."""
    v = [
        bm.verts.new((-hw, -hw, z0)),
        bm.verts.new((+hw, -hw, z0)),
        bm.verts.new((+hw, +hw, z0)),
        bm.verts.new((-hw, +hw, z0)),
        bm.verts.new((0.0, -hw, z_peak)),
        bm.verts.new((0.0, +hw, z_peak)),
    ]
    bm.faces.new([v[0], v[3], v[2], v[1]])  # bottom
    bm.faces.new([v[1], v[2], v[5], v[4]])  # +X slope (front-right)
    bm.faces.new([v[3], v[0], v[4], v[5]])  # -X slope (back-left)
    bm.faces.new([v[0], v[1], v[4]])        # -Y triangle
    bm.faces.new([v[2], v[3], v[5]])        # +Y triangle


def add_barrel_vault(bm, hw, z0, z_peak, axis='x', segs=12):
    """Add a curved barrel-vault roof along X_w or Y_w."""
    ring_neg = []
    ring_pos = []
    for i in range(segs + 1):
        t = -1.0 + 2.0 * (i / segs)  # [-1, 1]
        u = t * hw
        z = z0 + (z_peak - z0) * math.sqrt(max(0.0, 1.0 - t * t))
        if axis == 'x':
            ring_neg.append(bm.verts.new((-hw, u, z)))
            ring_pos.append(bm.verts.new((+hw, u, z)))
        else:
            ring_neg.append(bm.verts.new((u, -hw, z)))
            ring_pos.append(bm.verts.new((u, +hw, z)))
    for i in range(segs):
        if axis == 'x':
            bm.faces.new([ring_neg[i], ring_pos[i], ring_pos[i+1], ring_neg[i+1]])
        else:
            bm.faces.new([ring_neg[i+1], ring_pos[i+1], ring_pos[i], ring_neg[i]])
    # End caps & bottom
    bm.faces.new(ring_neg[::-1] if axis == 'x' else ring_neg)
    bm.faces.new(ring_pos if axis == 'x' else ring_pos[::-1])
    bm.faces.new([ring_neg[0], ring_neg[-1], ring_pos[-1], ring_pos[0]] if axis == 'x' else [ring_neg[0], ring_pos[0], ring_pos[-1], ring_neg[-1]])


def finalize_bvh(bm):
    """Recalculate normals outward, triangulate, and return BVHTree."""
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bmesh.ops.triangulate(bm, faces=bm.faces)
    return BVHTree.FromBMesh(bm)


# ==============================================================================
# Build Component Meshes for a Building Tile (000..128)
# ==============================================================================
def build_building_tile_components(spec):
    """
    Returns a list of (comp_name, bm_front, bm_back) for a buildingTile.
    Why separate bm_front and bm_back?
    - bm_front has the exact visible 3D geometry of this sprite layer.
    - bm_back has the full vertical shaft extension for building/roof pieces so that
      floor-to-floor seams have continuous 3D building thickness without pinching to 0!
    - Overhanging components (awnings) have their own closed bm_front == bm_back so
      rays can pass cleanly underneath the awning!
    """
    cat = spec['category']
    r_type = spec['roof_type']
    tid = spec['id']
    hw = 0.375  # Building half-width (0.75 total width)
    comps = []

    if cat == 'antenna':
        bm = bmesh.new()
        add_box(bm, -0.025, 0.025, -0.025, 0.025, 0.0, 0.28)
        add_box(bm, -0.06, 0.06, -0.015, 0.015, 0.22, 0.25)
        bvh = finalize_bvh(bm)
        comps.append(('antenna', bm, bvh, bvh))
        return comps

    if cat == 'base':
        # 1. Ground slab (sidewalk + dirt): [-0.5, 0.5]^2 x [-(H_SIDEWALK+H_DIRT), 0.0]
        bm_g = bmesh.new()
        add_box(bm_g, -0.5, 0.5, -0.5, 0.5, -(H_SIDEWALK + H_DIRT), 0.0)
        bvh_g = finalize_bvh(bm_g)
        comps.append(('ground', bm_g, bvh_g, bvh_g))

        # 2. 1st floor building body: [-0.375, 0.375]^2 x [0.0, H_FLOOR]
        bm_b_front = bmesh.new()
        bm_b_back = bmesh.new()
        z_top = H_FLOOR + (H_RIM if spec['height'] >= 129 else 0.0)
        add_box(bm_b_front, -hw, hw, -hw, hw, 0.0, z_top)
        # Top cornice & base plinth details
        add_box(bm_b_front, -hw - 0.01, hw + 0.01, -hw - 0.01, hw + 0.01, z_top - 0.035, z_top)
        if spec['has_left_steps']:
            add_box(bm_b_front, -0.09, 0.09, -hw - 0.055, -hw, 0.0, 0.055)
        if spec['has_right_steps']:
            add_box(bm_b_front, hw, hw + 0.055, -0.09, 0.09, 0.0, 0.055)

        # Back shaft extends down into ground and up so stacked floors have continuous thickness
        add_box(bm_b_back, -hw, hw, -hw, hw, -(H_SIDEWALK + H_DIRT), z_top + H_FLOOR)
        bvh_bf = finalize_bvh(bm_b_front)
        bvh_bb = finalize_bvh(bm_b_back)
        comps.append(('building', bm_b_front, bvh_bf, bvh_bb))

        # 3. Overhanging Storefront Awnings (separate component so light passes underneath!)
        if spec['has_left_awning']:
            bm_aw = bmesh.new()
            add_box(bm_aw, -0.33, 0.33, -hw - 0.085, -hw, 0.55 * H_FLOOR, 0.78 * H_FLOOR)
            bvh_aw = finalize_bvh(bm_aw)
            comps.append(('awning_left', bm_aw, bvh_aw, bvh_aw))
        if spec['has_right_awning']:
            bm_aw = bmesh.new()
            add_box(bm_aw, hw, hw + 0.085, -0.33, 0.33, 0.55 * H_FLOOR, 0.78 * H_FLOOR)
            bvh_aw = finalize_bvh(bm_aw)
            comps.append(('awning_right', bm_aw, bvh_aw, bvh_aw))
        return comps

    if cat == 'middle':
        bm_f = bmesh.new()
        bm_b = bmesh.new()
        add_box(bm_f, -hw, hw, -hw, hw, 0.0, H_FLOOR)
        add_box(bm_f, -hw - 0.01, hw + 0.01, -hw - 0.01, hw + 0.01, H_FLOOR - 0.03, H_FLOOR)
        # Continuous building shaft for back-face thickness
        add_box(bm_b, -hw, hw, -hw, hw, -2.5 * H_FLOOR, 2.0 * H_FLOOR)
        bvh_f = finalize_bvh(bm_f)
        bvh_b = finalize_bvh(bm_b)
        comps.append(('middle_floor', bm_f, bvh_f, bvh_b))
        return comps

    if cat == 'roof':
        bm_f = bmesh.new()
        bm_b = bmesh.new()
        # Base roof deck with 4-sided rim
        rim_t = 0.045
        add_box(bm_f, -hw, hw, -hw, hw, 0.0, H_RIM * 0.45)
        add_box(bm_f, -hw, hw, -hw, -hw + rim_t, 0.0, H_RIM)
        add_box(bm_f, -hw, hw, hw - rim_t, hw, 0.0, H_RIM)
        add_box(bm_f, -hw, -hw + rim_t, -hw, hw, 0.0, H_RIM)
        add_box(bm_f, hw - rim_t, hw, -hw, hw, 0.0, H_RIM)

        if r_type == 'flat_ac':
            # Two rooftop AC / HVAC units
            if spec['id'] in (117, 127):
                add_box(bm_f, -0.28, -0.14, -0.04, +0.10, H_RIM * 0.45, H_RIM * 1.35)
                add_box(bm_f, -0.28, -0.14, +0.13, +0.27, H_RIM * 0.45, H_RIM * 1.35)
            else:
                add_box(bm_f, -0.04, +0.10, -0.28, -0.14, H_RIM * 0.45, H_RIM * 1.35)
                add_box(bm_f, +0.13, +0.27, -0.28, -0.14, H_RIM * 0.45, H_RIM * 1.35)
        elif r_type == 'flat_tier':
            add_box(bm_f, -0.24, 0.24, -0.24, 0.24, H_RIM * 0.45, H_RIM * 1.45)
        elif r_type == 'flat_high_rim':
            add_box(bm_f, -hw, hw, -hw, -hw + rim_t, 0.0, H_RIM * 2.4)
            add_box(bm_f, -hw, -hw + rim_t, -hw, hw, 0.0, H_RIM * 2.4)
        elif r_type == 'gable_parapet_ny':  # #102 (peaked parapet on front-left -Y_w)
            v = [
                bm_f.verts.new((-hw, -hw, H_RIM)),
                bm_f.verts.new((+hw, -hw, H_RIM)),
                bm_f.verts.new((+hw, -hw + rim_t, H_RIM)),
                bm_f.verts.new((-hw, -hw + rim_t, H_RIM)),
                bm_f.verts.new((0.0, -hw, H_RIM * 2.5)),
                bm_f.verts.new((0.0, -hw + rim_t, H_RIM * 2.5)),
            ]
            bm_f.faces.new([v[0], v[1], v[4]])
            bm_f.faces.new([v[2], v[3], v[5]])
            bm_f.faces.new([v[0], v[4], v[5], v[3]])
            bm_f.faces.new([v[1], v[2], v[5], v[4]])
        elif r_type == 'gable_parapet_px':  # #110 (peaked parapet on front-right +X_w)
            v = [
                bm_f.verts.new((hw, -hw, H_RIM)),
                bm_f.verts.new((hw, +hw, H_RIM)),
                bm_f.verts.new((hw - rim_t, +hw, H_RIM)),
                bm_f.verts.new((hw - rim_t, -hw, H_RIM)),
                bm_f.verts.new((hw, 0.0, H_RIM * 2.5)),
                bm_f.verts.new((hw - rim_t, 0.0, H_RIM * 2.5)),
            ]
            bm_f.faces.new([v[0], v[1], v[4]])
            bm_f.faces.new([v[2], v[3], v[5]])
            bm_f.faces.new([v[0], v[4], v[5], v[3]])
            bm_f.faces.new([v[1], v[2], v[5], v[4]])
        elif r_type == 'gable_parapet_nx':  # #095
            add_pitched_gable_x(bm_f, hw, H_RIM * 0.45, H_RIM * 2.4)
        elif r_type == 'gable_parapet_py':  # #103
            add_pitched_gable_y(bm_f, hw, H_RIM * 0.45, H_RIM * 2.4)
        elif r_type == 'pitched_x':  # e.g. #088 (B6 green shop roof, ridge along X_w)
            add_pitched_gable_x(bm_f, hw, H_RIM * 0.5, H_RIM * 3.1)
        elif r_type == 'pitched_y':  # ridge along Y_w
            add_pitched_gable_y(bm_f, hw, H_RIM * 0.5, H_RIM * 3.1)
        elif r_type == 'vault_x':
            add_barrel_vault(bm_f, hw, H_RIM * 0.5, H_RIM * 3.3, axis='x')
        elif r_type == 'vault_y':
            add_barrel_vault(bm_f, hw, H_RIM * 0.5, H_RIM * 3.3, axis='y')

        # Back shaft for roof includes the roof geometry + downward building shaft
        bm_b = bm_f.copy()
        add_box(bm_b, -hw, hw, -hw, hw, -2.5 * H_FLOOR, H_RIM * 0.45)
        bvh_f = finalize_bvh(bm_f)
        bvh_b = finalize_bvh(bm_b)
        comps.append(('roof', bm_f, bvh_f, bvh_b))
        return comps


# ==============================================================================
# Raycasting a Tile's Components to Depth, Thickness, and Normal Arrays
# ==============================================================================
def raycast_tile_maps(comps, w, h, cx_px, cy_px, ref_alpha=None):
    """
    Raycast the 3D BMesh components from the calibrated orthographic isometric camera.
    Returns:
      z_front_px: (H, W) float32 in sample.png pixel units
      thickness_px: (H, W) float32 in sample.png pixel units
      normal_view: (H, W, 3) float32 unit normal in camera view space
      hit_mask: (H, W) bool
    """
    z_front = np.zeros((h, w), dtype=np.float32)
    thickness = np.zeros((h, w), dtype=np.float32)
    normal_v = np.zeros((h, w, 3), dtype=np.float32)
    normal_v[:, :, 1] = 0.866025
    normal_v[:, :, 2] = 0.500000
    hit_mask = np.zeros((h, w), dtype=bool)

    inv_s = 1.0 / ASSET_S_PX
    ray_dir_front = -F_CAM
    ray_dir_back = F_CAM

    for py in range(h):
        y_v = (cy_px - (py + 0.5)) * inv_s
        u_vec = y_v * U_CAM
        for px in range(w):
            x_v = ((px + 0.5) - cx_px) * inv_s
            base_pt = x_v * R_CAM + u_vec
            orig_front = base_pt + 10.0 * F_CAM

            best_z = -1e9
            best_n = None
            best_bvh_back = None

            for (cname, _bm, bvh_f, bvh_b) in comps:
                loc, norm, _idx, _dist = bvh_f.ray_cast(orig_front, ray_dir_front, 25.0)
                if loc is not None:
                    zf = loc.dot(F_CAM)
                    if zf > best_z:
                        best_z = zf
                        best_n = norm
                        best_bvh_back = bvh_b

            if best_n is not None:
                hit_mask[py, px] = True
                zf_px = best_z * SAMPLE_S_PX
                z_front[py, px] = zf_px

                # Cast backward ray against the winning component's back BVHTree
                orig_back = base_pt - 10.0 * F_CAM
                loc_b, _nb, _ib, _db = best_bvh_back.ray_cast(orig_back, ray_dir_back, 25.0)
                if loc_b is not None:
                    zb_px = loc_b.dot(F_CAM) * SAMPLE_S_PX
                    t_px = max(2.0, zf_px - zb_px)
                else:
                    t_px = 6.0
                thickness[py, px] = t_px

                # Transform world normal to camera view space (R_CAM, U_CAM, F_CAM)
                nx = best_n.dot(R_CAM)
                ny = best_n.dot(U_CAM)
                nz = best_n.dot(F_CAM)
                length = math.sqrt(nx*nx + ny*ny + nz*nz)
                if length > 1e-6:
                    normal_v[py, px, 0] = nx / length
                    normal_v[py, px, 1] = ny / length
                    normal_v[py, px, 2] = nz / length

    # Dilate valid 3D values by 4 iterations into any neighboring pixels so anti-aliased
    # sprite borders have 100% valid 3D depth, thickness, and normals without edge halos!
    for _ in range(4):
        missing = ~hit_mask
        if not np.any(missing):
            break
        for dy, dx in [(-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (-1, 1), (1, -1), (1, 1)]:
            shifted_mask = np.zeros_like(hit_mask)
            sy0, sy1 = max(0, dy), h + min(0, dy)
            sx0, sx1 = max(0, dx), w + min(0, dx)
            dy0, dy1 = max(0, -dy), h - max(0, dy)
            dx0, dx1 = max(0, -dx), w - max(0, dx)
            shifted_mask[dy0:dy1, dx0:dx1] = hit_mask[sy0:sy1, sx0:sx1]
            fill = missing & shifted_mask
            if np.any(fill):
                z_front_src = np.zeros_like(z_front)
                t_src = np.zeros_like(thickness)
                n_src = np.zeros_like(normal_v)
                z_front_src[dy0:dy1, dx0:dx1] = z_front[sy0:sy1, sx0:sx1]
                t_src[dy0:dy1, dx0:dx1] = thickness[sy0:sy1, sx0:sx1]
                n_src[dy0:dy1, dx0:dx1] = normal_v[sy0:sy1, sx0:sx1]
                z_front[fill] = z_front_src[fill]
                thickness[fill] = t_src[fill]
                normal_v[fill] = n_src[fill]
                hit_mask[fill] = True
                missing = ~hit_mask

    return z_front, thickness, normal_v


def save_encoded_maps(name, z_front, thickness, normal_v, alpha_uint8):
    """
    Save depth, thickness, and normal maps to generated/{depth,thickness,normal}/{name}.png.
    Encoding:
    - Depth: z_front in [-128, +128] px mapped to uint16 [0, 65535]:
      R = high byte (visually a clean grayscale depth map!), G = low byte, B = high byte, A = alpha.
    - Thickness: thickness in [0, 128] px mapped to uint16 [0, 65535]:
      R = high byte (visually a clean grayscale thickness map!), G = low byte, B = high byte, A = alpha.
    - Normal: view-space unit normal [-1, +1] mapped to uint8 [0, 255] in RGB, A = alpha.
    """
    h, w = z_front.shape
    mask = alpha_uint8 > 0

    # Depth encoding: range [-128.0, +128.0] px -> [0, 65535]
    z_norm = np.clip((z_front + 128.0) / 256.0, 0.0, 1.0)
    z_u16 = np.round(z_norm * 65535.0).astype(np.uint16)
    z_hi = ((z_u16 >> 8) & 0xFF).astype(np.uint8)
    z_lo = (z_u16 & 0xFF).astype(np.uint8)
    depth_rgba = np.zeros((h, w, 4), dtype=np.uint8)
    depth_rgba[:, :, 0] = np.where(mask, z_hi, 0)
    depth_rgba[:, :, 1] = np.where(mask, z_lo, 0)
    depth_rgba[:, :, 2] = np.where(mask, z_hi, 0)
    depth_rgba[:, :, 3] = alpha_uint8
    write_png_rgba8(f"generated/depth/{name}.png", depth_rgba)

    # Thickness encoding: range [0.0, 128.0] px -> [0, 65535]
    t_norm = np.clip(thickness / 128.0, 0.0, 1.0)
    t_u16 = np.round(t_norm * 65535.0).astype(np.uint16)
    t_hi = ((t_u16 >> 8) & 0xFF).astype(np.uint8)
    t_lo = (t_u16 & 0xFF).astype(np.uint8)
    thick_rgba = np.zeros((h, w, 4), dtype=np.uint8)
    thick_rgba[:, :, 0] = np.where(mask, t_hi, 0)
    thick_rgba[:, :, 1] = np.where(mask, t_lo, 0)
    thick_rgba[:, :, 2] = np.where(mask, t_hi, 0)
    thick_rgba[:, :, 3] = alpha_uint8
    write_png_rgba8(f"generated/thickness/{name}.png", thick_rgba)

    # Normal encoding: [-1, 1] -> [0, 255]
    n_u8 = np.clip(np.round((normal_v * 0.5 + 0.5) * 255.0), 0, 255).astype(np.uint8)
    norm_rgba = np.zeros((h, w, 4), dtype=np.uint8)
    norm_rgba[:, :, :3] = np.where(mask[:, :, None], n_u8, 0)
    norm_rgba[:, :, 3] = alpha_uint8
    write_png_rgba8(f"generated/normal/{name}.png", norm_rgba)


# ==============================================================================
# Build & Render Non-Building Scene Tiles (Roads, Plaza, Fountain, Red Wall, Props)
# ==============================================================================
def build_scene_tile_meshes_and_maps():
    """
    Constructs the 3D meshes in Blender for all road, plaza, fountain, wall, tree,
    and street lamp tiles in sample.png, raycasts their exact 3D Depth, Thickness,
    Normal, and 4x-supersampled Albedo sprites, and saves them.
    """
    # Standard ground tile dimensions in asset space: 132 x 127, origin at (66.0, 59.0)
    W, H = 132, 127
    CX, CY = 66.0, 59.0

    scene_tile_Types = [
        'scene_plaza',
        'scene_road_u',
        'scene_road_v',
        'scene_road_end_u',
        'scene_road_curve',
        'scene_road_crosswalk_u',
        'scene_road_t_u_v',
        'scene_road_t_v_u',
        'scene_road_t_u_negv',
        'scene_road_roundabout',
        'scene_road_cross',
        'scene_road_lamps_v',
        'scene_road_end_v_lamps',
        'scene_road_trees_v',
        'scene_road_trees_u',
        'scene_plaza_fountain',
        'scene_plaza_red_wall_44',
        'scene_plaza_red_wall_54',
        'scene_road_detached',
    ]

    # Material palette matching sample.png
    PALETTE = {
        'sidewalk': (
            np.array([210, 205, 186], dtype=np.float32),  # top (+Z)
            np.array([190, 185, 168], dtype=np.float32),  # left (-Y)
            np.array([150, 146, 132], dtype=np.float32),  # right (+X)
        ),
        'dirt': (
            np.array([167, 126, 83], dtype=np.float32),
            np.array([167, 126, 83], dtype=np.float32),
            np.array([130, 96, 63], dtype=np.float32),
        ),
        'asphalt': (
            np.array([97, 97, 97], dtype=np.float32),
            np.array([86, 86, 86], dtype=np.float32),
            np.array([72, 72, 72], dtype=np.float32),
        ),
        'stripe': (
            np.array([242, 242, 240], dtype=np.float32),
            np.array([210, 210, 208], dtype=np.float32),
            np.array([180, 180, 178], dtype=np.float32),
        ),
        'tree_trunk': (
            np.array([138, 102, 66], dtype=np.float32),
            np.array([138, 102, 66], dtype=np.float32),
            np.array([104, 76, 48], dtype=np.float32),
        ),
        'tree_crown': (
            np.array([139, 182, 76], dtype=np.float32),
            np.array([123, 161, 64], dtype=np.float32),
            np.array([93, 124, 47], dtype=np.float32),
        ),
        'lamp': (
            np.array([205, 208, 212], dtype=np.float32),
            np.array([175, 178, 182], dtype=np.float32),
            np.array([135, 138, 142], dtype=np.float32),
        ),
        'water': (
            np.array([155, 210, 223], dtype=np.float32),
            np.array([124, 178, 195], dtype=np.float32),
            np.array([101, 148, 165], dtype=np.float32),
        ),
        'red_wall': (
            np.array([210, 205, 186], dtype=np.float32),
            np.array([162, 76, 76], dtype=np.float32),
            np.array([131, 59, 59], dtype=np.float32),
        ),
    }

    def is_road_xy(tname, x, y):
        rw = 0.235
        if tname == 'scene_plaza' or tname.startswith('scene_plaza_'):
            return False
        if tname in ('scene_road_u', 'scene_road_crosswalk_u', 'scene_road_trees_u', 'scene_road_detached'):
            return abs(y) <= rw
        if tname in ('scene_road_v', 'scene_road_lamps_v', 'scene_road_trees_v'):
            return abs(x) <= rw
        if tname == 'scene_road_end_v_lamps':
            return abs(x) <= rw and y <= rw
        if tname == 'scene_road_end_u':
            return abs(y) <= rw and x >= -rw
        if tname == 'scene_road_curve':
            r = math.sqrt((x - 0.5)**2 + (y - 0.5)**2)
            return (0.5 - rw) <= r <= (0.5 + rw)
        if tname == 'scene_road_t_u_v':
            return (abs(y) <= rw) or (abs(x) <= rw and y >= -rw)
        if tname == 'scene_road_t_v_u':
            return (abs(x) <= rw) or (abs(y) <= rw and x >= -rw)
        if tname == 'scene_road_t_u_negv':
            return (abs(y) <= rw) or (abs(x) <= rw and y <= rw)
        if tname == 'scene_road_cross':
            return (abs(x) <= rw) or (abs(y) <= rw)
        if tname == 'scene_road_roundabout':
            # 4-way intersection with central circular island at (0, 0)
            in_road = (abs(x) <= rw) or (abs(y) <= rw)
            dist_island = math.sqrt(x * x + y * y)
            if dist_island < 0.145:
                return False
            if dist_island <= 0.36:
                return True
            return in_road
        return False

    for tname in scene_tile_Types:
        w_cur, h_cur = (148, 144) if tname == 'scene_road_detached' else (W, H)
        cx_cur, cy_cur = (74.0, 67.0) if tname == 'scene_road_detached' else (CX, CY)
        rot_angle = math.radians(-33.5) if tname == 'scene_road_detached' else 0.0
        cos_a, sin_a = math.cos(rot_angle), math.sin(rot_angle)

        # Build 3D BMesh components for this scene tile without internal vertical walls!
        comps = []
        bm_ground = bmesh.new()
        hg = 0.500 if tname == 'scene_road_detached' else 0.508
        if tname == 'scene_plaza' or tname.startswith('scene_plaza_'):
            add_box(bm_ground, -hg, hg, -hg, hg, -(H_SIDEWALK + H_DIRT), 0.0)
        elif tname in ('scene_road_u', 'scene_road_crosswalk_u', 'scene_road_trees_u', 'scene_road_detached'):
            add_box(bm_ground, -hg, hg, -hg, hg, -(H_SIDEWALK + H_DIRT), -H_CURB)
            add_box(bm_ground, -hg, hg, -hg, -0.235, -H_CURB, 0.0)
            add_box(bm_ground, -hg, hg, +0.235, hg, -H_CURB, 0.0)
        elif tname in ('scene_road_v', 'scene_road_lamps_v', 'scene_road_trees_v'):
            add_box(bm_ground, -hg, hg, -hg, hg, -(H_SIDEWALK + H_DIRT), -H_CURB)
            add_box(bm_ground, -hg, -0.235, -hg, hg, -H_CURB, 0.0)
            add_box(bm_ground, +0.235, hg, -hg, hg, -H_CURB, 0.0)
        elif tname == 'scene_road_end_v_lamps':
            add_box(bm_ground, -hg, hg, -hg, hg, -(H_SIDEWALK + H_DIRT), -H_CURB)
            add_box(bm_ground, -hg, -0.235, -hg, hg, -H_CURB, 0.0)
            add_box(bm_ground, +0.235, hg, -hg, hg, -H_CURB, 0.0)
            add_box(bm_ground, -0.235, +0.235, +0.235, hg, -H_CURB, 0.0)
        elif tname == 'scene_road_end_u':
            add_box(bm_ground, -hg, hg, -hg, hg, -(H_SIDEWALK + H_DIRT), -H_CURB)
            add_box(bm_ground, -hg, hg, -hg, -0.235, -H_CURB, 0.0)
            add_box(bm_ground, -hg, hg, +0.235, hg, -H_CURB, 0.0)
            add_box(bm_ground, -hg, -0.235, -0.235, +0.235, -H_CURB, 0.0)
        elif tname == 'scene_road_t_u_v':
            add_box(bm_ground, -hg, hg, -hg, hg, -(H_SIDEWALK + H_DIRT), -H_CURB)
            add_box(bm_ground, -hg, hg, -hg, -0.235, -H_CURB, 0.0)
            add_box(bm_ground, -hg, -0.235, +0.235, hg, -H_CURB, 0.0)
            add_box(bm_ground, +0.235, hg, +0.235, hg, -H_CURB, 0.0)
        elif tname == 'scene_road_t_v_u':
            add_box(bm_ground, -hg, hg, -hg, hg, -(H_SIDEWALK + H_DIRT), -H_CURB)
            add_box(bm_ground, -hg, -0.235, -hg, hg, -H_CURB, 0.0)
            add_box(bm_ground, +0.235, hg, -hg, -0.235, -H_CURB, 0.0)
            add_box(bm_ground, +0.235, hg, +0.235, hg, -H_CURB, 0.0)
        elif tname == 'scene_road_t_u_negv':
            add_box(bm_ground, -hg, hg, -hg, hg, -(H_SIDEWALK + H_DIRT), -H_CURB)
            add_box(bm_ground, -hg, hg, +0.235, hg, -H_CURB, 0.0)
            add_box(bm_ground, -hg, -0.235, -hg, -0.235, -H_CURB, 0.0)
            add_box(bm_ground, +0.235, hg, -hg, -0.235, -H_CURB, 0.0)
        elif tname == 'scene_road_cross':
            add_box(bm_ground, -hg, hg, -hg, hg, -(H_SIDEWALK + H_DIRT), -H_CURB)
            add_box(bm_ground, -hg, -0.235, -hg, -0.235, -H_CURB, 0.0)
            add_box(bm_ground, +0.235, hg, -hg, -0.235, -H_CURB, 0.0)
            add_box(bm_ground, -hg, -0.235, +0.235, hg, -H_CURB, 0.0)
            add_box(bm_ground, +0.235, hg, +0.235, hg, -H_CURB, 0.0)
        else:
            add_box(bm_ground, -hg, hg, -hg, hg, -(H_SIDEWALK + H_DIRT), -H_CURB)
            grid_n = 64
            step = (2.0 * hg) / grid_n
            road_grid = [[is_road_xy(tname, -hg + (i + 0.5) * step, -hg + (j + 0.5) * step) for j in range(grid_n)] for i in range(grid_n)]
            for i in range(grid_n):
                for j in range(grid_n):
                    if not road_grid[i][j]:
                        x0, x1 = -hg + i * step, -hg + (i + 1) * step
                        y0, y1 = -hg + j * step, -hg + (j + 1) * step
                        v4 = bm_ground.verts.new((x0, y0, 0.0))
                        v5 = bm_ground.verts.new((x1, y0, 0.0))
                        v6 = bm_ground.verts.new((x1, y1, 0.0))
                        v7 = bm_ground.verts.new((x0, y1, 0.0))
                        bm_ground.faces.new([v4, v5, v6, v7])
                        if j == 0 or road_grid[i][j - 1]:
                            b0, b1 = bm_ground.verts.new((x0, y0, -H_CURB)), bm_ground.verts.new((x1, y0, -H_CURB))
                            bm_ground.faces.new([b0, b1, v5, v4])
                        if j == grid_n - 1 or road_grid[i][j + 1]:
                            b2, b3 = bm_ground.verts.new((x1, y1, -H_CURB)), bm_ground.verts.new((x0, y1, -H_CURB))
                            bm_ground.faces.new([b2, b3, v7, v6])
                        if i == 0 or road_grid[i - 1][j]:
                            b0, b3 = bm_ground.verts.new((x0, y0, -H_CURB)), bm_ground.verts.new((x0, y1, -H_CURB))
                            bm_ground.faces.new([b0, v4, v7, b3])
                        if i == grid_n - 1 or road_grid[i + 1][j]:
                            b1, b2 = bm_ground.verts.new((x1, y0, -H_CURB)), bm_ground.verts.new((x1, y1, -H_CURB))
                            bm_ground.faces.new([b1, b2, v6, v5])
        if rot_angle != 0.0:
            bmesh.ops.rotate(bm_ground, verts=bm_ground.verts, cent=(0, 0, 0), matrix=Matrix.Rotation(rot_angle, 3, 'Z'))
        bvh_g = finalize_bvh(bm_ground)
        comps.append(('ground', bm_ground, bvh_g, bvh_g, 'ground'))

        # Add props (Trees, Lamps, Fountain, Red Wall) as separate 3D components!
        if tname in ('scene_road_trees_u', 'scene_road_trees_v'):
            positions = [(0.0, -0.365), (0.0, +0.365)] if tname == 'scene_road_trees_u' else [(-0.365, 0.0), (+0.365, 0.0)]
            for idx_t, (tx, ty) in enumerate(positions):
                bm_tr = bmesh.new()
                add_box(bm_tr, tx - 0.038, tx + 0.038, ty - 0.038, ty + 0.038, 0.0, 0.165)
                bvh_tr = finalize_bvh(bm_tr)
                comps.append((f'trunk_{idx_t}', bm_tr, bvh_tr, bvh_tr, 'tree_trunk'))

                bm_cr = bmesh.new()
                add_box(bm_cr, tx - 0.125, tx + 0.125, ty - 0.125, ty + 0.125, 0.155, 0.435)
                bvh_cr = finalize_bvh(bm_cr)
                comps.append((f'crown_{idx_t}', bm_cr, bvh_cr, bvh_cr, 'tree_crown'))

        if tname in ('scene_road_lamps_v', 'scene_road_end_v_lamps'):
            lamp_specs = [(-0.40, -0.40, +1.0), (+0.40, -0.10, -1.0)]
            for idx_l, (lx, ly_lamp, arm_dir) in enumerate(lamp_specs):
                bm_lp = bmesh.new()
                pr = 0.022
                add_box(bm_lp, lx - pr, lx + pr, ly_lamp - pr, ly_lamp + pr, 0.0, 0.40)
                ax0 = min(lx, lx + arm_dir * 0.19)
                ax1 = max(lx, lx + arm_dir * 0.19)
                add_box(bm_lp, ax0, ax1, ly_lamp - pr, ly_lamp + pr, 0.365, 0.40)
                bvh_lp = finalize_bvh(bm_lp)
                comps.append((f'lamp_{idx_l}', bm_lp, bvh_lp, bvh_lp, 'lamp'))

        if tname == 'scene_plaza_fountain':
            bm_fb = bmesh.new()
            r_out, r_in = 0.25, 0.19
            add_box(bm_fb, -r_out, r_out, -r_out, -r_in, 0.0, 0.065)
            add_box(bm_fb, -r_out, r_out, r_in, r_out, 0.0, 0.065)
            add_box(bm_fb, -r_out, -r_in, -r_in, r_in, 0.0, 0.065)
            add_box(bm_fb, r_in, r_out, -r_in, r_in, 0.0, 0.065)
            bvh_fb = finalize_bvh(bm_fb)
            comps.append(('fountain_rim', bm_fb, bvh_fb, bvh_fb, 'sidewalk'))

            bm_fw = bmesh.new()
            add_box(bm_fw, -r_in, r_in, -r_in, r_in, 0.0, 0.04)
            add_box(bm_fw, -0.088, 0.088, -0.088, 0.088, 0.04, 0.24)
            bvh_fw = finalize_bvh(bm_fw)
            comps.append(('fountain_water', bm_fw, bvh_fw, bvh_fw, 'water'))

        if tname == 'scene_plaza_red_wall_44':
            bm_rw = bmesh.new()
            add_box(bm_rw, -0.17, hg, -hg, -0.39, 0.0, 0.33)
            bvh_rw = finalize_bvh(bm_rw)
            comps.append(('red_wall', bm_rw, bvh_rw, bvh_rw, 'red_wall'))

        if tname == 'scene_plaza_red_wall_54':
            bm_rw = bmesh.new()
            add_box(bm_rw, -hg, hg, -hg, -0.39, 0.0, 0.33)
            add_box(bm_rw, 0.39, hg, -hg, hg, 0.0, 0.33)
            bvh_rw = finalize_bvh(bm_rw)
            comps.append(('red_wall', bm_rw, bvh_rw, bvh_rw, 'red_wall'))

        # Raycast Depth, Thickness, Normal (using 3-tuple comps)
        comps_3 = [(c[0], c[1], c[2], c[3]) for c in comps]
        z_front, thickness, normal_v = raycast_tile_maps(comps_3, w_cur, h_cur, cx_cur, cy_cur)

        # Render 3x3 supersampled Albedo Color sprite directly from the 3D geometry & exact palette
        albedo = np.zeros((h_cur, w_cur, 4), dtype=np.float32)
        inv_s = 1.0 / ASSET_S_PX
        ray_dir_front = -F_CAM
        sub_offsets = (0.1667, 0.5, 0.8333)

        for py in range(h_cur):
            for px in range(w_cur):
                col_acc = np.zeros(3, dtype=np.float32)
                hits = 0
                for sy in sub_offsets:
                    y_v = (cy_cur - (py + sy)) * inv_s
                    u_vec = y_v * U_CAM
                    for sx in sub_offsets:
                        x_v = ((px + sx) - cx_cur) * inv_s
                        orig_front = x_v * R_CAM + u_vec + 10.0 * F_CAM

                        best_z = -1e9
                        best_loc = None
                        best_n = None
                        best_mat = None

                        for (_cname, _bm, bvh_f, _bvh_b, mat_tag) in comps:
                            loc, norm, _idx, _dist = bvh_f.ray_cast(orig_front, ray_dir_front, 25.0)
                            if loc is not None:
                                zf = loc.dot(F_CAM)
                                if zf > best_z:
                                    best_z = zf
                                    best_loc = loc
                                    best_n = norm
                                    best_mat = mat_tag

                        if best_loc is not None:
                            hits += 1
                            lx, ly, lz = best_loc.x, best_loc.y, best_loc.z
                            if rot_angle != 0.0:
                                rx = lx * cos_a + ly * sin_a
                                ry = -lx * sin_a + ly * cos_a
                                lx, ly = rx, ry

                            mtag = best_mat
                            if mtag == 'ground':
                                if lz < -H_SIDEWALK + 0.005:
                                    mtag = 'dirt'
                                elif lz < -0.005 and is_road_xy(tname, lx, ly):
                                    mtag = 'asphalt'
                                    if tname == 'scene_road_crosswalk_u' and abs(lx) < 0.14:
                                        for sc in (-0.15, -0.05, 0.05, 0.15):
                                            if abs(ly - sc) < 0.024:
                                                mtag = 'stripe'
                                                break
                                else:
                                    mtag = 'sidewalk'

                            c_top, c_left, c_right = PALETTE[mtag]
                            if mtag == 'red_wall' and (lz < 0.05 or lz > 0.275):
                                c_top, c_left, c_right = PALETTE['sidewalk']

                            nx_w, ny_w, nz_w = best_n.x, best_n.y, best_n.z
                            if nz_w > 0.65:
                                c = c_top.copy()
                                if mtag == 'sidewalk' and (abs(lx) < 0.007 or abs(ly) < 0.007):
                                    c *= 0.945
                            elif nx_w > abs(ny_w) * 0.8 and nx_w > 0:
                                c = c_right.copy()
                            else:
                                c = c_left.copy()
                            col_acc += c

                if hits > 0:
                    albedo[py, px, :3] = col_acc / hits
                    albedo[py, px, 3] = (hits / 9.0) * 255.0

        albedo_u8 = np.clip(np.round(albedo), 0, 255).astype(np.uint8)
        write_png_rgba8(f"generated/scene_tiles/{tname}.png", albedo_u8)
        save_encoded_maps(tname, z_front, thickness, normal_v, albedo_u8[:, :, 3])

        for (_cname, bm, _bf, _bb, _mt) in comps:
            bm.free()


# ==============================================================================
# Main Pipeline Execution in Blender 5.2
# ==============================================================================
def main():
    print("=== Starting Blender 5.2 3D Reconstruction & Map Generation ===")
    with open("blender/tile_specs.json", "r") as f:
        specs = json.load(f)

    # 1. Process all 129 buildingTiles (000..128)
    for idx in range(129):
        tname = f"buildingTiles_{idx:03d}"
        spec = specs[tname]
        w, h = spec['width'], spec['height']
        cat = spec['category']

        if cat == 'base':
            cx_px, cy_px = w / 2.0, h - 68.0
        elif cat == 'middle':
            cx_px, cy_px = w / 2.0, h - 25.5
        elif cat == 'roof':
            cx_px, cy_px = w / 2.0, h - 26.2
        else:  # antenna
            cx_px, cy_px = w / 2.0, h - 3.0

        rgba_orig = read_png_rgba8(f"assets/{tname}.png")
        alpha_u8 = rgba_orig[:, :, 3]

        comps = build_building_tile_components(spec)
        z_front, thickness, normal_v = raycast_tile_maps(comps, w, h, cx_px, cy_px, alpha_u8)
        save_encoded_maps(tname, z_front, thickness, normal_v, alpha_u8)

        # Also create white-rimmed roof variant for buildingTiles_128 (used on B1, B2, B7 in sample.png)
        if idx == 128:
            rgba_white = rgba_orig.copy()
            yy, xx = np.mgrid[0:h, 0:w]
            dx = np.abs(xx - 48.5) / 36.0
            dy = np.abs(yy - 25.5) / 18.0
            rim_mask = (alpha_u8 > 50) & ((dx + dy) > 0.72)
            rgb_f = rgba_white[:, :, :3].astype(np.float32)
            lum = 0.35 * rgb_f[:, :, 0] + 0.45 * rgb_f[:, :, 1] + 0.20 * rgb_f[:, :, 2]
            for c_i, tint in enumerate((1.0, 1.0, 0.985)):
                ch = rgb_f[:, :, c_i]
                ch[rim_mask] = np.clip((lum[rim_mask] * 1.19 + 24.0) * tint, 0, 255)
            rgba_white[:, :, :3] = rgb_f.astype(np.uint8)
            write_png_rgba8("generated/scene_tiles/buildingTiles_128_white.png", rgba_white)
            save_encoded_maps("buildingTiles_128_white", z_front, thickness, normal_v, alpha_u8)

        for (_cname, bm, _bf, _bb) in comps:
            bm.free()

        if (idx + 1) % 25 == 0 or idx == 128:
            print(f"  Processed {idx + 1}/129 buildingTiles...")

    # 2. Build and bake all 18 non-building scene tiles
    print("Building and baking 18 non-building scene tiles...")
    build_scene_tile_meshes_and_maps()

    # 3. Construct full 3D reconstructed scene in Blender 5.2 and save .blend file + 3D render
    print("Constructing full 3D city scene in Blender 5.2 and saving blender/reconstructed_assets.blend...")
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene

    # Add Orthographic Camera matching sample.png
    cam_data = bpy.data.cameras.new("IsoCamera")
    cam_data.type = 'ORTHO'
    cam_data.ortho_scale = 918.0 / SAMPLE_S_PX
    cam_obj = bpy.data.objects.new("IsoCamera", cam_data)
    scene.collection.objects.link(cam_obj)
    cam_obj.rotation_euler = CAM_EULER
    cam_obj.location = Vector((3.0, 2.0, 0.5)) + 15.0 * F_CAM
    scene.camera = cam_obj

    # Add Sun Light
    light_data = bpy.data.lights.new(name="SunLight", type='SUN')
    light_data.energy = 3.5
    light_obj = bpy.data.objects.new(name="SunLight", object_data=light_data)
    scene.collection.objects.link(light_obj)
    light_obj.rotation_euler = Euler((math.radians(45), math.radians(-25), math.radians(30)), 'XYZ')

    # Add reconstructed 3D meshes for the 8 buildings into the Blender scene
    buildings_3d = [
        ("B1_Yellow_4F", 0, 0, [29, 51, 51, 51, 128]),
        ("B2_Red_2F", -1, 2, [36, 49, 128]),
        ("B3_Brown_1F", 0, 3, [14, 102]),
        ("B4_Brown_4F", 2, 3, [99, 38, 38, 38, 110]),
        ("B5_Grey_2F", 2, 4, [124, 31, 127]),
        ("B6_GreenShop_1F", 2, 1, [108, 88]),
        ("B7_Modern_3F", 3, 1, [1, 16, 16, 128]),
        ("B8_RedBlue_2F", 4, 3, [34, 52, 128]),
    ]
    for bname, u, v, tids in buildings_3d:
        z_cur = 0.0
        for layer_idx, tid in enumerate(tids):
            spec = specs[f"buildingTiles_{tid:03d}"]
            comps = build_building_tile_components(spec)
            for cname, bm, _bf, _bb in comps:
                mesh = bpy.data.meshes.new(f"{bname}_{layer_idx}_{cname}")
                bm.to_mesh(mesh)
                bm.free()
                obj = bpy.data.objects.new(f"{bname}_{layer_idx}_{cname}", mesh)
                obj.location = Vector((float(u), float(v), z_cur))
                scene.collection.objects.link(obj)
            if layer_idx == 0 or spec['category'] == 'middle':
                z_cur += H_FLOOR

    bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath("blender/reconstructed_assets.blend"))
    print("=== Completed Blender 5.2 Reconstruction & Asset Generation Successfully! ===")

if __name__ == "__main__":
    main()
