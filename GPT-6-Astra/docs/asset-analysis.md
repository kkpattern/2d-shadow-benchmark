# Sprite and reference reconstruction analysis

The supplied set contains 129 RGBA sprites. `sample.png` is 918 by 515 pixels, with a solid background RGB `(63,124,182)`. The reference is an assembled town scene, not a single sprite. No sprite contains the complete town, road network, trees, lamps, blue roof column, or the front access ramp.

## Projection and dimensions

The reference uses a 2:1 ground diamond: a nominal ground tile projects to 104 by 52 pixels. Most base sprites are 132 by 127 pixels, so the common working scale is `26/33 = 0.7878788`. Standalone storeys are 99 or 100 pixels wide and 85 pixels high; they become approximately 78 by 67 pixels. Their footprint is 0.75 of a ground tile, and a new storey adds approximately 27–28 screen pixels to the height.

An orthographic camera at 45 degrees azimuth and 30 degrees elevation produces this ground projection. A useful screen-space lattice is:

```
screen = (407,113) + u * (52,26) + v * (-52,26)
```

With one ground tile per world unit, vertical world displacement projects to approximately 63.687 pixels per unit. A normal storey is therefore roughly 0.43 world units high. Model the slab and sidewalk separately from buildings. The source base sprites bake a slab under the building, while standalone storeys do not.

For a base sprite, the building occupies approximately source x=16..116, y=0..85. Its lower silhouette is `y <= 84 - abs(x-66)/2`. This mask excludes the integral ground tile and is used by the intermediate composition script. The base's extracted building begins about 13.4 reference pixels to the right of the full sprite origin.

## Identified building assembly

All coordinates below are reference-image pixels at the common scale. Base coordinates refer to the full source PNG. Floor and cap coordinates refer to each PNG's native transparent bounds. Registration is accurate to approximately two pixels; floors can be regularized to a shared 27–28 pixel pitch in the reconstructed geometry.

| Building | Full base sprite and origin | Added storeys, bottom to top | Roof cap |
|---|---|---|---|
| Rear red, two floors | 036 at (200,118) | 049 at (213,90) | Original recessed roof |
| Left tan, four floors | 029 at (148,195) | 051 at (161,168), (161,141), (161,114) | Original recessed roof |
| Small brown cabin | 014 at (304,117) | None | 102 at (316,114) |
| Brown tower, four floors | 099 at (408,171) | 038 at (421,140), (421,113), (421,86) | 110 at (420,83) |
| Rear blue shop, two floors | 124 at (460,144) | 015 at (472,116) | 005 at (472,113) |
| Green-awning kiosk | 108 at (304,221) | None | Dark pitched 088 at (317,213) |
| Front red glass tower, three floors | 001 at (356,247) | 023 at (369,220), (369,193) | Original recessed roof |
| Right red shop, two floors | 034 at (512,221) | 052 at (525,194) | 128 at (524,191) |

`analysis/scene-sprites.json` contains these assemblies in back-to-front order, plus approximate coordinates for the procedural props. Within a building, draw the base first, then ascending storeys, then the cap. The glass tower hides the right side of the kiosk. The brown tower hides much of the blue shop. The tan tower hides the rear red building's left face. Geometry with real depth should reproduce this order naturally.

The blue shop upper-left face cannot be uniquely established because it is hidden. Sprite 015 is the best visible-facade match; sprite 031 is visually close on the exposed right face. The lower shop's small red awning is on the right-facing wall, consistent with 124.

## Verification performed

`analysis/contact-sheet.png` inventories every asset with its ID. `analysis/roofs.png` shows the cap variants at larger scale. `analysis/match_assets.py` performs masked FFT RGB least-squares matching; `analysis/local_match.py` restricts registration to the expected visible facade, excluding occluded halves. Naive full-image matching is unreliable because ground tiles and lower roofs are occluded.

`analysis/match_roofs.py` verifies cap variants in narrow neighborhoods. The best RGB root-mean-square errors over opaque cap pixels, in 8-bit channel units, are:

| Cap | Best matched ID | RMSE |
|---|---:|---:|
| Brown tower | 110 | 5.7 |
| Cabin | 102 | 10.0 |
| Blue shop | 005 | 11.6 |
| Right red shop | 128 | 8.5 |
| Kiosk | 088 | 9.6 |

Run `python analysis/compose_buildings.py` to regenerate `analysis/reconstructed-buildings.png`. That intermediate output uses only supplied sprites and a fresh solid background, and confirms that the building assemblies align closely with the reference. It intentionally omits procedural ground, road, and props. It does not contain any cropped or traced image content from the reference.

There is a real material difference: the reference makes the top parapet rims of the tan, rear red, and glass towers near-white. The matching native sprites use warm stone RGB around `(216,211,191)`. This explains some residual matching error even when shape and facade align. Intermediate comparison should not mistake that difference for a camera registration problem.

## Procedural elements and reference-only details

Use geometry for the tiled island, intersecting dark-gray roads, front ramp, white crosswalk, three blocky trees, thin gray streetlamps, right low red enclosure, and blue rooftop column. Their approximate image-space landmarks are recorded in the manifest. The low red enclosure spans about 107 screen pixels, wider than a standard 78-pixel building footprint; it should not be forced into a standard building module.

The Kenney/public-domain badge at lower left is reference branding. It is not scene geometry and should remain a reference-only element. Neither `sample.png` nor any analysis crop should be used as a runtime scene texture or ground layer.
