"""Compare the independent reconstruction with its reference, excluding only branding.

Run: python scripts/compare_reference.py
Outputs a reproducible figure and JSON; no scene or runtime files are modified.
"""
from pathlib import Path
import json
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'verification'
REFERENCE = ROOT / 'sample.png'
RECONSTRUCTION = OUT / 'reconstruction.png'


def font(size, bold=False):
    for name in ('segoeuib.ttf' if bold else 'segoeui.ttf', 'arial.ttf'):
        path = Path('C:/Windows/Fonts') / name
        if path.exists():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default(size=size)


def main():
    ref_image = Image.open(REFERENCE).convert('RGB')
    ours_image = Image.open(RECONSTRUCTION).convert('RGB')
    if ref_image.size != ours_image.size:
        raise ValueError(f'Image dimensions differ: {ref_image.size} vs {ours_image.size}')
    ref = np.asarray(ref_image, dtype=np.int16)
    ours = np.asarray(ours_image, dtype=np.int16)
    h, w = ref.shape[:2]
    yy, xx = np.mgrid[:h, :w]
    excluded = (xx < 305) & (yy > 420)
    valid = ~excluded
    ref_bg = ref[0, 0]
    ours_bg = ours[0, 0]
    # A small tolerance keeps antialiasing fringes from defining the silhouette.
    threshold = 12
    ref_fg = (np.max(np.abs(ref-ref_bg), axis=2) > threshold) & valid
    ours_fg = (np.max(np.abs(ours-ours_bg), axis=2) > threshold) & valid
    union = ref_fg | ours_fg
    intersection = ref_fg & ours_fg
    reference_only = ref_fg & ~ours_fg
    reconstruction_only = ours_fg & ~ref_fg
    background = valid & ~union
    error = np.abs(ref-ours).astype(np.float64)
    pixel_error = error.mean(axis=2)

    def pixel_stats(mask):
        values = error[mask]
        return {
            'pixel_count': int(mask.sum()),
            'mae_rgb_8bit': float(values.mean()),
            'rmse_rgb_8bit': float(np.sqrt(np.mean(values**2))),
            'mean_pixel_error_p50': float(np.percentile(pixel_error[mask], 50)),
            'mean_pixel_error_p95': float(np.percentile(pixel_error[mask], 95)),
        }

    metrics = {
        'reference': 'sample.png',
        'reconstruction': 'verification/reconstruction.png',
        'image_size': [w, h],
        'comparison_space': '8-bit sRGB image channels; no color normalization, registration, or rescaling',
        'excluded_region': {'condition': 'x < 305 and y > 420', 'pixel_count': int(excluded.sum()), 'reason': 'Reference Kenney/public-domain branding'},
        'background': {
            'sampling': 'Exact top-left pixel [0,0] from each image',
            'reference_rgb': ref_bg.tolist(),
            'reconstruction_rgb': ours_bg.tolist(),
            'absolute_channel_difference': np.abs(ref_bg-ours_bg).tolist(),
        },
        'foreground_definition': {
            'criterion': 'Maximum absolute RGB channel distance from each image\'s own sampled background > 12',
            'threshold_8bit': threshold,
            'purpose': 'Suppress antialiasing fringe while preserving all scene content; independent backgrounds avoid labeling the color mismatch as foreground',
        },
        'silhouette': {
            'reference_pixels': int(ref_fg.sum()),
            'reconstruction_pixels': int(ours_fg.sum()),
            'intersection_pixels': int(intersection.sum()),
            'union_pixels': int(union.sum()),
            'reference_only_pixels': int(reference_only.sum()),
            'reconstruction_only_pixels': int(reconstruction_only.sum()),
            'intersection_over_union': float(intersection.sum()/union.sum()),
            'dice': float(2*intersection.sum()/(ref_fg.sum()+ours_fg.sum())),
            'reconstruction_precision': float(intersection.sum()/ours_fg.sum()),
            'reference_recall': float(intersection.sum()/ref_fg.sum()),
        },
        'scene_union': pixel_stats(union),
        'scene_intersection': pixel_stats(intersection),
        'global_excluding_branding': pixel_stats(valid),
        'shared_background': pixel_stats(background),
        'shared_background_fraction_of_valid_image': float(background.sum()/valid.sum()),
        'interpretation': 'Scene-union MAE is the primary color/composition error. The global MAE is strongly diluted by the large shared solid background. Silhouette overlap does not validate internal road layout or rendering/shadow correctness.',
    }
    OUT.mkdir(exist_ok=True)
    (OUT/'reference-metrics.json').write_text(json.dumps(metrics, indent=2)+'\n', encoding='utf-8')

    # Absolute-error heatmap, explicitly mapped in 8-bit RGB-error units.
    levels = np.array([0, 5, 15, 30, 60, 100], dtype=float)
    colors = np.array([[16,24,40],[33,66,89],[28,129,150],[230,195,73],[227,112,41],[217,47,50]], dtype=float)
    heat = np.empty((h,w,3), dtype=np.uint8)
    for channel in range(3):
        heat[:,:,channel] = np.interp(pixel_error,levels,colors[:,channel]).astype(np.uint8)
    heat[excluded] = [48,52,63]
    heat_image = Image.fromarray(heat)
    silhouette = np.empty((h,w,3),dtype=np.uint8)
    silhouette[:] = [16,24,40]
    silhouette[intersection] = [194,207,218]
    silhouette[reference_only] = [227,76,151]
    silhouette[reconstruction_only] = [33,201,214]
    silhouette[excluded] = [48,52,63]
    silhouette_image = Image.fromarray(silhouette)

    margin, gap = 24, 24
    image_y1, image_y2 = 110, 703
    fig = Image.new('RGB',(2*w+2*margin+gap, h+image_y2+97),(242,245,249))
    draw = ImageDraw.Draw(fig)
    draw.text((margin,17),'Reference reconstruction — measured visual comparison',font=font(31,True),fill=(22,36,53))
    draw.text((margin,60),f'Same {w} × {h} pixels · no alignment or color correction · bottom-left branding is the only excluded region',font=font(20),fill=(76,88,102))
    right = margin+w+gap
    panels = [
        (ref_image, margin, image_y1, 'REFERENCE  ·  sample.png'),
        (ours_image, right, image_y1, 'RECONSTRUCTION  ·  independent assets + geometry'),
        (heat_image, margin, image_y2, 'ABSOLUTE RGB ERROR  ·  dark blue 0 → red 100+'),
        (silhouette_image, right, image_y2, 'SILHOUETTE  ·  shared / reference only / reconstruction only'),
    ]
    for img,x,y,label in panels:
        draw.text((x,y-29),label,font=font(19,True),fill=(37,52,70))
        fig.paste(img,(x,y))
        draw.rectangle((x,y,x+w-1,y+h-1),outline=(192,203,214),width=1)
        if y==image_y1:
            draw.rectangle((x,y+421,x+304,y+h-1),outline=(238,188,82),width=2)
    stats_y=image_y1+h+12
    draw.text((margin,stats_y),f'Background RGB: reference {tuple(map(int,ref_bg))}  |  reconstructed {tuple(map(int,ours_bg))}',font=font(19),fill=(65,80,98))
    draw.text((right,stats_y),f'Foreground IoU {metrics["silhouette"]["intersection_over_union"]:.2%}  |  scene-union MAE {metrics["scene_union"]["mae_rgb_8bit"]:.2f}/255',font=font(19,True),fill=(29,55,76))
    footer=image_y2+h+12
    for value in [0,5,15,30,60,100]:
        offset=int(value/100*350)
        rgb=tuple(int(np.interp(value,levels,colors[:,c])) for c in range(3))
        draw.rectangle((margin+offset,footer,margin+offset+42,footer+12),fill=rgb)
        draw.text((margin+offset,footer+16),str(value),font=font(15),fill=(65,80,98))
    draw.text((margin+435,footer),f'Global MAE {metrics["global_excluding_branding"]["mae_rgb_8bit"]:.2f}/255',font=font(18),fill=(65,80,98))
    draw.text((margin+435,footer+25),f'{metrics["shared_background_fraction_of_valid_image"]:.1%} of scored pixels are shared background',font=font(17),fill=(65,80,98))
    for i,(rgb,label) in enumerate([((194,207,218),'Shared'),((227,76,151),'Reference only'),((33,201,214),'Reconstruction only')]):
        x=right+i*275
        draw.rectangle((x,footer,x+18,footer+18),fill=rgb)
        draw.text((x+27,footer-2),label,font=font(17),fill=(65,80,98))
    draw.text((right,footer+31),'Road shape, terrace and prop geometry remain approximations.',font=font(19),fill=(65,80,98))
    fig.save(OUT/'reference-comparison.png')
    print(json.dumps(metrics,indent=2))


if __name__ == '__main__':
    main()
