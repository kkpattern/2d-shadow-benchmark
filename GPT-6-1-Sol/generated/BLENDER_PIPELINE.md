# Blender reconstruction and shadow buffers

`reconstructed-scene.blend` is a real Blender 5.2 project. It contains closed meshes for the placed buildings, their recessed roofs and parapets, the small shed roof, the ground foundation, trees, lamps, the low terrace walls, the cyan vent, and the detached road ramp. A hidden collection contains reusable multi-mesh proxies for all 129 source assets. These are intentionally low-poly shadow proxies; facade detail remains in the original PNG artwork used by Three.js.

To rebuild from the repository root on this machine:

```powershell
& 'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe' --background --python scripts/reconstruct_blender.py
```

The script reads the measured placements in `scene-layout.json` and the composed ground outline in `scenery-geometry.json`. Native building tiles use a 99-pixel-wide building footprint, a 35-pixel vertical story, and a 132-pixel-wide ground tile. The ground tile's top diamond is centered at native pixel `(66,59)` and its total side depth is 35 pixels. The scene scales these dimensions by `26/33`. Placed buildings share the continuous terrain, matching the artwork compositor's clipping of native base tiles; the reusable library retains their original foundations. A placed sprite's projected footprint is respected independently, avoiding accumulated offsets along a stack.

## Camera and units

The output resolution is 918 × 515. All depth values are signed, unnormalized distances in world units. One world unit projects to one pixel along an orthonormal camera axis. With origin `(459,257.5)`, the basis is:

```
right  = ( 1/sqrt(2), -1/sqrt(2), 0)
down   = ( 1/sqrt(8),  1/sqrt(8), -sqrt(3)/2)
toward = ( sqrt(3/8),  sqrt(3/8), 1/2)
```

For screen coordinates `(x,y)` and depth `d`, reconstruct a world position with:

```
P = (x - 459) * right + (y - 257.5) * down + d * toward
```

Depth increases toward the camera, so a solid interval has `front >= back`. At world height `Z=0`, depth is `sqrt(3) * (y - 257.5)`. Normals use the same right/down/toward basis. The Blender camera has a horizontal mirror scale to reproduce the artwork's Y-down projection convention; its render agrees with the numerical rasterizer.

## Binary files

Every binary is IEEE754 little-endian float32. Rows run from the top of the image to the bottom, and samples are at pixel centers `(x+0.5,y+0.5)`.

| File | Packing |
| --- | --- |
| `shadow-intervals.f32` | Four layers, layer-major, then row-major RGBA. Each texel is `[front, back, objectId, valid]`. |
| `shadow-normals.f32` | Row-major RGBA: `[normalRight, normalDown, normalToward, valid]`. |
| `shadow-materials.f32` | Row-major RGBA: `[linearR, linearG, linearB, valid]`. Proxy materials are diagnostic, while the app uses original sprite colors. |

For an interval layer `l`, pixel `(x,y)`, and channel `c`, the float index is `(((l*515+y)*918+x)*4+c)`. Invalid texels are zero-filled. `bake-metadata.json` and `shadow-buffers.json` contain the same encoding, projection, object table, actual depth range, and bake statistics. `depthRange` covers visible front depths for display; `occupiedDepthRange` includes the farthest retained back depth and is the appropriate bound for ray traversal.

## How occupied intervals are generated

The exporter obtains evaluated Blender mesh triangles and rasterizes their orthographic front and back intersections. It first forms an occupied range for each closed object. It sorts those ranges by front depth and merges only overlapping or adjoining ranges, using a 0.3-unit numerical tolerance. It retains the nearest four separated occupied ranges. It does not create a solid range between unrelated front and back objects across an air gap. The metadata reports any pixels with more than four occupied ranges; the deeper ranges at those pixels are omitted.

Normals come from the nearest intersected triangle, with unit length in the camera basis. The browser uses the raw float files with nearest filtering. The PNG files are visual QA views, not precision inputs: `depth-front.png` and `depth-back.png` normalize to the metadata's depth range, `thickness.png` normalizes to `thicknessPreviewMax`, and `normals.png` encodes XYZ as `N*0.5+0.5`. `validity.png`, `materials.png`, `geometry-preview.png`, and the actual Blender workbench render `blender-preview.png` make the reconstruction inspectable.

`geometry-qa.json` records finite data, ordered front/back intervals, unit-normal precision, and silhouette overlap with the composed artwork. `proxy-mask-comparison.png` marks artwork without a proxy in red and proxies outside the artwork in yellow; the small residuals are largely sprite decoration and antialiasing.

The proxies approximate sprite silhouettes, overhangs, and decorative details. The sparse screen-space representation also has the usual limitation that geometry absent from the reference camera cannot cast an independently reconstructed off-screen shadow.
