"""Masked RGB least-squares registration of supplied sprites against sample.png."""
from pathlib import Path
import json
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
scene = np.array(Image.open(ROOT/'sample.png').convert('RGB'),dtype=np.float32)
shape = (1024,1024)
sf = np.fft.rfft2(scene, s=shape, axes=(0,1))
ss = np.fft.rfft2((scene*scene).sum(axis=2),s=shape)
ids = list(range(57))+[85,92,93,99,100,101,106,107,108,109,113,114,115,116,117,122,123,124,125]
results=[]
for id in ids:
    im = Image.open(ROOT/f'assets/buildingTiles_{id:03d}.png').convert('RGBA')
    if im.width>120:
        im=im.crop((17,0,116,85))
        arr=np.array(im)
        yy,xx=np.mgrid[:85,:99]
        arr[:,:,3][yy>84-np.abs(xx-49)*.5]=0
        im=Image.fromarray(arr)
    best=[]
    for scale in [.78,.79,.80]:
        tile=im.resize((round(im.width*scale),round(im.height*scale)),Image.Resampling.LANCZOS)
        arr=np.array(tile,dtype=np.float32)
        mask=arr[:,:,3]>253
        for axis in [0,1]:
            mask &= np.roll(mask,1,axis)&np.roll(mask,-1,axis)
        # Roofs are occasionally covered by the next storey; find facade pixels.
        yy,xx=np.mgrid[:tile.height,:tile.width]
        mask &= yy>tile.height*.36+np.minimum(xx,tile.width-xx)*.4
        mask=mask.astype(np.float32)
        n=mask.sum()
        tf=np.fft.rfft2(arr[:,:,:3]*mask[:,:,None],s=shape,axes=(0,1))
        mf=np.fft.rfft2(mask,s=shape)
        cross=np.fft.irfft2((sf*np.conj(tf)).sum(axis=2),s=shape)
        energy=np.fft.irfft2(ss*np.conj(mf),s=shape)
        err=(energy-2*cross+((arr[:,:,:3]**2)*mask[:,:,None]).sum())/(n*3)
        err=err[:scene.shape[0]-tile.height+1,:scene.shape[1]-tile.width+1]
        y,x=np.unravel_index(np.argmin(err),err.shape)
        best.append(dict(id=id,scale=scale,x=int(x),y=int(y),width=tile.width,height=tile.height,rmse=float(np.sqrt(max(0,err[y,x])))))
    result=min(best,key=lambda d:d['rmse'])
    print(result,flush=True)
    results.append(result)
(ROOT/'analysis/facade-matches.json').write_text(json.dumps(results,indent=2))
