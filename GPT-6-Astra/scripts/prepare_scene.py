"""Rebuild the reference composition from supplied tiles and procedural street props.

No pixels are copied from sample.png. The reference is used only for comparison.
The same solid descriptions drive the Blender reconstruction and depth bake.
"""
from pathlib import Path
import json
import math
import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'public' / 'generated'
OUT.mkdir(parents=True, exist_ok=True)
W, H, AA = 918, 515, 4
SCALE = 26 / 33
PPU = 52 * math.sqrt(2)
ZPX = PPU * math.sqrt(3) / 2
RIGHT = np.array([-1, 1, 0]) / math.sqrt(2)
UP = np.array([-1 / math.sqrt(8), -1 / math.sqrt(8), math.sqrt(3) / 2])
FORWARD = np.cross(UP, RIGHT)
SOLIDS = []


def world(sx, sy, z=0):
    dx, dy = (sx - W / 2) / 52, (sy - H / 2 + ZPX * z) / 26
    return [(dy - dx) / 2, (dx + dy) / 2, z]


def project(v):
    a = np.array(v)
    return (W / 2 + np.dot(a, RIGHT) * PPU, H / 2 - np.dot(a, UP) * PPU)


def box(name, center, size, color, category='architecture'):
    cx, cy, cz = center
    dx, dy, dz = np.array(size) / 2
    vertices = [[cx+x*dx, cy+y*dy, cz+z*dz]
                for x,y,z in [(-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),
                              (-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1)]]
    faces = [[0,3,2,1],[0,1,5,4],[1,2,6,5],[2,3,7,6],[3,0,4,7],[4,5,6,7]]
    solid = dict(name=name, vertices=vertices, faces=faces, color=color, category=category)
    SOLIDS.append(solid)
    return solid


def prism(name, footprint, bottom, top, color, category='street'):
    points = [world(x,y)[:2] for x,y in footprint]
    n = len(points)
    vertices = [[x,y,bottom] for x,y in points] + [[x,y,top] for x,y in points]
    # Reorient to outward faces regardless of the input screen winding.
    area = sum(points[i][0]*points[(i+1)%n][1]-points[(i+1)%n][0]*points[i][1] for i in range(n))
    if area < 0:
        points.reverse()
        vertices = [[x,y,bottom] for x,y in points] + [[x,y,top] for x,y in points]
    faces = [list(reversed(range(n))), list(range(n,2*n))]
    faces += [[i,(i+1)%n,(i+1)%n+n,i+n] for i in range(n)]
    solid = dict(name=name, vertices=vertices, faces=faces, color=color, category=category)
    SOLIDS.append(solid)
    return solid


def poly(image, pts, fill, outline=None, width=1):
    draw = ImageDraw.Draw(image)
    scaled = [(round(x*AA),round(y*AA)) for x,y in pts]
    draw.polygon(scaled, fill=tuple(fill))
    if outline:
        draw.line(scaled+[scaled[0]], fill=tuple(outline), width=max(1,round(width*AA)), joint='curve')


def draw_solid(image, solid, stroke=False):
    vs = np.array(solid['vertices'])
    faces = []
    for indices in solid['faces']:
        face = vs[indices]
        normal = np.cross(face[1]-face[0],face[2]-face[0])
        norm = np.linalg.norm(normal)
        if norm == 0: continue
        normal /= norm
        if np.dot(normal, FORWARD) >= -1e-6: continue
        # Fixed asset-like lighting for the painted source layer.
        shade = 1.06 if normal[2] > .6 else (.91 if normal[0] > .5 else .78)
        color = [max(0,min(255,round(c*shade))) for c in solid['color']]
        depth = np.mean(face @ FORWARD)
        faces.append((depth, [project(v) for v in face], color))
    for _, pts, color in sorted(faces, reverse=True):
        poly(image, pts, color, [174,172,154] if stroke else None, .65)


def draw_objects(image, objects, stroke=False):
    for obj in sorted(objects, key=lambda o: np.mean(np.array(o['vertices'])@FORWARD), reverse=True):
        draw_solid(image, obj, stroke)


