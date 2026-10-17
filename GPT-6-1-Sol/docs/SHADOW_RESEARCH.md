# Screen-space shadows for an orthographic sprite city

Research retrieved **2026-10-18** (Asia/Shanghai). This document completes the research portion of `TASK.md` and specifies a practical Blender-to-Three.js data contract. Literature findings are cited where discussed; the proposed pipeline, coordinate contract, shader pseudocode, and verification plan are an implementation design for this repository.

## Current implementation and audit (2026-10-18)

The remaining research/design sections describe the general recommended pipeline; the following is the concrete repository implementation. In particular, its depth sign is deliberately the **opposite** of the positive camera-forward convention used in the general equations below. The implemented convention is internally consistent and does not require conversion at runtime.

- `generated/bake-metadata.json` defines a 918 by 515 buffer with top-to-bottom rows, pixel-center samples, four layer-major RGBA float32 interval images, and a visible-surface normal image. Interval RGBA is **front toward-camera depth, back toward-camera depth, object ID, validity**. Front depth is greater than or equal to back depth. Normal XYZ is camera-right, screen-down, toward-camera.
- The world-to-view basis is orthonormal. One world unit equals one screen pixel in that basis. An absolute screen sample `(x,y)` and depth `d` reconstruct as `(x-459)*right + (y-257.5)*down + d*toward`. `src/main.js` projects the world sun through exactly this basis. The shader flips the display UV's Y when fetching the top-down numerical buffers. The sign and vertical alignment have been checked against the metadata.
- The bake script rasterizes triangles from evaluated Blender mesh geometry at pixel centers. It computes each object's greatest and least toward-camera depths, sorts occupied intervals, and merges overlapping or almost touching intervals with a 0.3-unit tolerance. It retains four disconnected intervals, so air gaps larger than that merge tolerance remain empty. A merged interval keeps its foremost contributing object's ID; that ID does not identify every component in the union.
- The final bake contains 127 objects and 133,204 valid visible pixels. **328 pixels exceed four occupied intervals** (about 0.246% of valid pixels); their additional, farthest intervals are discarded. Four layers therefore improve hidden coverage but do not represent every occupied segment of the proxies.
- The first interval's front depth plus pixel position is the receiver; the separate normal buffer supplies its geometric normal. Position XYZ is reconstructed implicitly. Runtime does not load the exported material-color float buffer. The original-art composition supplies visible color, and numerical proxies determine shadow visibility.
- The final shadow traversal uses **per-cell DDA**, a 1440-cell bound, texel-center interval fetches, and the ray's entry/exit depths inside each cell. Corner crossings advance both axes. A depth-volume cutoff ends rays once they pass the occupied scene range. The earlier prototype used 256 steps at a projected 1.65-pixel stride; that version could skip texels and apply a preceding cell's depth segment to the wrong endpoint texel, causing false blockers as well as leaks. That prototype is no longer the intended implementation.
- The origin moves 0.8 units along the receiver normal. The immediate same-ID portion is clipped until ray distance 3.2, after which self shadowing is allowed. Intervals are slightly eroded by `min(0.25, thickness*0.1)` at each end; essentially zero-thickness segments are skipped. These are documented artistic/raster tolerances, not a floating-point error proof. Erosion can still remove very fine contact shadows.
- A hard sun uses one ray. A soft sun uses three fixed angular samples on a small triangle around the sun direction, at 0.65 times the requested angular cone radius. This gives stable, inexpensive approximate softness, with at most four raw visibility levels. There is no temporal accumulation or receiver-aware denoising. Fine roof rims can retain raster stair steps or discrete penumbra bands.
- Float textures use nearest filtering and non-color interpretation. The shadow target is 8-bit. The final composite intentionally darkens and tints the supplied artwork in its original display color space so the unshadowed composition remains faithful. This differs from the physically linear lighting workflow recommended below; the strength and tint are artistic controls.

The audit confirmed that azimuth 225 degrees/elevation 42 degrees produces a view-space sun approximately `(0,-0.951,-0.308)`. Both camera-visible positive-X/positive-Y building facades then face away from the light; their darkening is expected rather than evidence of a reversed camera basis. The runtime validates the bake dimensions/layer count, and the light animation advances independently of its shadow-render throttling.

