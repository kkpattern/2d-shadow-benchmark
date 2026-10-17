We need to recreate the scene in `sample.png` using Three.js and add dynamic shadows.

Specific steps:

1. Conduct in-depth research on screen-space raymarching shadow rendering techniques, and analyze how to render shadows using information such as depth and thickness.
2. Based on the solution from Step 1, use Blender 5.2 to reconstruct the 2D models in the `assets` directory, and then generate the depth and other images required by the research in Step 1.
3. Use the results from Step 2 along with the `assets` to recreate the scene from `sample.png` in Three.js, and create a dynamic global light source to cast shadows for the scene.

Use screenshots and other comparison mechanisms to ensure that both your intermediate steps and final results meet expectations, and invoke subagents to complete tasks when necessary.

## Completion — 18 October 2026

- [x] Research and derivation: `docs/shadow-research.md`, with primary sources,
      depth/thickness equations, implementation choices and limitations.
- [x] Blender 5.2.2 reconstruction: `blender/city.blend`, reproducible scripts,
      Cycles preview, front/back depth, normals, thickness and eight disjoint
      depth intervals. The scene needs at most seven; no intervals are lost.
- [x] Three.js scene with interactive directional light, animated sun,
      screen-space raymarched shadows, debug views and reference comparison.
- [x] Saved intermediate/final screenshots and quantitative comparisons in
      `verification/`; independent Blender BVH checks pass. Foreground silhouette
      overlap is 98.54%; procedural streets and props remain approximate.

Run `npm run dev`. See `README.md` for rebuilding, verification and known limits.