def street_path(image, points, radius=.255):
    """Stroke in the ground plane, preserving constant physical road width."""
    points=[np.array(world(*p)) for p in points]
    ink=[89,90,87,255]
    for a,b in zip(points,points[1:]):
        t=b-a
        n=np.array([-t[1],t[0],0]); n*=radius/np.linalg.norm(n)
        poly(image,[project(v) for v in (a+n,b+n,b-n,a-n)],ink)
    for p in points:
        poly(image,[project(p+np.array([math.cos(t)*radius,math.sin(t)*radius,0])) for t in np.linspace(0,math.tau,48)],ink)


def sprite(image, index, x, y, whiten=False):
    source = Image.open(ROOT / 'assets' / f'buildingTiles_{index:03d}.png').convert('RGBA')
    if source.width >= 130:
        # Base modules contain their own thick ground tile. Neighbouring paving
        # hides those sides in a continuous city; retain only the building.
        mask = Image.new('L',source.size)
        ImageDraw.Draw(mask).polygon([(14,0),(119,0),(119,61),(70,89),(63,89),(14,63)],fill=255)
        source.putalpha(Image.fromarray(np.minimum(np.array(source.getchannel('A')),np.array(mask))))
    if whiten:
        # Roof lips in the reference use a brighter trim; preserve walls and windows.
        data = np.array(source)
        yy = np.arange(source.height)[:,None]
        rgb = data[:,:,:3].astype(int)
        # Top outer diamond, rather than the recessed roof deck.
        xx = np.arange(source.width)[None,:]
        roof_y = np.abs(xx-(source.width-1)/2)*.5
        edge = ((yy >= roof_y) & (yy < roof_y+6)) | ((yy > 48-roof_y) & (yy < 55-roof_y))
        mask = edge & (yy < 56) & (rgb.min(2)>160) & (rgb.max(2)-rgb.min(2)<48)
        data[mask,:3] = np.minimum(255, rgb[mask] + 40)
        source = Image.fromarray(data)
    size = (round(source.width*SCALE*AA), round(source.height*SCALE*AA))
    source = source.resize(size, Image.Resampling.LANCZOS)
    image.alpha_composite(source, (round(x*AA), round(y*AA)))


def building(name, x, y, height, floors, color, style, awning=None):
    center = world(x,y)
    cx,cy,_ = center
    width=.75
    roof=.055
    box(name+' / masonry', [cx,cy,(height-.085)/2], [width,width,height-.085], color)
    box(name+' / recessed roof', [cx,cy,height-.075], [.67,.67,.04], [196,195,174])
    for axis in (0,1):
        for side in (-1,1):
            c=[cx,cy,height-.026]
            c[axis]+=side*(width/2-.018)
            dims=[width,width,.052]
            dims[axis]=.036
            box(name+f' / parapet {axis} {side}',c,dims,[224,223,204])
    floorheight=height/floors
    for level in range(floors):
        z=(level+.12)*floorheight
        if level > 0:
            box(name+f' / cornice {level}',[cx,cy,level*floorheight],[.756,.756,.035],[211,210,191])
        for face in (0,1):
            # The simpler faces intentionally follow the supplied sprite's massing.
            if style == 'plain' and face == 1: continue
            count=3 if style=='arched' else 2
            for k in range(count):
                c=[cx,cy,z+floorheight*.38]
                c[face]+=.378
                c[1-face]+=(k-(count-1)/2)*(.22 if count==3 else .34)
                dims=[.12 if count==3 else .28]*2+[floorheight*.58]
                dims[face]=.012
                box(name+f' / window {level} {face} {k}',c,dims,[134,174,181], 'detail')
    if awning:
        c=[cx+.43,cy,floorheight*.72]
        box(name+' / canopy',c,[.18,.79,.065],awning)