The ordinary `depthRange` metadata describes visible first-layer fronts, not the complete occupied volume. For DDA's depth exit test the correct conservative bounds are **minimum back over every valid layer, maximum front over every valid layer**. The final data's occupied bounds are approximately `[-267.3132, 306.9475]`; visible-front bounds are approximately `[-251.1474, 306.9475]`. Using only the latter as a traversal bound can discard valid deeper slabs. The audited runtime now supplies `occupiedDepthRange` to the shadow pass, with a conservative `[-600,600]` fallback, and retains `depthRange` for debug normalization.

No complete Blender geometric shadow-reference comparison is implied by this audit. The numerical interval invariants and coordinate mapping are checked; proxy-to-art silhouette mismatch, dropped fifth-plus layers, subpixel geometry, display-space shading, and finite area samples remain practical limitations.

## Decision

Keep the supplied isometric PNG artwork as the source of visible color. Reconstruct simple solid proxy models in Blender, project them through one fixed orthographic camera, and bake **linear front depth, linear back depth, receiver depth/position, receiver normal, validity, and object identity**. Trace from each visible receiver toward the movable light through those buffers. Use a small set of light samples to produce soft edges.

This preserves the reference's illustrated appearance while giving the light a meaningful 3D relationship to buildings, sidewalks, roofs, and roads. The proxy volume is an authored approximation of each sprite, not a recovery of its unique true geometry. A single image cannot determine hidden shape.

For the first implementation, a front/back interval is suitable for a solid boxlike building. Preserve separate objects or multiple intervals wherever camera rays cross disconnected geometry. If the initial implementation stores only the nearest object interval, expose and document that restriction; do not call the result complete geometric visibility. For a freely moving camera or arbitrary offscreen geometry, retain real proxy meshes and use light-space shadow maps or geometric ray tracing as a fallback.

## What the literature establishes

