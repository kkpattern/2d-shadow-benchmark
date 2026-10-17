"""Independent Blender BVH checks of the baked field and shader traversal.

Run: blender --background blender/city.blend --python scripts/validate_bake.py
This does not modify the blend or source data. Results are recorded as JSON.
"""
from pathlib import Path
import json
import math
import numpy as np
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'public'/'generated'
m=json.loads((OUT/'scene.json').read_text())
W,H=m['width'],m['height']
R,U,F,C=[np.array(m['camera'][k]) for k in ('right','up','forward','origin')]
PPU=m['pixelsPerUnit']


def unpack(pair):
    q=pair[...,0].astype(np.uint16)*256+pair[...,1]
    return q.astype(np.float64)/65535*m['depthRange']+m['depthMin']


raw=[np.fromfile(OUT/f'interval{i}.bin',dtype=np.uint8).reshape(H,W,4) for i in range(m['layers'])]
front=np.stack([unpack(v[...,:2]) for v in raw],axis=-1)
back=np.stack([unpack(v[...,2:]) for v in raw],axis=-1)
valid=back>front
assert m['overflowPixels']==0
assert np.all(~valid[...,1:]|valid[...,:-1]), 'Empty layer precedes occupied layer'
assert np.all(~valid[...,1:]|(front[...,1:]>=back[...,:-1])), 'Overlapping intervals were not merged'
assert np.all(front>=m['depthMin']) and np.all(back<=m['depthMin']+m['depthRange'])
data=np.load(ROOT/'verification'/'bake-data.npz')
normals=data['normals'].astype(float)/255*2-1
normals/=np.maximum(np.linalg.norm(normals,axis=-1,keepdims=True),1e-8)
assert np.isfinite(normals).all()

# Build a completely independent BVH from the saved Blender meshes. This uses
# continuous triangle intersection, not the bake's pixel rasterizer.
vertices=[]; triangles=[]
for obj in bpy.context.scene.objects:
    if obj.type!='MESH' or obj.get('bake_exclude'): continue
    mesh=obj.data
    mesh.calc_loop_triangles()
    first=len(vertices)
    vertices.extend([obj.matrix_world@v.co for v in mesh.vertices])
    triangles.extend([[first+i for i in t.vertices] for t in mesh.loop_triangles])
bvh=BVHTree.FromPolygons(vertices,triangles,all_triangles=True,epsilon=0.0)

ys,xs=np.where(valid[...,0])
rng=np.random.default_rng(20261018)
indices=rng.choice(len(xs),min(4096,len(xs)),replace=False)
xs,ys=xs[indices],ys[indices]
depth=front[ys,xs,0]
uv=np.column_stack(((xs+.5)/W,1-(ys+.5)/H))
plane=(uv-.5)*[W,H]/PPU
points=C+plane[:,:1]*R+plane[:,1:]*U+depth[:,None]*F
ns=normals[ys,xs]
reprojection=np.column_stack((.5+(points-C)@R*PPU/W,.5+(points-C)@U*PPU/H))
assert np.max(abs(reprojection-uv))<1e-12
depth_errors=[]
for p,d in zip(points,depth):
    ray_start=p-F*d
    result=bvh.ray_cast(Vector(ray_start),Vector(F),100)
    assert result[0] is not None
    depth_errors.append(abs(result[3]-d))
assert max(depth_errors)<m['depthQuantum']*.6+1e-5, max(depth_errors)


def texture_trace(L):
    offset=ns*.012+L*.018
    start=points+offset
    pos=uv+np.column_stack((offset@R,offset@U))*PPU/[W,H]
    d=depth+offset@F
    distance=np.maximum(0,(m['maxHeight']-start[:,2])/max(L[2],.001))
    projected=np.array([L@R,L@U])*PPU
    steps=np.maximum(.7/max(np.linalg.norm(projected),1),distance/192)
    delta=steps*(L@F)
    half=abs(delta)*.48
    hit=np.zeros(len(xs),bool)
    active=distance>0
    for i in range(192):
        active&=((i+1)*steps<=distance)&~hit
        pos+=steps[:,None]*projected/[W,H]
        d+=delta
        active&=(pos[:,0]>0)&(pos[:,0]<1)&(pos[:,1]>0)&(pos[:,1]<1)
        active&=(d>=m['depthMin'])&(d<=m['depthMin']+m['depthRange'])
        if not np.any(active): break
        ids=np.where(active)[0]
        ix=np.floor(pos[ids,0]*W).astype(int)
        iy=np.floor((1-pos[ids,1])*H).astype(int)
        f,b=front[iy,ix],back[iy,ix]
        tolerance=np.minimum(.006,(b-f)*.2)
        overlaps=(b>f)&((d[ids]+half[ids])[:,None]>f+tolerance)&((d[ids]-half[ids])[:,None]<b-tolerance)
        hit[ids]|=overlaps.any(axis=-1)
    return hit,start,distance


results=[]
for azimuth,elevation in [(-40,40),(140,40),(-70,23),(-10,78)]:
    az,el=map(math.radians,(azimuth,elevation))
    L=np.array([math.cos(az)*math.cos(el),math.sin(az)*math.cos(el),math.sin(el)])
    traced,start,distance=texture_trace(L)
    truth=[]
    for p,d in zip(start,distance):
        result=bvh.ray_cast(Vector(p),Vector(L),max(0,d))
        truth.append(result[0] is not None)
    truth=np.array(truth)
    errors=traced!=truth
    ground=ns[:,2]>.99
    result=dict(azimuth=azimuth,elevation=elevation,samples=len(xs),
      agreement=float((~errors).mean()),falseShadow=int((traced&~truth).sum()),
      missedShadow=int((~traced&truth).sum()),
      groundSamples=int(ground.sum()),groundAgreement=float((~errors[ground]).mean()),
      groundTruthShadowPixels=int(truth[ground].sum()),
      note='CPU equivalent of hard-shadow shader vs independent Blender BVH; includes silhouette/normal quantization errors.')
    results.append(result)
    assert result['agreement']>.90, result

# A simple interval-only regression guards the central thickness distinction.
def overlaps(ray, intervals):
    return any(max(ray[0],a)<min(ray[1],b) for a,b in intervals)
assert not overlaps((2.2,2.8),[(1,2),(3,4)])
assert overlaps((2.2,2.8),[(1,4)]) # Incorrect outer envelope fills the air gap.
assert overlaps((2.9,3.1),[(1,2),(3,4)]) # Segment straddles a thin entry boundary.
assert not overlaps((4.1,4.5),[(1,2),(3,4)]) # Finite back depth lets light pass behind.

report=dict(blenderVersion=bpy.app.version_string,passed=True,
  intervalChecks='Ordered, disjoint, contiguous valid layers; no overflow; bounded depth; finite normalized normals.',
  independentBvhDepthSamples=len(depth_errors),maxDepthError=max(depth_errors),
  quantizationUnit=m['depthQuantum'],maxReprojectionError=float(np.max(abs(reprojection-uv))),
  syntheticGapTests=4,shadowComparisons=results)
(ROOT/'verification'/'geometry-validation.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report,indent=2))
