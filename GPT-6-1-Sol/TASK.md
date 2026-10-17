We need to recreate the scene in `sample.png` using Three.js and add dynamic shadows.

Specific steps:

1. Conduct in-depth research on screen-space raymarching shadow rendering techniques, and analyze how to render shadows using information such as depth and thickness.
2. Based on the solution from Step 1, use Blender 5.2 to reconstruct the 2D models in the `assets` directory, and then generate the depth and other images required by the research in Step 1.
3. Use the results from Step 2 along with the `assets` to recreate the scene from `sample.png` in Three.js, and create a dynamic global light source to cast shadows for the scene.

Use screenshots and other comparison mechanisms to ensure that both your intermediate steps and final results meet expectations, and invoke subagents to complete tasks when necessary.

---

Completed 2026-10-18:

- [x] Primary-source research and implementation audit: `docs/SHADOW_RESEARCH.md`.
- [x] Blender 5.2 reconstruction, editable `.blend`, reusable asset proxies, depth/thickness/normal/validity data and visual QA: `generated/`.
- [x] Local Three.js scene with movable global sunlight, dynamic layered screen-space shadows, diagnostic views and reference comparison.
- [x] Browser interaction checks, production build, numerical validation and comparison screenshots: `verification/`.

Run and rebuild instructions, measured comparison errors and rendering limitations are in `README.md`.

