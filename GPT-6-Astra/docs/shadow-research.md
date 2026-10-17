# Dynamic shadows from layered depth and thickness

Research and implementation design for `TASK.md`, 18 October 2026. This document separates established methods from the project-specific derivation below. The renderer keeps the supplied sprite artwork and a fixed orthographic view, reconstructs proxy solids in Blender, and evaluates a moving directional light in Three.js.

## Findings from primary sources

* **Screen-space traversal.** McGuire and Mara describe tracing a ray through adjacent depth-buffer pixels with a perspective-correct DDA. Their intersection test uses the depth range traversed within a pixel and a finite surface thickness; they also discuss multiple depth layers, strides, jitter, missing geometry, and a viewport guard band. For this project, orthographic projection removes the perspective division from interpolation, while the interval intersection principle remains useful. [McGuire and Mara, *Efficient GPU Screen-Space Ray Tracing*, JCGT 3(4), 2014, especially sections 1–3](https://jcgt.org/published/0003/04/04/paper.pdf).
* **What a production contact-shadow pass does.** Epic traces from each shaded point toward a light through scene depth. With a fixed sample count, longer traces produce more artifacts. Consequently, increasing the maximum ray length alone is not a quality improvement. [Epic Games, *Contact Shadows*](https://dev.epicgames.com/documentation/en-us/unreal-engine/contact-shadows-in-unreal-engine).
* **Relationship to full shadows.** Bend's published presentation and example implementation document screen-space shadows used in *Days Gone*, including their usefulness for detail beyond ordinary shadow-map resolution. This establishes the technique as a practical complement to global visibility data, rather than proof that a single visible depth layer can represent an arbitrary scene. [Bend Studio, *Inside Bend: Screen Space Shadows*, with SIGGRAPH 2023 materials](https://www.bendstudio.com/blog/inside-bend-screen-space-shadows/).
* **Modern hybrid approach.** Epic's SIGGRAPH 2025 MegaLights materials describe hierarchical depth traversal, short screen traces, a small assumed surface thickness, and fallback to hardware ray tracing. The useful lesson here is to distinguish an observed occluder from a ray that merely disappears behind incomplete screen data. [Epic Games, *MegaLights: Stochastic Direct Lighting*, screen-trace slides](https://advances.realtimerendering.com/s2025/content/MegaLights_Stochastic_Direct_Lighting_2025.pdf).
* **Bake data.** Blender exposes depth, position, and normal passes. Its manual cautions that several data passes are not antialiased and describes alpha thresholds affecting which surface contributes. A beauty image is therefore not a substitute for numerical geometry passes. The stable pass semantics are documented in the Blender manual; the project's scripts must additionally record the actual Blender executable version used. [Blender Manual, *Passes*](https://docs.blender.org/manual/en/3.5/render/layers/passes.html). Blender's own BVH API exposes mesh ray casts and returns hit position, normal, polygon index, and distance, enabling explicit entry/exit baking without relying on a display-transformed depth render. [Blender Python API, *BVHTree Utilities*](https://docs.blender.org/api/current/mathutils.bvhtree.html?highlight=ray).

## Selected representation

The selected design is a **layered orthographic occupancy field**. It is more informative than the usual screen-space contact-shadow input because Blender can bake surfaces hidden behind the first visible surface.

For every bake pixel, recover each reconstructed convex solid's front/back intersections by rasterizing its mesh triangles. Sort the resulting occupied depth intervals and merge only overlapping or touching intervals. Save at most eight disjoint intervals in front-to-back order:

```text
pixel u,v: [front0, back0], [front1, back1], ... , [front7, back7]
```

Each pair describes a finite solid segment along the camera ray. The air between two pairs remains air. Save the first visible surface's depth and world normal separately for reconstructing the receiving point, and retain useful front-depth, back-depth, and thickness preview images. Thickness is `back - front` for the associated interval; it is camera-ray thickness, not wall-normal thickness or distance along the light ray.

This distinction matters for the reference buildings. A single interval from a roof's front to the ground would incorrectly fill open space underneath an overhang or between separate buildings. Multiple intervals preserve these gaps. Overlapping volumes that actually occupy the same space should be merged, because a union of opaque solids casts the same binary shadow as its components.

The color image is assembled from the supplied building sprites, procedural ground and street props, and a limited bright-parapet color remap on selected buildings. It is a reconstruction of the reference composition, not a pixel-identical or wholly unmodified copy of the original assets. Blender geometry is the shadow proxy and must agree with that image's silhouette, roof slopes, wall depths, and ground contact. Painted doors and window frames remain flat where the proxy does not model their apparent extrusion.

The original artwork includes baked face shading. The implemented beauty shader preserves the reconstructed color's shading and multiplies it by `1 - shadowAmount * strength`; it does not add a second Lambertian lighting term. Normals currently supply receiver bias and a diagnostic view. The “original color” view displays the reconstructed composition without added shadows; the comparison overlay displays the supplied reference. Dynamic visibility can be physically motivated even when the color treatment is deliberately stylized.

## Coordinate and depth contract

Use one documented world convention for both Blender and the JavaScript shader. The equations below use Blender's Z-up world. Define:

* `C`: camera position;
* `R`, `U`, `F`: unit camera right, up, and forward vectors, with `F` pointing into the scene;
* `W`, `H`: orthographic world-space width and height covered by the bake;
* `Nx`, `Ny`: bake pixel dimensions;
* `u`, `v`: texture coordinates increasing to the right and upward;
* `d = dot(P - C, F)`: positive **linear camera depth**.

The checked scene uses the following basis and camera origin (rounded here; the manifest retains full precision):

```text
R = (-0.70710678, +0.70710678,  0.00000000)
U = (-0.35355339, -0.35355339, +0.86602540)
F = (-0.61237244, -0.61237244, -0.50000000)
C = (12.24744871, 12.24744871, 10.00000000) = -20 F
pixelsPerUnit = 73.53910524
W = 918 / pixelsPerUnit; H = 515 / pixelsPerUnit
```

Reconstruction and projection are exact for the chosen orthographic camera:

```text
x = (u - 0.5) W
y = (v - 0.5) H
P = C + x R + y U + d F

u(P) = 0.5 + dot(P - C, R) / W
v(P) = 0.5 + dot(P - C, U) / H
d(P) = dot(P - C, F)
```

In conventional right-handed view coordinates this depth is `-viewPosition.z`. It is not a raw perspective depth-buffer value, clip-space Z, distance from a single pinhole camera origin to an off-axis point, or world height. Always transform the normal and light into the same coordinate system before their dot product.

The bake files have top-down rows, so `v = 1 - (row + 0.5) / Ny`. The runtime explicitly reverses the raw interval rows before creating a `DataTexture` with `flipY = false`; ordinary color/front/back/normal PNG textures use the texture loader's vertical flip. Three.js documents both `flipY` and the different handling of `ImageBitmap`; its default filtering is unsuitable for byte-packed depth. [Three.js, *Texture*](https://threejs.org/docs/pages/Texture.html).

Camera fitting is a geometric measurement, not a choice of an “isometric” label. With equal horizontal azimuth and a Z-up orthographic camera, the ground-axis screen slope magnitude is `sin(elevation)`. A 2:1 diamond therefore implies 30 degrees of elevation, while a true isometric camera is approximately 35.264 degrees. Measure the asset edges and use the resulting camera consistently for color placement and data baking.

## Numerical storage

Use a shared finite depth range `[dMin, dMax]` recorded with the camera metadata. Quantize an endpoint as:

```text
q = round(clamp((d - dMin) / (dMax - dMin), 0, 1) * 65535)
highByte = floor(q / 256)
lowByte  = q - highByte * 256
```

One RGBA8 byte buffer stores a pair: `RG = front high/low`, `BA = back high/low`. The baker writes both a raw `.bin` runtime buffer and an inspectable PNG with the same data, for each of eight layers. Decode normalized sampled channels with:

```glsl
float unpack16(vec2 bytes) {
    return dot(bytes, vec2(65280.0, 255.0)) / 65535.0;
}
// d = mix(dMin, dMax, unpack16(sample.rg));
```

An empty interval has `front >= back`; the baker encodes empty pairs as zero bytes. The alpha channel is the low byte of back depth, not coverage. The runtime preserves all four bytes through raw-buffer `DataTexture` uploads, nearest sampling, no mipmaps, and no color conversion. Browser image/canvas decoding paths can involve premultiplication, which is why interval PNGs are inspection artifacts rather than runtime input. Setting `premultiplyAlpha = false` alone would only address texture upload, not every earlier image-processing step. Separate front/back PNGs have a true opaque coverage alpha for valid pixels and store their endpoint in RG, so they can use the normal PNG loading path.

Normals use `RGB = 0.5 * (normalWorld + 1)` and coverage in alpha, and are normalized after decoding. All geometry textures use `NoColorSpace`; the artwork is sRGB color data. The custom shader includes `colorspace_fragment` for final display conversion. [Three.js, *Color Management*](https://threejs.org/manual/pages/color-management.html).

The endpoint quantization interval is `(dMax - dMin) / 65535`. The checked bake uses depths 15 through 25 world units, for a quantum of approximately `0.0001525902`. The 8-bit grayscale depth/thickness previews are for inspection, never authoritative endpoint input; the shader computes thickness from the shared-range 16-bit front/back textures.

## Baking closed solids in Blender

The required scene is a genuine mesh reconstruction: closed walls, pitched roofs, extruded floor/island shapes, and any substantial foreground objects. A billboarding color plane alone cannot supply meaningful thickness.

The implemented `scripts/build_scene.py` creates and saves the closed meshes, renders a Cycles geometry preview, then rasterizes their actual mesh triangles in Python/NumPy. It transforms vertices into the shared camera basis, evaluates projected triangle coverage at pixel centers, and barycentrically interpolates linear camera depth. For each authored convex component, the minimum covered triangle depth is entry and the maximum is exit. This is geometrically equivalent to finding the first and last camera-ray intersections for that convex component; the core bake does not call a BVH or estimate depths from sprite colors.

Convex decomposition is an explicit input requirement: a concave object with disconnected occupied sections along a ray cannot be baked as one min/max pair. Roofs, walls, and props are therefore authored as separate convex parts. The rasterizer gathers a visible normal from the closest triangle and orients it camera-facing (`dot(N,F) <= 0`), compensating for inconsistent winding on some authored wedges. It does not rely on winding to pair entry/exit events. Closed, nondegenerate components remain necessary, and future modifiers would need evaluated-mesh extraction because the current script reads `obj.data` directly.

The script merges sorted intervals using a `0.00025` world-unit touching tolerance, auditing up to 12 temporary intervals. It raises an error if any pixel requires more than eight exported intervals, rather than silently truncating. The checked `scene.json` records eight exported layers, maximum seven occupied intervals, and zero overflow pixels. A four-layer export was insufficient for the scene. For every valid interval, the intended invariant is `front < back`; adjacent intervals obey `back[i] <= front[i+1]` after merging.

Independent Blender BVH validation is completed by `scripts/validate_bake.py`, with results recorded in `verification/geometry-validation.json`. The validator constructs its own BVH from the saved Blender mesh triangles and compares continuous intersections with the rasterized field. This remains a validation path, not the production baking method; its measured results and scope are detailed below.

The first visible surface depth/normal comes from the same bake geometry. The checked manifest records Blender `5.2.2 LTS`, 254 mesh components, and 131,975 covered pixels. These are bake metadata, not proof of visual fidelity: fit the geometry against the source sprites and `sample.png`, since a numerical shadow can be internally consistent but visibly detached from the illustrated building.

## Directional-light visibility algorithm

Let `L` be a normalized **surface-to-light** direction. A directional source makes this constant over the scene. For a receiving point reconstructed from front depth, offset the origin slightly outward:

```text
P0 = P + normalBias * N + rayBias * L
P(t) = P0 + t L, t > 0
```

Projection is affine, so compute its derivatives once. A general major-axis traversal derivation is:

```text
du/dt = dot(L, R) / W
dv/dt = dot(L, U) / H
dd/dt = dot(L, F)
pixelsPerWorldUnit = max(abs(du/dt) Nx, abs(dv/dt) Ny)
dt = pixelStride / pixelsPerWorldUnit
```

A one-pixel major-axis stride visits a contiguous thin rasterization of the projected line. Testing the depth range occupied by a ray segment rather than just its center reduces misses when a steep depth slope crosses a thin solid between samples. Exact texel-boundary DDA traversal remains a possible refinement; the implemented shader uses the bounded approximate stepping described below.

For each visited pixel, evaluate the valid stored intervals in order. The mathematical overlap test for an unmodified solid `[front, back]` and ray segment `[rMin, rMax]` is:

```text
max(rMin, front) <= min(rMax, back)
```

`src/shadow.frag.glsl` contracts each interval slightly to reduce self-intersections at rasterized surfaces:

```text
epsilon = min(0.006, 0.2 * (back - front))
hit when rayMax > front + epsilon and rayMin < back - epsilon
```

If an interval is empty, no later interval exists at that pixel. If `rayMax <= front + epsilon`, deeper ordered intervals cannot intersect the ray either. These conditions allow the shader to avoid fetching all eight textures on most steps. A hit returns shadow amount one (visibility zero); no hit returns shadow amount zero. The contracted test is a practical bias, not the exact unmodified-solid overlap condition.

The current ray starts at `P + 0.012 N + 0.018 L`. The controls constrain sun elevation to 10–85 degrees, so `L.z` is positive. The maximum possible blocker height from the bake supplies a physical trace bound:

```text
traceDistance = max(0, (maxHeight - startWorldZ) / max(L.z, 0.001))
projected = (dot(L,R), dot(L,U)) * pixelsPerUnit
stepWorld = max(0.7 / max(length(projected), 1), traceDistance / 192)
dd = dot(L,F) * stepWorld
sample depth range = [sampleDepth - 0.48 abs(dd), sampleDepth + 0.48 abs(dd)]
```

The shader takes at most 192 steps per ray, stopping on a hit, image/depth-boundary exit, or the height-derived distance. For short rays, samples are approximately 0.7 pixels apart in projected Euclidean distance. Longer rays increase their spacing to span the trace within the budget. The depth ranges approximate a sample's footprint; they are not exact per-texel clipping intervals, and the initial/tail portions and small gaps between ranges are a potential source of misses. A segment-depth test reduces depth tunneling but cannot recover a thin caster skipped horizontally by a large stride.

This differs materially from `rayDepth > frontDepth`: the latter treats everything behind a visible surface as filled, so it produces large false shadows. The finite back endpoint allows light to pass behind a solid. Checking eight intervals also allows a deeper hidden building to block a ray after it passes behind the first building.

For near-zero projected light direction, the implemented denominator floor avoids division by zero and preserves bounded marching. An analytic same-pixel interval test would be a stronger extension than this approximate sampling if arbitrary light directions or non-frontmost receivers are added.

For a future point light, the same coordinate equations apply per receiver with `L = normalize(lightPosition - P0)` and a ray length limited to that distance; the directional-height bound would need adjustment. The implemented global source is directional, so its elevation/azimuth animate without rebaking the geometry.

## Bias, edge quality, and cost

Depth quantization tolerance and artistic self-intersection bias have different roles. A numerical tolerance of one to two endpoint quanta would cover encoding error; the implemented interval contraction of up to `0.006` world units is larger and deliberately rejects near-boundary hits. Its cap at 20 percent of interval thickness keeps at least 60 percent of even a thin interval. Normal/ray offsets prevent the receiver from immediately hitting its own surface. Larger offsets detach shadows, while contracting intervals can leak light; these are tradeoffs to evaluate against a mesh reference. The implementation does not exclude the entire receiving object, so its roof can shadow its own wall.

Treat boundaries as discontinuities. Bilinear filtering of packed bytes is invalid, and even filtering decoded depth can invent a slope connecting an unrelated roof and background. The implemented soft-shadow mode averages three directions around a cone with radius `softness * 0.035`, using a deterministic per-pixel rotation. This keeps repeat captures stable and approximates a broad source, with visible three-sample granularity possible at shadow edges. Hard mode uses one ray. A depth/normal-aware visibility filter or more angular samples would be future quality options; geometry intervals should not be blurred across silhouettes.

At 918 by 515 pixels the output contains 472,770 pixels. A 192-step ray with eight interval reads has a full-frame upper bound of approximately 726 million interval reads; restricting that calculation to the bake's 131,975 covered pixels gives approximately 203 million. Three-ray softness triples those bounds. These are pessimistic arithmetic bounds, not measurements: color/geometry masks, ordered-layer exits, shadow hits, and domain/height termination substantially reduce actual work. The application renders at a fixed native resolution and pixel ratio one, so enlarging its CSS presentation does not multiply trace work.

The UI exposes azimuth, elevation, softness, shadow strength, and diagnostic views. The 192-step budget, nominal 0.7-pixel stride, and receiver offsets are shader constants. A low sun creates longer rays and therefore wider steps, with possible missed thin casters; validation should include that case. Hierarchical min/max occupancy bounds could skip empty blocks, but constructing conservative bounds for eight disjoint intervals is more involved than generating ordinary color mipmaps.

## Limits and alternatives

| Representation | Useful property | Remaining tradeoff |
| --- | --- | --- |
| One front depth plus constant thickness | Minimal storage and cheap contact shadows | Thickness is guessed; hidden surfaces and gaps are missing |
| Front plus outermost back | Measures an occupied envelope | Fills disconnected air gaps along the camera ray |
| Eight merged entry/exit pairs, selected here | Represents hidden solids and real gaps in a bounded fixed view | Export rejects interval-cap overflow; sampled silhouettes and finite image extent remain |
| Light-space shadow map from reconstructed meshes | Handles off-camera casters and changing camera views | Requires geometry at runtime and light-space resolution/bias management |
| Runtime mesh BVH or volumetric field | Broader visibility coverage independent of the camera | More storage, traversal, and implementation cost |

Three.js supports the light-space option by rendering shadow-casting geometry from the light's view; directional lights use an orthographic shadow camera. That would be the natural fallback for free camera movement or an extended world. [Three.js, *Shadows*](https://threejs.org/manual/pages/shadows.html).

The selected layered bake reduces the usual hidden-surface limitation because it includes geometry invisible in the beauty image. It does not recover solids outside the baked camera rectangle or depth range. Interval-cap overflow is rejected during baking, and the current scene has none; more complex scenes may require additional layers or another representation. No guard band is implemented, so boundary-crossing traces accept missing off-image occluders. Geometry omitted from the reconstruction, including the unknown backs of supplied sprites, cannot be inferred uniquely from color art.

The fixed view is part of the design. Resizing the presentation while keeping the same projected scene is supported; rotating the camera changes which rays the textures represent and requires a rebake or another representation. Moving the light is supported because occupied space remains constant. Moving a building without updating its data textures is not.

## Completed geometry validation

`verification/geometry-validation.json` records a successful Blender `5.2.2 LTS` validation run. The validator checks valid layers are contiguous, ordered, disjoint, within the recorded depth range, and free of overflow. It also checks finite decoded normals, reconstruction/reprojection consistency, and four synthetic interval tests covering an air gap, the incorrect filled envelope, an entry-boundary crossing, and visibility behind a finite back depth.

For 4,096 reproducibly selected covered pixels, first-visible-depth comparisons against the independent mesh BVH have a maximum absolute error of `7.97223e-5` world units, approximately 0.52 of the `1.52590e-4` depth quantum. The largest reprojection error is approximately `5.0e-16` in normalized UV coordinates. The depth comparison tests first hits; it does not independently measure every back endpoint at every pixel.

The validator also compares a CPU equivalent of the hard-shadow shader against independent continuous BVH visibility at the same 4,096 receivers and the same biased origins, for four sun directions:

| Sun azimuth / elevation | Agreement | False shadow samples | Missed shadow samples |
| --- | ---: | ---: | ---: |
| -40° / 40° | 98.97% | 1 | 41 |
| 140° / 40° | 98.51% | 4 | 57 |
| -70° / 23° | 97.83% | 1 | 88 |
| -10° / 78° | 99.46% | 12 | 10 |

These results support the geometry bake and the bounded hard-shadow traversal, while quantifying remaining rasterization/stride/bias errors. They are **CPU-equivalent hard-shadow comparisons, not GPU framebuffer readback**, and do not validate the three-ray soft-shadow mode, GPU texture-upload correctness, all possible light directions, or pixel-perfect reconstruction of the reference artwork. Browser screenshots and runtime checks supply separate evidence for the displayed result.

## Wider validation protocol

The completed geometry checks above are read from the generated manifest and validation report. The following wider acceptance protocol is not a claim that every recommended experiment has passed; additional completed measurements belong in the verification report:

1. **Color reconstruction:** compare the unlit assembled sprite scene to `sample.png` at identical 918 by 515 framing. Save a side-by-side image and absolute-difference image; compute pixel error/foreground overlap. Differences from shadowing should be evaluated separately from placement and color errors.
2. **Blender intermediates:** render the reconstructed proxy scene and inspect it alongside the color image. Export front, back, thickness, normal, and interval-count previews. Verify roof pitch, visible wall height, silhouette alignment, and ground contact.
3. **Numerical contract:** check endpoint ordering, valid masks, depth-range containment, interval overflow, finite normals, and PNG pack/unpack error. Reproject reconstructed front-hit points and verify they return to the originating pixel centers.
4. **Known visibility:** use a box on a plane for contact; a suspended slab for light passing beneath; and two separated slabs along a camera ray for the difference between an outer envelope and disjoint intervals. Include thin geometry and light directions almost parallel to the view.
5. **Changing light:** save screenshots at opposite azimuths and at high/low elevations. Ground shadows must move opposite the horizontal light direction and become longer at lower elevations. Cast shadows on walls should agree with the proxy geometry; their baked color shading intentionally remains unchanged.
6. **Reference visibility:** on representative scene pixels compare the texture trace with Blender mesh ray casts from the same biased receiver toward the same light. Report false positives and negatives, emphasizing silhouettes, overhangs, and interval-cap pixels rather than only easy interior regions.
7. **Performance and stability:** inspect browser shader compilation/errors and measure frame behavior at the actual native render resolution. Report device/browser context for timing; sample counts alone are not a frame-rate result. Repeat a static frame to ensure any jitter does not create uncontrolled shimmer.

The final repository's verification outputs should distinguish completed measurements from these recommended checks and should retain screenshots for both intermediate geometry and final dynamic-light states.
