# Reference comparison

Run `python scripts/compare_reference.py` after regenerating `verification/reconstruction.png`. The script compares it with `sample.png` at their original 918 × 515 resolution and writes:

- `verification/reference-comparison.png`: reference and reconstruction, absolute RGB-error heatmap, and silhouette agreement.
- `verification/reference-metrics.json`: metric definitions, counts, background samples, and measured errors.

Only the lower-left branding region, `x < 305 and y > 420`, is excluded. There is no image alignment, rescaling, color normalization, or additional favorable crop. The reconstructed scene uses the supplied building sprites and procedural street/prop geometry; the reference image is an evaluation input only.

## Measured results

| Measure | Result |
|---|---:|
| Foreground silhouette intersection-over-union | **98.54%** |
| Foreground silhouette Dice | 99.26% |
| Reference foreground covered by reconstruction | 98.72% |
| Mean absolute RGB error on foreground union | **23.47 / 255** |
| Root-mean-square RGB error on foreground union | 38.49 / 255 |
| Mean absolute RGB error over all valid pixels | 7.13 / 255 |
| Valid image occupied by shared background | 69.63% |

The foreground mask uses maximum RGB-channel distance greater than 12 from each image's own top-left background sample. This suppresses weak antialiasing fringes. Silhouette counts are 134,606 reference pixels, 133,141 reconstructed pixels, and 132,887 shared pixels. The foreground union contains 134,860 pixels.

The exact sampled background is `(63,124,182)` in both the reference and the reconstruction. The global error is much lower than the foreground error because approximately 70% of scored pixels are matching uniform background. The **foreground-union error is the more informative composition/color measurement**; neither it nor silhouette overlap measures dynamic-shadow correctness.

## Visual findings and limits

The eight building groups are close in placement, footprint, storey count, and facade detail. This follows from using the identified native sprite modules and matching roof caps. Roof-rim whitening in `scripts/prepare_scene.py` moves the three bright-trim towers toward the reference, but some edge alignment and material differences remain.

The streets, terrace, retaining enclosure, ramp, paving, and props are approximations. The reconstructed road has different widths, corner curvature, branch endpoints, and junction shapes. The back-right road/sidewalk platform is present and supports the lamps. The terrace and red enclosure differ in height and shape, and the reference contains additional local shading that the painted procedural ground does not reproduce. These differences are prominent in the heatmap despite the high overall silhouette overlap.

The comparison is of the independently prepared source-color composition, before interactive dynamic lighting. It validates reference reconstruction only. Blender mesh/depth consistency and changing-light shadow behavior require their separate diagnostic and browser checks.
