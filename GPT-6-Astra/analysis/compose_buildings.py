"""Render an intermediate asset-only reconstruction for visual comparison."""
from pathlib import Path
import json
import numpy as np
from PIL import Image
R=Path(__file__).resolve().parents[1]
spec=json.loads((R/'analysis/scene-sprites.json').read_text())
canvas=Image.new('RGBA',tuple(spec['referenceSize']),tuple(spec['backgroundRGB'])+(255,))
for b in spec['buildings']:
 for layer in [b['base']]+b['storeys']+([b['cap']] if b.get('cap') else []):
  im=Image.open(R/f"assets/buildingTiles_{layer['id']:03}.png").convert('RGBA')
  if layer is b['base']:
   a=np.array(im)
   yy,xx=np.mgrid[:im.height,:im.width]
   # Extract building silhouette and discard the sprite's integral ground tile.
   m=(xx>=16)&(xx<=116)&(yy<=84-np.abs(xx-66)*.5)
   a[:,:,3][~m]=0
   im=Image.fromarray(a)
  im=im.resize((round(im.width*spec['scale']),round(im.height*spec['scale'])),Image.Resampling.LANCZOS)
  canvas.alpha_composite(im,(round(layer['x']),round(layer['y'])))
canvas.convert('RGB').save(R/'analysis/reconstructed-buildings.png')
