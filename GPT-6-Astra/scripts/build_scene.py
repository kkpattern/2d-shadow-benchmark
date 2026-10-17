"""Run with Blender 5.2: blender --background --python scripts/build_scene.py.

Creates the editable .blend, renders an independent geometry preview, then
rasterizes the actual evaluated mesh triangles into disjoint depth intervals.
No depth is inferred from the color image and no reference pixels are sampled.
"""
import bpy
import json
import math
import sys
import time
from pathlib import Path
import numpy as np
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'public'/'generated'
layout = json.loads((OUT/'layout.json').read_text(encoding='utf8'))
W,H = layout['width'],layout['height']
PPU = layout['pixelsPerUnit']
R,U,F = [np.array(layout['camera'][key]) for key in ('right','up','forward')]
ORIGIN = np.array(layout['camera']['origin'])


def png(name, array):
    """Write PNG directly: PNG alpha must not undergo Blender color management."""
    import struct, zlib
    h,w,c = array.shape
    assert c in (3,4)
    data = b''.join(b'\0'+array[y].tobytes() for y in range(h))
    def chunk(kind, value):
        return struct.pack('>I',len(value))+kind+value+struct.pack('>I',zlib.crc32(kind+value)&0xffffffff)
    header=struct.pack('>IIBBBBB',w,h,8,6 if c==4 else 2,0,0,0)
    (OUT/name).write_bytes(b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',header)+chunk(b'IDAT',zlib.compress(data,9))+chunk(b'IEND',b''))


def create_scene():
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    scene=bpy.context.scene
    scene.render.resolution_x=W
    scene.render.resolution_y=H
    scene.render.resolution_percentage=100
    scene.render.image_settings.file_format='PNG'
    scene.render.film_transparent=False
    collections={}
    materials={}
    for desc in layout['solids']:
        category=desc['category']
        if category not in collections:
            col=bpy.data.collections.new(category.title())
            scene.collection.children.link(col)
            collections[category]=col
        mesh=bpy.data.meshes.new(desc['name'])
        mesh.from_pydata(desc['vertices'],[],desc['faces'])
        mesh.update()
        obj=bpy.data.objects.new(desc['name'],mesh)
        collections[category].objects.link(obj)
        color=tuple(desc['color'])
        if color not in materials:
            mat=bpy.data.materials.new('Paint '+str(color))
            # Standard input colors are linear; convert the measured sRGB paint.
            rgb=[v/255 for v in color]
            linear=[v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4 for v in rgb]
            mat.diffuse_color=(*linear,1)
            mat.use_nodes=True
            mat.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value=(*linear,1)
            mat.node_tree.nodes['Principled BSDF'].inputs['Roughness'].default_value=.8
            materials[color]=mat
        obj.data.materials.append(materials[color])
        obj['source']='Reconstructed solid proxy from supplied Kenney tiles'
    camera_data=bpy.data.cameras.new('Reference orthographic camera')
    camera=bpy.data.objects.new('Reference orthographic camera',camera_data)
    scene.collection.objects.link(camera)
    camera.location=ORIGIN.tolist()
    camera.rotation_euler=Vector(F.tolist()).to_track_quat('-Z','Y').to_euler()
    camera_data.type='ORTHO'
    # Blender ortho_scale spans the image width for a landscape frame.
    camera_data.ortho_scale=W/PPU
    camera_data.clip_start=.1
    camera_data.clip_end=100
    scene.camera=camera
    # A transparent orthographic decal reproduces the procedural street layout
    # in the editable Blender scene. Geometry data uses the paving beneath it.
    mesh=bpy.data.meshes.new('Street markings decal')
    corners=[]
    for sx,sy in [(0,0),(0,H),(W,H),(W,0)]:
        # Intersect the camera ray with the horizontal z=0.001 plane.
        start=ORIGIN+R*((sx-W/2)/PPU)+U*((H/2-sy)/PPU)
        corners.append((start+F*((.001-start[2])/F[2])).tolist())
    mesh.from_pydata(corners,[],[[0,1,2,3]])
    mesh.uv_layers.new(name='UVMap')
    for loop,uv in zip(mesh.uv_layers.active.data,[(0,1),(0,0),(1,0),(1,1)]): loop.uv=uv
    decal=bpy.data.objects.new('Street markings (color only)',mesh)
    scene.collection.objects.link(decal)
    decal['bake_exclude']=True
    mat=bpy.data.materials.new('Asphalt decal')
    mat.use_nodes=True
    tree=mat.node_tree
    shader=tree.nodes.get('Principled BSDF')
    texture=tree.nodes.new('ShaderNodeTexImage')
    texture.image=bpy.data.images.load(str(OUT/'roads.png'))
    texture.image.pack()
    tree.links.new(texture.outputs['Color'],shader.inputs['Base Color'])
    tree.links.new(texture.outputs['Alpha'],shader.inputs['Alpha'])
    shader.inputs['Roughness'].default_value=1
    decal.data.materials.append(mat)
    scene.world.color=(.2,.2,.2)
    scene.world.use_nodes=True
    scene.world.node_tree.nodes['Background'].inputs['Color'].default_value=(.14,.25,.42,1)
    scene.world.node_tree.nodes['Background'].inputs['Strength'].default_value=.8
    sun_data=bpy.data.lights.new('Global sun','SUN')
    sun_data.energy=2.3
    sun_data.angle=math.radians(2)
    sun=bpy.data.objects.new('Global sun',sun_data)
    scene.collection.objects.link(sun)
    sun.rotation_euler=(math.radians(25),math.radians(-25),math.radians(-35))
    scene.render.engine='CYCLES'
    scene.cycles.samples=24
    scene.cycles.use_denoising=True
    scene.view_settings.view_transform='Standard'
    scene.view_settings.look='None'
    scene['pipeline']='Eight disjoint front/back depth intervals from closed mesh rasterization'
    scene['pixels_per_unit']=PPU
    scene['source_assets']='../assets/buildingTiles_*.png'
    # Make the saved file useful when opened interactively.
    for area in bpy.context.screen.areas:
        if area.type=='VIEW_3D':
            area.spaces.active.region_3d.view_perspective='CAMERA'
    bpy.ops.wm.save_as_mainfile(filepath=str(ROOT/'blender'/'city.blend'))
    scene.render.filepath=str(ROOT/'verification'/'blender-geometry.png')
    bpy.ops.render.render(write_still=True)
    return scene


def bake(scene):
    started=time.perf_counter()
    # Extra capacity is used to audit complexity before exporting eight layers.
    CAPACITY=12
    fronts=np.full((H,W,CAPACITY),np.inf,np.float32)
    backs=np.full((H,W,CAPACITY),-np.inf,np.float32)
    visible_depth=np.full((H,W),np.inf,np.float32)
    normals=np.zeros((H,W,3),np.float32)
    # Rasterize every convex component separately. Meshes are deliberately
    # decomposed into convex pieces so min/max are entry/exit, not a hull over air.
    for obj in [o for o in scene.objects if o.type=='MESH' and not o.get('bake_exclude')]:
        mesh=obj.data
        mesh.calc_loop_triangles()
        vertices=np.array([obj.matrix_world@v.co for v in mesh.vertices],dtype=np.float64)
        screen=np.column_stack((W/2+vertices@R*PPU,H/2-vertices@U*PPU,(vertices-ORIGIN)@F))
        x0=max(0,int(math.floor(screen[:,0].min())))
        x1=min(W,int(math.ceil(screen[:,0].max())))
        y0=max(0,int(math.floor(screen[:,1].min())))
        y1=min(H,int(math.ceil(screen[:,1].max())))
        if x1<=x0 or y1<=y0: continue
        yy,xx=np.mgrid[y0:y1,x0:x1].astype(np.float64)
        xx+=.5; yy+=.5
        entry=np.full(xx.shape,np.inf,np.float32)
        leave=np.full(xx.shape,-np.inf,np.float32)
        face_normal=np.zeros((*xx.shape,3),np.float32)
        for tri in mesh.loop_triangles:
            ids=list(tri.vertices)
            a,b,c=screen[ids]
            denom=(b[1]-c[1])*(a[0]-c[0])+(c[0]-b[0])*(a[1]-c[1])
            if abs(denom)<1e-9: continue
            wa=((b[1]-c[1])*(xx-c[0])+(c[0]-b[0])*(yy-c[1]))/denom
            wb=((c[1]-a[1])*(xx-c[0])+(a[0]-c[0])*(yy-c[1]))/denom
            wc=1-wa-wb
            mask=(wa>=-1e-7)&(wb>=-1e-7)&(wc>=-1e-7)
            d=wa*a[2]+wb*b[2]+wc*c[2]
            nearer=mask&(d<entry)
            n=np.cross(vertices[ids[1]]-vertices[ids[0]],vertices[ids[2]]-vertices[ids[0]])
            n/=np.linalg.norm(n)
            # Some authored wedge faces have opposite winding; the first
            # intersection always has an outward camera-facing normal.
            if n@F>0: n=-n
            face_normal[nearer]=n
            entry=np.where(mask,np.minimum(entry,d),entry)
            leave=np.where(mask,np.maximum(leave,d),leave)
        valid=np.isfinite(entry)&(leave>entry+1e-5)
        hit=valid&(entry<visible_depth[y0:y1,x0:x1])
        normals[y0:y1,x0:x1][hit]=face_normal[hit]
        visible_depth[y0:y1,x0:x1][hit]=entry[hit]
        # Merge overlapping / touching intervals while preserving real gaps.
        current_f=fronts[y0:y1,x0:x1]
        current_b=backs[y0:y1,x0:x1]
        fs=np.concatenate([current_f,np.where(valid,entry,np.inf)[...,None]],axis=-1)
        bs=np.concatenate([current_b,np.where(valid,leave,-np.inf)[...,None]],axis=-1)
        order=np.argsort(fs,axis=-1,kind='stable')
        fs=np.take_along_axis(fs,order,axis=-1)
        bs=np.take_along_axis(bs,order,axis=-1)
        merged_f=np.full_like(current_f,np.inf)
        merged_b=np.full_like(current_b,-np.inf)
        slots=np.full(xx.shape,-1,dtype=np.int8)
        last_end=np.full(xx.shape,-np.inf)
        iy,ix=np.indices(xx.shape)
        for j in range(CAPACITY+1):
            good=np.isfinite(fs[...,j])
            fresh=good&((slots<0)|(fs[...,j]>last_end+.00025))
            slots+=fresh.astype(np.int8)
            if np.any(slots>=CAPACITY): raise RuntimeError('Depth interval capacity exceeded')
            merged_f[iy[fresh],ix[fresh],slots[fresh]]=fs[...,j][fresh]
            last_end=np.where(fresh,bs[...,j],np.maximum(last_end,bs[...,j]))
            merged_b[iy[good],ix[good],slots[good]]=last_end[good]
        current_f[:]=merged_f
        current_b[:]=merged_b
    valid=np.isfinite(fronts)
    counts=valid.sum(axis=-1)
    overflow=int((counts>8).sum())
    if overflow:
        raise RuntimeError(f'{overflow} pixels exceed eight exported depth intervals')
    depth_min=float(math.floor(fronts[valid].min())-1)
    depth_max=float(math.ceil(backs[valid].max())+1)
    depth_range=depth_max-depth_min
    def quantize(v):
        safe=np.where(np.isfinite(v),v,depth_min)
        return np.round(np.clip((safe-depth_min)/depth_range,0,1)*65535).astype(np.uint16)
    for i in range(8):
        f,b=quantize(fronts[:,:,i]),quantize(backs[:,:,i])
        packed=np.stack([f>>8,f&255,b>>8,b&255],axis=-1).astype(np.uint8)
        packed.tofile(OUT/f'interval{i}.bin')
        png(f'interval{i}.png',packed)
    coverage=valid[:,:,0]
    for name,values in [('front',fronts[:,:,0]),('back',backs[:,:,0])]:
        q=quantize(values)
        data=np.stack([q>>8,q&255,np.zeros_like(q),coverage.astype(np.uint16)*255],axis=-1).astype(np.uint8)
        png(name+'.png',data)
    rgb=np.round(np.clip(normals*.5+.5,0,1)*255).astype(np.uint8)
    np.savez_compressed(ROOT/'verification'/'bake-data.npz',normals=rgb,visible_depth=visible_depth)
    png('normal.png',np.dstack([rgb,coverage.astype(np.uint8)*255]))
    thickness=np.where(coverage,backs[:,:,0]-fronts[:,:,0],0)
    png('thickness.png',np.dstack([np.repeat(np.clip(thickness[...,None]/2*255,0,255),3,axis=-1).astype(np.uint8),coverage.astype(np.uint8)*255]))
    preview_depth=np.where(coverage,1-(fronts[:,:,0]-depth_min)/depth_range,0)
    png('depth-preview.png',np.dstack([np.repeat(np.clip(preview_depth[...,None]*255,0,255),3,axis=-1).astype(np.uint8),coverage.astype(np.uint8)*255]))
    png('interval-count.png',np.dstack([(counts*50).astype(np.uint8),(counts*35).astype(np.uint8),(counts*18).astype(np.uint8),coverage.astype(np.uint8)*255]))
    manifest={key:layout[key] for key in ('width','height','pixelsPerUnit','camera')}
    manifest.update(depthMin=depth_min,depthRange=depth_range,layers=8,background='#3f7cb6',
                    maxHeight=max(v[2] for s in layout['solids'] for v in s['vertices']),
                    blenderVersion=bpy.app.version_string,solidCount=len(layout['solids']),
                    maxIntervals=int(counts.max()),overflowPixels=overflow,
                    coveredPixels=int(coverage.sum()),depthQuantum=depth_range/65535,
                    intervalHistogram={str(i):int((counts==i).sum()) for i in range(int(counts.max())+1)},
                    bakeSeconds=round(time.perf_counter()-started,3),
                    conventions='Positive linear camera depth. Raw packed RG front, BA back. Rows top-down. World Z up.',
                    assets='Original supplied Kenney building tiles; procedural ground and props.')
    (OUT/'scene.json').write_text(json.dumps(manifest,indent=2),encoding='utf8')
    print(json.dumps(manifest,indent=2))


scene=create_scene()
bake(scene)
print('Blender reconstruction and depth bake complete.')
