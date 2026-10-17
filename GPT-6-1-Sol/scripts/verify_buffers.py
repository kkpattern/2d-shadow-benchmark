"""Validate numerical bake invariants and report honest reference error metrics."""
import json
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw

ROOT=Path(__file__).resolve().parents[1]
W,H=918,515
out=ROOT/'verification'
out.mkdir(exist_ok=True)
intervals=np.fromfile(ROOT/'generated/shadow-intervals.f32',dtype='<f4').reshape(4,H,W,4)
normals=np.fromfile(ROOT/'generated/shadow-normals.f32',dtype='<f4').reshape(H,W,4)
assert np.isfinite(intervals).all() and np.isfinite(normals).all(), 'Nonfinite bake values'
valid=intervals[:,:,:,3]>.5
assert np.all(intervals[:,:,:,0][valid]>=intervals[:,:,:,1][valid]), 'Back is ahead of front'
for k in range(3):
    both=valid[k]&valid[k+1]
    assert np.all(intervals[k,:,:,1][both] >= intervals[k+1,:,:,0][both]-.01), 'Intervals overlap or are unsorted'
nv=normals[:,:,3]>.5
assert np.all(np.abs(np.linalg.norm(normals[:,:,:3][nv],axis=-1)-1)<.03), 'Normals not unit length'
assert valid[0].sum()>70000, 'Suspiciously empty scene'

reference=np.asarray(Image.open(ROOT/'sample.png').convert('RGB')).astype(float)
recreated=np.asarray(Image.open(ROOT/'generated/albedo.png').convert('RGB')).astype(float)
scene=np.any(reference!=[63,124,182],axis=-1)
scene[415:,:]=False # Exclude attribution to avoid inflating the measured agreement.
scene[:60,:]=False
mae=np.abs(recreated-reference).mean(axis=-1)
report={'finite_buffers':True,'front_ge_back':True,'sorted_disjoint_layers':True,'unit_normals':True,
        'valid_pixels_per_layer':[int(v.sum()) for v in valid],
        'reference_comparison':{'method':'RGB MAE in source scene foreground; attribution excluded',
          'foreground_mae_0_255':round(float(mae[scene].mean()),3),
          'full_image_mae_0_255':round(float(mae.mean()),3),
          'exact_reproduction':False,
          'note':'Sprite positions matched to the source; ground/roads/props and closed depth proxies reconstructed approximately.'}}
if (out/'scene-default.png').exists():
    lit=np.asarray(Image.open(out/'scene-default.png').convert('RGB')).astype(float)
    unlit=np.asarray(Image.open(out/'scene-no-shadows.png').convert('RGB')).astype(float)
    opposite=np.asarray(Image.open(out/'scene-opposite-sun.png').convert('RGB')).astype(float)
    color_error=float(np.abs(unlit-recreated).mean())
    report['dynamic_render']={'shadow_changed_pixels':int((np.abs(lit-unlit).max(axis=-1)>3).sum()),'sun_changed_pixels':int((np.abs(lit-opposite).max(axis=-1)>3).sum()),'unshadowed_albedo_mae':round(color_error,6)}
    assert report['dynamic_render']['shadow_changed_pixels']>500,'Too few shadowed pixels'
    assert report['dynamic_render']['sun_changed_pixels']>500,'Sun direction does not materially change the scene'
    assert color_error<.25, 'Unshadowed GPU output does not preserve source art colors'
comparison=Image.new('RGB',(W*3,H+30),'#101f2b')
draw=ImageDraw.Draw(comparison)
heat=np.clip(np.abs(recreated-reference)*3,0,255).astype('uint8')
for i,(label,img) in enumerate([('REFERENCE',Image.fromarray(reference.astype('uint8'))),('RECONSTRUCTED ALBEDO',Image.fromarray(recreated.astype('uint8'))),('ABSOLUTE DIFFERENCE × 3',Image.fromarray(heat))]):
    draw.text((i*W+15,9),label,fill='#e7b674')
    comparison.paste(img,(i*W,30))
comparison.save(out/'reference-comparison.png')
(out/'buffer-report.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report,indent=2))
