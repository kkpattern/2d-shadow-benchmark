"""Reproducible sprite catalog, masked matching, and reference comparison.

Dependencies: Pillow and NumPy. Run from any directory:
    python scripts/analyze_assets.py
    python scripts/analyze_assets.py --match

The optional matcher correlates only opaque lower-wall pixels, avoiding roofs
that the reference recolors and hiding upper-story occlusions. It uses NumPy FFT
correlation and never copies scene pixels into the runtime texture.
"""
from pathlib import Path
import argparse,json
import numpy as np
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'generated'

def masked_match(reference,asset,scale):
    source=Image.open(asset).convert('RGBA')
    source=source.resize((round(source.width*scale),round(source.height*scale)),Image.Resampling.LANCZOS)
    a=np.asarray(source).astype(np.float32)
    rgb=a[:,:,:3]
    mask=(a[:,:,3]>250).astype(np.float32)
    mask[:round(52*scale)]=0
    mask[round(84*scale):]=0
    h,w=mask.shape;H,W=reference.shape[:2]
    shape=(2**int(np.ceil(np.log2(H+h))),2**int(np.ceil(np.log2(W+w))))
    fm=np.fft.rfft2(mask[::-1,::-1],shape)
    score=np.zeros((H-h+1,W-w+1))
    for c in range(3):
        fi=np.fft.rfft2(reference[:,:,c],shape)
        fi2=np.fft.rfft2(reference[:,:,c]**2,shape)
        ft=np.fft.rfft2((rgb[:,:,c]*mask)[::-1,::-1],shape)
        score+=np.fft.irfft2(fi2*fm-2*fi*ft,shape)[h-1:H,w-1:W]
    score+=(rgb*rgb*mask[:,:,None]).sum()
    score/=mask.sum()*3
    peaks=[]
    for _ in range(3):
        y,x=np.unravel_index(np.argmin(score),score.shape)
        peaks.append({'x':int(x),'y':int(y),'meanSquaredRGBError':round(float(score[y,x]),3)})
        score[max(0,y-10):y+11,max(0,x-10):x+11]=1e12
    return peaks

def main():
    args=argparse.ArgumentParser();args.add_argument('--match',action='store_true');args=args.parse_args()
    files=sorted((ROOT/'assets').glob('*.png'))
    sheet=Image.new('RGB',(1400,2080),(63,124,182));draw=ImageDraw.Draw(sheet)
    catalog=[]
    for i,p in enumerate(files):
        a=Image.open(p).convert('RGBA');x=(i%10)*140;y=(i//10)*160
        sheet.paste(a,(x,y+20),a);draw.text((x+5,y+3),p.stem[-3:],fill='white')
        catalog.append({'id':int(p.stem[-3:]),'size':list(a.size),'alphaBounds':list(a.getbbox())})
    sheet.save(OUT/'contact-sheet.png')
    layout=json.loads((OUT/'scene-layout.json').read_text())
    ref=np.asarray(Image.open(ROOT/'sample.png').convert('RGB')).astype(np.float32)
    result=np.asarray(Image.open(OUT/'albedo.png').convert('RGB')).astype(np.float32)
    error=np.abs(ref-result)
    fg=np.max(np.abs(ref-[63,124,182]),axis=2)>5
    fg[420:493,27:304]=False
    report={'assetCount':len(files),'placedSpriteCount':len(layout['sprites']),
      'uniquePlacedAssets':sorted(set(s['id'] for s in layout['sprites'])),
      'nativeToScreenScale':layout['scale'],'nativeFloorHeight':35,
      'screenFloorHeight':35*layout['scale'],
      'metrics':{'rgbMAE0to255':round(float(error.mean()),4),
       'foregroundRGBMAE0to255':round(float(error[fg].mean()),4),
       'rgbRMSE0to255':round(float(np.sqrt(np.mean((ref-result)**2))),4),
       'foregroundDefinition':'Reference differs from blue by >5 in any channel; isolated credit rectangle excluded.'},
      'limitations':['Original lighting and local ground gradients are approximated.',
       'Subpixel sprite positions, resampling, source roof variants, decorative contours and paving seams are not exact.',
       'The scene texture uses source assets and vector scenery; only the isolated artist credit is taken from the reference.'],
      'assetCatalog':catalog}
    if args.match:
        report['maskedStoryMatches']={str(i):masked_match(ref,ROOT/f'assets/buildingTiles_{i:03d}.png',layout['scale']) for i in [38,51,23,52]}
    (OUT/'scene-analysis.json').write_text(json.dumps(report,indent=2))
    print(json.dumps({k:v for k,v in report.items() if k!='assetCatalog'},indent=2))
if __name__=='__main__':main()
