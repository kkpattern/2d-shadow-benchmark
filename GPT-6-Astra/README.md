# Isometric Shadow Lab

A Three.js reconstruction of `sample.png`, using the supplied Kenney building
tiles, Blender 5.2 geometry, and dynamic screen-space raymarched shadows.
The reference is used for comparison only; it is not the rendered scene texture.

## Run

Requires Node.js 22.12+ (tested with 22.18). Baked assets are included, so Blender
is **not** required to run the demo.

```sh
npm ci
npm run dev
```

Open the local URL printed by Vite. `npm run build` creates `dist/`;
`npm run preview` serves the production build.

The light controls change azimuth, elevation, softness and shadow strength.
**Animate sun** (or Space outside a form control) moves the global light. The
six views show the lit scene, reconstructed source color, front depth, solid
thickness, world normals, and shadow visibility. **Compare reference** enables
a draggable before/after divider. The camera stays fixed to preserve the bake.

## Rebuild the Blender assets

Requires Blender **5.2** (tested with 5.2.2 LTS), Python 3.11+, NumPy and Pillow.

```sh
python -m pip install -r requirements.txt
npm run bake
```

The script finds the standard Windows Blender 5.2 installation or `blender` on
PATH. Override with `BLENDER_PATH` if needed. For example in PowerShell:

```powershell
$env:BLENDER_PATH = 'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe'
npm run bake
```

This performs the complete reproducible pipeline:

1. Assemble 24 sprite layers into eight building groups; draw the ground and
   missing props from the same solid descriptions used for the geometry.
2. Save **`blender/city.blend`** with 254 closed solid components, materials,
   orthographic camera, global sun, and packed street decal. Render a separate
   geometry preview with Cycles.
3. Rasterize mesh triangles into sorted, merged, disjoint camera-depth intervals.
   Export color, front/back depth, normals, thickness and eight interval layers.
4. Validate against independent Blender BVH ray casts and compare the source-color
   reconstruction with the reference.

`npm run verify` repeats the numerical and image comparisons without rebuilding.
Blender scripts use `--python-exit-code 1` so failed assertions fail the command.
All writes stay in this project. Blender may report a nonfatal OS thumbnail-cache
warning in a restricted environment; the `.blend`, render and bake still save.

## How the shadows work

The visible color preserves the illustrated assets. Blender supplies solid
geometry beneath them: walls, recessed roofs and parapets, pitched kiosk roof,
terraces, trees, street lamps and the island. No runtime shadow map or static
shadow texture is used.

Each 918 × 515 texel stores up to eight occupied camera-depth intervals. The
fragment shader reconstructs its receiver, projects a ray toward the directional
sun and tests that ray against the finite entry/exit intervals. Separate layers
preserve air gaps and hidden casters. Traces stop above the highest solid or at
the bake boundary. Softness uses three deterministic directions around the sun.

Depth endpoints have 16-bit precision over the shared range 15–25 world units.
Raw RGBA buffers preserve all packed bytes, including depth stored in alpha;
PNG decoding/premultiplication is avoided for the interval data. Color is sRGB;
depth and normals are numerical data. The measured scene needs seven intervals
at most, with **zero overflow** in the eight-layer export.

See [the research and derivation](docs/shadow-research.md),
[asset matching](docs/asset-analysis.md), and
[reference comparison methodology](docs/reference-validation.md).

## Verification

Completed checks and retained evidence:

| Check | Result |
| --- | --- |
| Production build | `npm run build` passes |
| Source-color silhouette vs reference | **98.54% IoU**; branding excluded |
| Source-color RGB error on foreground union | **23.47 / 255 MAE** |
| Bake vs independent mesh BVH | 4,096 sampled camera rays; max depth error **0.00007973** |
| Hard-shadow CPU traversal vs mesh BVH | 4,096 rays × 4 sun directions; **97.83–99.46% agreement** |
| Interval validity | Ordered, disjoint, bounded; zero overflow; gap/finite-thickness regressions pass |
| Browser | No console/shader errors; presets, animation, pause, reset, toggle and comparison exercised |
| Responsive layout | Desktop and 390 px mobile checked; no mobile horizontal overflow |

The shader-equivalent CPU test is an independent visibility comparison against
continuous mesh rays; it is not a claim of GPU pixel readback validation. Browser
screenshots separately verify runtime output. The supplied Windows in-app browser
showed approximately 60 FPS at the fixed native render resolution; this is a local
observation, not a cross-device performance guarantee.

- [Reference and error comparison](verification/reference-comparison.png)
- [Blender geometry render](verification/blender-geometry.png)
- [Browser demo](verification/browser-desktop.jpg)
- [Four light directions compared](verification/light-comparison.jpg)
- [Opposite light direction](verification/browser-opposite.jpg)
- [Low sun](verification/browser-low-sun.jpg) / [high sun](verification/browser-high-sun.jpg)
- [Mobile layout](verification/browser-mobile.jpg)
- [Numerical results](verification/geometry-validation.json)
- [Reference metrics](verification/reference-metrics.json)

Capture routes include `/?capture=1&azimuth=-40&elevation=40`,
`/?capture=1&view=original`, and `/?capture=1&view=normals`. Captures use fixed
918 × 515 scene coordinates. `window.__shadowLab` also exposes `ready`,
`setState`, `render`, and `getState` for developer harnesses.

## Limits

This is a close composition reconstruction, not a pixel-identical copy. Street
widths/junctions, the terrace and some props are approximate; three top parapets
are brightened to match the reference. Painted windows retain their original
lighting, and the geometry simplifies facade detail. Silhouette IoU alone does
not measure these internal differences; the foreground color error is reported
alongside it.

The visibility field is fixed to this camera and geometry. Camera rotation,
moving buildings or off-image casters require a rebake or another representation.
At low sun angles the 192-step budget increases the projected stride, so thin
casters and silhouette contacts can be missed. Three cone samples give modest
softness, not a converged area-light solution. The documented ray biases trade
contact precision against self-shadow artifacts.

The supplied artwork and reference are credited to **Kenney**; the reference
marks them public domain. Original files in `assets/` and `sample.png` are intact.