**Pixel traversal and finite thickness.** McGuire and Mara's peer-reviewed implementation traverses contiguous screen pixels with a perspective-correct DDA. It represents depth samples as finite slabs, compares the ray's depth *interval* within a pixel against them, supports several depth layers, and discusses guard bands for missing viewport information. A fixed world-distance march can skip pixels or visit pixels repeatedly under perspective. A one-sided “ray is behind depth” test instead treats every depth sample as an unbounded wall. These are useful distinctions even though the fixed orthographic camera here removes perspective interpolation complexity. [McGuire and Mara, *Efficient GPU Screen-Space Ray Tracing*, JCGT 2014](https://jcgt.org/published/0003/04/04/).

**Production role.** Bend Studio describes its shipped screen-space shadow technique as a complement to shadow maps that captures fine shadow detail, including distant details that are expensive for traditional maps. The studio provides its SIGGRAPH 2023 presentation and example code. This supports using image-space tracing for detail, but does not establish that one visible depth layer can replace all scene visibility. This project has a more favorable fixed-view, small-scene setting and can afford to author extra hidden information offline. [Bend Studio, *Inside Bend: Screen Space Shadows*](https://www.bendstudio.com/blog/inside-bend-screen-space-shadows).

**Hidden layers.** Deep G-buffers capture information behind the primary visible layer. Mara, McGuire, and Luebke show that a second appropriately separated layer improves several screen-space illumination effects while remaining view dependent. Layer separation matters: storing two very close surfaces may still omit the important distant object. A front/back pair for one object is different from two independent visible surface layers; the former describes its occupied thickness, the latter describes additional geometry. [Mara et al., *Lighting Deep G-Buffers*, NVIDIA technical report 2013](https://casual-effects.com/research/Mara2013DeepGBuffer/Mara2013DeepGBuffer-small.pdf).

**Acceleration.** Widmer et al. combine a hierarchy with local planar approximations to skip empty space and handle multiple depth layers. Their paper explains why a bound on march steps can miss geometry even when a final binary search is used. A hierarchy improves traversal efficiency; it cannot invent missing surfaces. A simpler conservative min/max pyramid would be a possible optimization here after correctness is established. [Widmer et al., *An Adaptive Acceleration Structure for Screen-space Ray Tracing*, HPG 2015](https://research.nvidia.com/sites/default/files/pubs/2015-08_An-Adaptive-Acceleration/AcceleratedSSRT_HPG15.pdf).

**Bias versus thickness.** Unity's HDRP contact-shadow documentation distinguishes ray bias, which can reduce self shadowing but detach contacts when excessive, from thickness, which can fill holes but widen shadows. It also identifies sample count as a quality/performance control. These controls solve different problems: increasing a caster's physical thickness to cover a numerical-origin error alters the object, and increasing origin bias to compensate for a missing back depth can detach its shadow. [Unity, *Contact Shadows*, HDRP 10.5](https://docs.unity3d.com/Packages/com.unity.render-pipelines.high-definition%4010.5/manual/Override-Contact-Shadows.html).

**Numerical origins.** NVIDIA's analysis of geometric ray tracing offsets secondary-ray origins beyond a floating-point uncertainty bound along the geometric normal. Its exact error constants concern triangle traversal and do not transfer directly to texture-space slabs. The applicable principle is to separate true surface thickness from numerical tolerance and to relate the tolerance to representation error. Our largest errors are likely to be raster resolution, proxy alignment, and quantized depth rather than triangle-intersection roundoff. [van Antwerpen, *Solving Self-Intersection Artifacts in DirectX Raytracing*, NVIDIA 2023](https://developer.nvidia.com/blog/solving-self-intersection-artifacts-in-directx-raytracing/).

**Softness.** NVIDIA's PCSS material estimates a penumbra from light size and blocker/receiver distances before filtering shadow comparisons. It offers a useful contact-hardening reference. Because this implementation already traces receiver-to-light rays, sampling several positions on the light directly is easier to reason about than transplanting a PCSS filter into the camera-depth image. A blur of depth values is not a visibility integral. [Fernando, *Percentage-Closer Soft Shadows*, NVIDIA 2005](https://developer.download.nvidia.com/shaderlibrary/docs/shadow_PCSS.pdf).

## Coordinate and data contract

Use one documented world basis for the bake and runtime. A convenient Blender convention is X/Y on the ground and Z up. Three.js can keep this convention by setting the camera's `up` to `(0,0,1)`, or convert every exported position and normal by the same axis permutation. Mixing a Y-up light with Z-up depth is a particularly difficult failure to diagnose visually.

Let `C` be the bake camera location; let orthonormal vectors `R`, `U`, and `F` point screen-right, screen-up, and camera-forward. For a world point `X`, define:

```text
x = dot(X - C, R)
y = dot(X - C, U)
d = dot(X - C, F)       // positive distance along parallel camera rays

u = (x - left) / (right - left)
v = (y - bottom) / (top - bottom)
X = C + x R + y U + d F
```

All depth values are this **linear camera-forward distance**, measured in the same units as the light and geometry. They are not Euclidean distance from the camera origin and not unprocessed hardware depth. Orthographic camera size stays independent of object distance, which makes it appropriate for this composition. [Three.js, `OrthographicCamera`](https://threejs.org/docs/pages/OrthographicCamera.html).

If using a standard OpenGL hardware depth value `z` rather than the proposed custom linear bake, reconstruct via the actual inverse projection:

```glsl
vec4 q = inverseProjection * vec4(uv * 2.0 - 1.0, z * 2.0 - 1.0, 1.0);
vec3 viewPosition = q.xyz / q.w;
```

That expression assumes WebGL's normal `[-1,+1]` clip-depth convention, default depth range, and no reversed-depth or logarithmic-depth alteration. With the usual orthographic near/far convention, positive forward distance is `near + z * (far - near)`. Do not apply the familiar perspective inverse-depth formula to an orthographic bake. WebGPU or reversed depth needs the matching convention.

The bake metadata should include image dimensions, bounds, camera basis, depth encoding range, object IDs, world units, and row order. Changing the camera projection invalidates a fixed camera-space bake. Resizing the viewport is safe if the same composition is letterboxed rather than silently stretching its projection.

### Suggested images

| Data | Meaning | Runtime use |
| --- | --- | --- |
| Original sprite/color atlas | Supplied RGBA artwork | Recreate color and alpha composition |
| Front depth | First entry into a caster solid along `F` | Beginning of occupied interval |
| Back depth | Exit of that same solid along `F` | End of occupied interval |
| Validity/coverage | A defined surface/interval exists | Reject clear pixels; do not interpret clear depth as geometry |
| Object ID | Stable integer associated with interval | Diagnostic views, immediate self-hit handling |
| Receiver depth or XYZ | Visible surface from which shadows are queried | Reconstruct world position |
| Receiver normal | Geometric face normal | Bias and optional diffuse response |
| Optional second interval | Another object behind the first | Hidden building and deep-overlap robustness |

For an orthographic view, receiver depth plus pixel coordinates and camera metadata is sufficient; XYZ is redundant but useful for diagnostics. Ground is a receiver even where no building sprite covers it. Roofs and vertical walls need different receiver positions and normals. Giving every sprite pixel the ground position produces plausible ground shadows but cannot produce correct roof or facade shadows.

## Why front and back matter

A solid caster at pixel `p` occupies the interval `[a(p), b(p)]`, with `a <= b`. The camera ray goes through empty space before `a`, enters the object, and leaves at `b`. The thickness is `b-a`. A shadow ray that passes behind `b` is in empty space again; this is the central benefit over a single-depth unbounded-wall model.

For a sample interval along the light ray with depths `[r0,r1]`, let `rmin=min(r0,r1)` and `rmax=max(r0,r1)`. The two depth intervals overlap when:

```text
rmax >= a - tolerance  AND  rmin <= b + tolerance
```

The XY sample must also intersect that pixel's footprint and validity must be true. Testing only the depth at a single ray point can jump completely through a thin object. Comparing a depth segment catches crossings within a step, provided the step does not skip the relevant XY cell. For best reference quality, use an exact grid-cell traversal and compute ray `t` at the cell's entry and exit. A dominant-axis DDA with one-pixel stride is a simpler approximation; use half-pixel strides or conservative neighbor coverage for thin diagonal features.

Do **not** combine the nearest front depth of one object and farthest back depth of another into one solid interval. A pole in front of a building must not fill all the air between them. Similarly, a hollow roof, archway, disconnected window trim, or a tree canopy plus trunk may have several disjoint intervals in one pixel. Split proxy components, keep layers, or accept and identify the conservative solid approximation.

## Bake strategy in Blender

1. Match the reference's orthographic view and sprite footprints first. Use boxes, roof rims, sidewalk slabs, tree trunks, and foliage blocks; decorative paint does not require separate geometry unless it should affect shadows.
2. Keep proxy models closed and consistently oriented. Geometry intended to be a thin sheet requires an explicitly chosen thickness.
3. Render visible receiver position/normal/mask from the complete scene with the fixed camera. Preserve true surface selection rather than reusing a beauty image's alpha as universal geometry.
4. For each caster or layer, render its front and back surfaces from identical projection and pixel sampling. Isolating one closed object makes entry/exit association unambiguous. An alternative is to cast parallel rays through the Blender geometry and record sorted entry/exit intersections directly.
5. Export numerical buffers without display transforms, exposure changes, denoising, or image compression that changes samples. Save a `.blend` and deterministic script so data can be regenerated.

Blender's manual documents Z as distance to visible surfaces, Position as world position, and Normal as the shading normal. It also notes that Z/Position/index passes are not anti-aliased and that alpha thresholds affect data passes. These passes are useful building blocks, but Z alone supplies neither a back exit nor a guarantee of our custom camera-forward encoding. Compute the linear depth from Position and the exported camera basis, or verify the Z convention with known test planes. [Blender Manual, *Passes* (4.2 reference)](https://docs.blender.org/manual/en/4.2/render/layers/passes.html).

The cited manual is a stable API/data-semantics reference, not proof that this repository has run Blender 5.2. Record the actual executable version separately when generating assets, as required by the task. Use the installed version's API and inspect the output rather than assuming a render pass or backface setting has unchanged behavior.

For a second back-surface render using an opposite camera, its depth values cannot be used directly: the camera basis and depth origin are different. Convert both passes to the common world/camera basis. A backface-only render of a closed isolated object can capture its exit; rendering the entire scene's backfaces can select the wrong object's exit.

### Precision and sampling

Prefer float data for numerical use (`Float32Array` textures or EXR decoded into float). If PNG portability is useful, pack depth into two or more integer channels and explicitly decode the representation. An 8-bit channel over a depth range `D` has an approximate quantization interval `D/255`; that may exceed the width of a window rim or the intended contact bias. A 16-bit packed depth has interval `D/65535`.

Depth, IDs, masks, and normals are non-color data. Use `NoColorSpace`, nearest filtering, clamp-to-edge addressing, and no automatically averaged mipmaps for interval tests. Explicitly check UV bounds before sampling: clamping an out-of-bounds ray to the last image column creates an artificial extruded wall. Three.js `DataTexture` supports raw typed-array data, defaults to nearest filtering, disables generated mipmaps, and defaults to `flipY=false`; set these explicitly so the contract remains visible in code. [Three.js, `DataTexture`](https://threejs.org/docs/pages/DataTexture.html).

Original color PNGs should be decoded as sRGB and lighting/shadow multiplication performed in linear space before the display conversion. Numeric buffer values must never receive that conversion. A custom shader must also perform the final output conversion correctly. [Three.js, *Color Management*](https://threejs.org/manual/pages/color-management.html).

## Runtime shadow query

For a visible receiver `P` and one sampled light location `L`, form a finite connection ray. Offset the receiver along its geometric normal `N` by a small `epsilonN`, then start a short distance `epsilonT` along the ray:

```text
P0 = P + epsilonN N
Q(t) = P0 + t (L - P0),        t in [tStart, 1)
tStart = epsilonT / length(L - P0)
```

For a directional light, use a normalized direction toward the light and a finite maximum distance covering the proxy volume. A light exactly over a receiver can project to a single screen pixel: handle that case by testing the complete depth segment in that cell rather than dividing by its projected length.

Project `P0` and `L` to UV. Under orthographic projection, UV and camera depth are affine in `t`, so interpolation is exact:

```text
uv(t) = uv0 + t (uvLight - uv0)
d(t)  = d0  + t (dLight  - d0)
pixelLength = max(abs((uvLight - uv0) * bufferSize))
```

The following is deliberately implementation-level pseudocode; exact cell traversal is preferable for the validation reference:

```glsl
// Ray clipped to the valid buffer rectangle and to the finite light segment.
int steps = max(1, int(ceil(pixelLength / pixelStride)));
for (int i = 0; i < MAX_STEPS; ++i) {
    if (i >= steps) break;
    float ta = mix(tStart, tEnd, float(i) / float(steps));
    float tb = mix(tStart, tEnd, float(i + 1) / float(steps));
    vec2 uv = uvAt(0.5 * (ta + tb));
    if (outsideUnitSquare(uv)) break;
    float lo = min(depthAt(ta), depthAt(tb));
    float hi = max(depthAt(ta), depthAt(tb));
    for (int layer = 0; layer < LAYERS; ++layer) {
        Interval slab = fetchInterval(uv, layer); // nearest, no color conversion
        if (!slab.valid) continue;
        bool overlaps = hi >= slab.front - epsilonDepth
                     && lo <= slab.back + epsilonDepth;
        bool immediateSelf = slab.id == receiverId && tb < selfRejectDistanceT;
        if (overlaps && !immediateSelf) return 0.0;
    }
}
return 1.0;
```

If `steps > MAX_STEPS`, do not silently spread the steps across the complete ray and claim pixel coverage. Either increase the loop cap, lower the shadow-buffer resolution, traverse a hierarchy, or explicitly report the larger stride quality mode. A final binary refinement improves a detected crossing; it cannot recover a skipped blocker.

Treat the immediate-self condition as optional and local. Ignoring the receiver object ID for the whole ray destroys legitimate self shadowing when a roof or another part of the same building blocks its facade. Keep depth tolerance small and separate from interval thickness. A reasonable starting tolerance is one or two depth quantization steps plus a small fraction of the world-space texel footprint; tune with debug views and a contact fixture rather than increasing until all artifacts disappear.

For back-facing receivers, evaluate direct lighting separately with `max(dot(N,l),0)` where appropriate. A visibility ray and a diffuse lighting term answer different questions. With already shaded sprite art, limit the dynamic relighting range to avoid multiplying the artwork by a second strong fixed diffuse shading model.

## Soft shadows and composition

For an area light with deterministic disk or rectangle samples `L_j`, estimate visibility by averaging independent hard queries:

```text
V(P) = sum_j visibility(P, L_j) / sampleCount
Clinear = Albedo * (Ambient + Direct * V(P))
```

Use the same small sample pattern across frames for a stable static camera. Four samples can reveal distinct bands; eight or more generally gives smoother transitions but multiplies trace cost. These are starting quality choices, not measured performance guarantees. Animate the light center and optionally its size, leaving the bake unchanged.

A directional emitter can use a small disk of directions instead of point locations. Its angular radius controls penumbra growth. For a finite point-area emitter, sample positions around its center and keep the light above the tallest proxy unless below-horizon lighting is intentionally supported.

A small bilateral blur of the **visibility result** can hide sampling noise. Weight neighbors by receiver depth, normal, and object identity to avoid dark leakage across silhouettes. Do not blur front/back depth together or let a ground shadow blur onto a foreground roof. An artistic minimum shadow opacity is acceptable for the illustration, but should be distinct from geometric visibility.

## Limits, alternatives, and practical tradeoffs

| Representation | Benefit | Principal failure / cost |
| --- | --- | --- |
| Visible front depth plus constant thickness | Smallest data and easiest first prototype | False solid walls, thin-object leaks, wrong thickness across shapes |
| Front/back of nearest object | Finite solid occupancy | Omits hidden objects and disjoint intervals |
| Per-object or layered front/back | Better hidden and inter-object visibility | More storage, sampling, and layer-selection work |
| Height map above ground | Efficient ground-plane 2.5D shadows | Cannot model vertical facades, overhangs, hollow structures generally |
| Hierarchical interval traversal | Skips empty regions for long rays | Additional structure and traversal complexity |
| Proxy mesh shadow maps | Handles offscreen casters and camera changes | Additional render passes, light-space aliasing and bias |
| Geometric ray tracing | Visibility against the full proxy scene | Browser/runtime support and acceleration-structure cost |

A guard-band bake covers casters slightly outside the final crop, but cannot represent arbitrary offscreen content. A larger fixed bake can cover the entire authored diorama and make this limitation less visible. When a ray leaves the represented region, its remaining visibility is unknown; returning lit is a deliberate light-leak fallback, while returning shadow creates a dark border. Clip and expose this behavior in diagnostics.

Finite front/back data is exact only for the chosen sampled solid representation. It is not a signed distance field; the difference between ray depth and front depth is not a safe world-space sphere-tracing step. Using that difference as a large XY jump can skip narrow buildings.

Moving the light is supported. Moving or deforming a caster invalidates its static baked buffers unless the scene recomposites transformed per-object data or re-renders them. Moving the camera changes projected footprints and hidden coverage. Alpha-cutout decorations require matching caster coverage and an intentional opaque/cutout/transmission policy. Partial transparency is not recovered by an opaque slab test.

At full-screen resolution, workload is approximately receivers × traversed pixels × light samples × tested layers. Trace at a reduced fixed resolution if necessary, then reconstruct with receiver-aware filtering. Avoid claiming a frame rate until browser timings are measured on the actual machine. Cache static receiver reconstruction and bake data; only the light and shadow pass need to change each frame.

## Verification plan

1. Render a depth calibration fixture: two planes at known distances and one closed box. Decode exported values and verify front <= back, the known box thickness, and round-trip projection error below one bake texel.
2. Render diagnostic images for front depth, back depth, thickness, receiver depth, normal, ID, and validity. Inspect every silhouette and verify vertical orientation with an asymmetric marker.
3. Compare the assembled sprite scene to `sample.png` with shadows disabled. Record a screenshot and aligned difference image before evaluating new lighting.
4. Use known light poses on both sides of the diorama, directly overhead, and near a roof. Verify shadow direction, moving silhouette, ground contact, facade/roof receivers, and that a ray behind a caster's back exit remains lit.
5. Include a hidden-blocker fixture and a disconnected-interval fixture. These reveal the difference between one slab, multiple layers, and complete proxy visibility.
6. Compare one deterministic light pose against a Blender shadow-only render of the same proxies. Inspect a difference image; report silhouette or layer limitations instead of adjusting the proxy until unrelated errors cancel.
7. Capture lit/shadow debug masks and a short timed light sweep in the final browser. Check console errors and look for stair steps, detached contacts, border walls, and temporal bands.

The immediate acceptance target is an accurate reference composition with stable, visibly responsive shadows from a global moving light. The research does not establish complete 3D shape recovery or physically exact shadows from a single layer of sprite-derived geometry.
