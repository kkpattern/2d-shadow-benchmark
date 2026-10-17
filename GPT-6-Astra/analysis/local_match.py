from pathlib import Path
import numpy as np
from PIL import Image
import json
R=Path(__file__).resolve().parents[1]
S=np.array(Image.open(R/'sample.png').convert('RGB'),dtype=float)
groups={
  'rear-blue-upper':([7,8,15,24,31],473,114),
  'rear-blue-base':([3,93,101,116,117,124,125],473,142),
  'rear-red-upper':([45,49,52,54],213,91),
  'rear-red-base':([30,36],213,119),
  'brown-base':([99,113],421,169),
  'glass-upper':([16,23],369,193),
  'glass-base':([1,9,10,17,123],369,247),
  'kiosk-base':([20,100,108],317,222),
  'cabin':([14,32],317,116),
  'right-red-upper':([45,49,52,54],524,193),
  'right-red-base':([18,26,34,41],524,221),
}
out={}
for name,(ids,cx,cy) in groups.items():
 rows=[]
 for id in ids:
  orig=Image.open(R/f'assets/buildingTiles_{id:03}.png').convert('RGBA')
  base=orig.width>120
  if base:
   orig=orig.crop((17,0,116,85))
   p=np.array(orig); yy,xx=np.mgrid[:85,:99]
   p[:,:,3][yy>84-np.abs(xx-49)*.5]=0
   orig=Image.fromarray(p)
  for scale in [.7878787878,.79]:
   im=orig.resize((round(orig.width*scale),round(orig.height*scale)),Image.Resampling.LANCZOS)
   a=np.array(im,dtype=float);h,w=a.shape[:2]; yy,xx=np.mgrid[:h,:w]
   m=(a[:,:,3]>253)&(yy>h*.37+np.minimum(xx,w-xx)*.4)
   if name.startswith('rear-blue'): m &= xx>33
   if name.startswith('rear-red'): m &= xx>40
   if name=='brown-base': m &= yy>h*.68
   if name=='kiosk-base': m &= xx<45
   for y in range(cy-3,cy+4):
    for x in range(cx-3,cx+4):
     diff=(S[y:y+h,x:x+w]-a[:,:,:3])[m]
     err=float(np.sqrt((diff*diff).mean()))
     rows.append(dict(id=id,x=x,y=y,scale=scale,rmse=err,base=base,fullSpriteX=x-17*scale if base else x))
 out[name]=sorted(rows,key=lambda r:r['rmse'])[:3]
 print(name,out[name][0])
(R/'analysis/local-matches.json').write_text(json.dumps(out,indent=2))