def main():
    image = Image.new('RGBA',(W*AA,H*AA),(0,0,0,0))
    # The irregular island is assembled as real closed paving and earth volumes.
    tiles = {(u,v) for u in range(5) for v in range(5)}
    tiles |= {(-1,2),(-1,3),(4,-1),(5,0),(6,0),(5,1),(5,2),(6,2),(5,3)}
    for u,v in sorted(tiles):
        sx=407+52*(u-v)
        sy=113+26*(u+v)+26
        c=world(sx,sy)
        box(f'Tile {u},{v} / earth',[c[0],c[1],-.31],[1,1,.18],[170,132,87],'ground')
        box(f'Tile {u},{v} / paving',[c[0],c[1],-.11],[1,1,.22],[202,201,181],'ground')
    back_street=[(563,191),(616,165),(637,176),(637,202),(615,213)]
    prism('Back street / earth',back_street,-.4,-.22,[170,132,87],'ground')
    prism('Back street / paving',back_street,-.22,0,[202,201,181],'ground')
    draw_objects(image,SOLIDS,True)
    # Street ribbons, curb islands and crossing markings; paths lie on z=0.
    # Keep roads on the island even where reconstructed paths run past the edge.
    road = Image.new('RGBA',image.size)
    street_path(road,[(356,215),(646,360)])
    street_path(road,[(622,178),(444,267)])
    street_path(road,[(405,124),(545,194)])
    street_path(road,[(301,185),(356,212)])
    street_path(road,[(356,215),(280,253),(268,260),(266,267),(270,273),(438,357)])
    street_path(road,[(438,357),(523,314)])
    alpha = np.array(road.getchannel('A'))
    groundalpha=np.array(image.getchannel('A'))
    road.putalpha(Image.fromarray(np.minimum(alpha,groundalpha)))
    image.alpha_composite(road)
    road.resize((W,H),Image.Resampling.LANCZOS).save(OUT/'roads.png')
    for i in range(4):
        x=341+i*6
        y=320-i*3
        poly(image,[(x,y),(x+13,y+6.5),(x+16,y+5),(x+3,y-1.5)],[242,241,226,255])

    # Detached foreground road tile, visible in the supplied reference.
    bridge=[(410,375),(481,372),(500,422),(429,425)]
    bridgeobjs=[prism('Detached road / earth',bridge,-.3,-.15,[170,132,87]),
                prism('Detached road / deck',bridge,-.15,0,[207,205,183])]
    draw_objects(image,bridgeobjs)
    poly(image,[(430,375),(466,373),(485,423),(448,425)],[100,101,97,255])
    # Geometric inset kerbs for thickness and cast shadows.
    for name,pts in [('west',[(410,375),(429,375),(449,425),(430,425)]),
                     ('east',[(467,373),(481,372),(500,422),(486,423)])]:
        obj=prism('Detached road / '+name+' kerb',pts,0,.035,[219,217,192])
        draw_solid(image,obj)

    # Build meshes beneath each sprite stack. Base tile top centers are calibrated
    # from asset pixels, independently of the visual sprite composition.
    layouts=[
      dict(name='Ruby apartments',base=[200,118],top=90,floors=2,color=[163,64,60],style='arched',sprites=[(36,200,118),(49,213,90)],white=True),
      dict(name='Sandstone tower',base=[148,195],top=114,floors=4,color=[184,184,132],style='arched',sprites=[(29,148,195),(51,161,168),(51,161,141),(51,161,114)],white=True),
      dict(name='Corner cottage',base=[304,117],top=114,floors=1,color=[160,125,81],style='arched',sprites=[(14,304,117),(102,316,114)]),
      dict(name='Ochre tower',base=[408,171],top=83,floors=4,color=[166,126,79],style='arched',awning=[176,129,69],sprites=[(99,408,171),(38,421,140),(38,421,113),(38,421,86),(110,420,83)]),
      dict(name='Blue corner offices',base=[460,144],top=113,floors=2,color=[184,188,170],style='glass',sprites=[(124,460,144),(15,472,116),(5,472,113)]),
      dict(name='Green newsstand',base=[304,221],top=226,floors=1,color=[181,181,162],style='glass',awning=[125,170,50],sprites=[(108,304,221),(88,317,213)]),
      dict(name='Glass avenue',base=[356,247],top=193,floors=3,color=[164,69,63],style='glass',sprites=[(1,356,247),(23,369,220),(23,369,193)],white=True),
      dict(name='Crimson shop',base=[512,221],top=191,floors=2,color=[165,58,57],style='plain',awning=[103,165,192],sprites=[(34,512,221),(52,525,194),(128,524,191)]),
    ]
    visual=[]
    for b in layouts:
        x,y=b['base']
        sx,sy=x+52,y+60*SCALE
        height=(sy-19.5-b['top'])/ZPX
        building(b['name'],sx,sy,height,b['floors'],b['color'],b['style'],b.get('awning'))
        visual.append((sy,'building',b))
    # The kiosk's dark gable is two convex wedges; no billboard shadow proxy.
    cx,cy,_=world(356,221+60*SCALE)
    z=(221+60*SCALE-19.5-226)/ZPX
    for side in (-1,1):
        verts=[[cx-.39,cy+side*.39,z],[cx+.39,cy+side*.39,z],
               [cx+.39,cy,z+.24],[cx-.39,cy,z+.24],
               [cx-.39,cy,z],[cx+.39,cy,z]]
        SOLIDS.append(dict(name=f'Newsstand gable {side}',vertices=verts,faces=[[0,1,2,3],[0,4,5,1],[4,3,2,5],[0,3,4],[1,5,2]],color=[90,91,87],category='architecture'))

    # Fountain terrace and low red retaining wall, absent from the supplied tiles.
    start=len(SOLIDS)
    c=world(667,244)
    box('Fountain terrace',[c[0],c[1],.19],[1,1,.38],[198,195,173])
    c=world(667,242)
    box('Fountain / plinth',[c[0],c[1],.405],[.46,.46,.05],[173,173,156])
    box('Fountain / water',[c[0],c[1],.447],[.34,.34,.035],[111,166,181])
    box('Fountain / centerpiece',[c[0],c[1],.59],[.19,.19,.29],[118,185,204])
    visual.append((244,'solid',SOLIDS[start:]))
    start=len(SOLIDS)
    # Continuous low red volume beside the fountain terrace.
    c=world(668,281)
    box('Courtyard / red wall',[c[0],c[1],.16],[1,1,.32],[161,62,59])
    box('Courtyard / pale cap',[c[0],c[1],.335],[1.025,1.025,.035],[219,217,198])
    visual.append((282,'solid',SOLIDS[start:]))
    for i,(sx,sy) in enumerate([(388,180),(427,214),(595,355),(635,335)]):
        start=len(SOLIDS)
        c=world(sx,sy)
        box(f'Tree {i} / trunk',[c[0],c[1],.12],[.055,.055,.24],[136,105,65],'vegetation')
        box(f'Tree {i} / crown',[c[0],c[1],.33],[.23,.23,.27],[112,168,51],'vegetation')
        visual.append((sy,'solid',SOLIDS[start:]))
    for i,(sx,sy) in enumerate([(259,246),(320,250),(570,197),(635,201)]):
        start=len(SOLIDS)
        c=world(sx,sy)
        box(f'Lamp {i} / pole',[c[0],c[1],.22],[.023,.023,.44],[165,166,155],'street')
        box(f'Lamp {i} / arm',[c[0]+.09,c[1],.44],[.20,.025,.025],[212,211,194],'street')
        visual.append((sy,'solid',SOLIDS[start:]))
    for _,kind,item in sorted(visual,key=lambda v:v[0]):
        if kind=='solid': draw_objects(image,item)
        else:
            for index,x,y in item['sprites']: sprite(image,index,x,y,item.get('white',False))
    image=image.resize((W,H),Image.Resampling.LANCZOS)
    image.save(OUT/'color.png')
    bg=Image.new('RGBA',(W,H),(63,124,182,255))
    bg.alpha_composite(image)
    bg.convert('RGB').save(ROOT/'verification'/'reconstruction.png')
    layout=dict(width=W,height=H,pixelsPerUnit=PPU,camera=dict(right=RIGHT.tolist(),up=UP.tolist(),forward=FORWARD.tolist(),origin=(-FORWARD*20).tolist()),solids=SOLIDS,buildings=layouts)
    (OUT/'layout.json').write_text(json.dumps(layout,indent=2),encoding='utf8')
    print(f'Prepared {len(SOLIDS)} closed solids and {sum(len(b["sprites"]) for b in layouts)} sprite layers.')


if __name__=='__main__': main()
