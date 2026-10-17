from pathlib import Path
import numpy as np
from PIL import Image
import json
R=Path(__file__).resolve().parents[1]
S=np.array(Image.open(R/'sample.png').convert('RGB'),dtype=float)
ids=[5,6,13,79,86,87,94,95,102,103,110,111,118,119,120,121,126,127,128]
groups={'brown':(ids,421,84),'cabin':(ids,317,115),'blue':(ids,473,114),'right-red':(ids,525,193),'kiosk':([81,88,89,96,97,104,105,112],317,213)}
out={}
for name,(candidates,cx,cy) in groups.items():
 rows=[]
 for id in candidates:
  orig=Image.open(R/f'assets/buildingTiles_{id:03}.png').convert('RGBA')
  scale=26/33
  im=orig.resize((round(orig.width*scale),round(orig.height*scale)),Image.Resampling.LANCZOS)
  a=np.array(im,dtype=float);h,w=a.shape[:2]; yy,xx=np.mgrid[:h,:w]
  m=(a[:,:,3]>253)
  if name=='blue': m &= xx>28
  if name=='kiosk': m &= xx<48
  for y in range(cy-4,cy+5):
   for x in range(cx-3,cx+4):
    diff=(S[y:y+h,x:x+w]-a[:,:,:3])[m]
    err=float(np.sqrt((diff*diff).mean()))
    rows.append(dict(id=id,x=x,y=y,scale=scale,rmse=err))
 out[name]=sorted(rows,key=lambda r:r['rmse'])[:5]
 print(name,out[name][:2])
(R/'analysis/roof-matches.json').write_text(json.dumps(out,indent=2))
