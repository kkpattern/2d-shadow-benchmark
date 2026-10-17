# 2D Screen Space Raymarching Shadow Benchmark

A benchmark for AI coding models: recreate a supplied 2D isometric scene in Three.js and add dynamic shadows using screen-space ray marching.

The task covers the full workflow:

1. Research screen-space shadow techniques, including how depth and thickness can represent occluders.
2. Use Blender 5.2 to reconstruct geometry for the supplied sprites and generate the required depth, thickness, and other maps.
3. Recreate the reference scene in Three.js, add a movable global light, and verify the results with screenshots and comparisons.

The complete instructions are in [template/TASK.md](template/TASK.md). Existing model runs are stored in separate directories in this repository.

## Try it yourself

The [template directory](template/) contains everything needed to start a new run:

- [TASK.md](template/TASK.md): the benchmark prompt.
- [sample.png](template/sample.png): the reference scene.
- [assets/](template/assets/): the source sprites.

Install Blender 5.2. Then copy the template into a fresh directory. Open it as your coding agent's workspace and ask it:

> finish @TASK.md

## Asset credits

The scene assets and reference artwork are by [Kenney](https://kenney.nl/), from [Isometric Tiles Buildings](https://kenney.nl/assets/isometric-tiles-buildings). The asset pack is released under [Creative Commons CC0](https://creativecommons.org/publicdomain/zero/1.0/).
