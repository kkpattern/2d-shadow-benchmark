"""Recreate the reference from source sprites and independently drawn vector scenery.

No reference pixels are used for scene geometry or scene color. sample.png is
used only by the comparison UI and validation scripts. Asset credit is kept
as text rather than adding the Kenney logo to the rendered scene.
"""
from pathlib import Path
import json
import math
import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'generated'
W, H, AA = 918, 515, 4
BLUE = (63, 124, 182)
OUT.mkdir(exist_ok=True)
im = Image.new('RGB', (W * AA, H * AA), BLUE)
d = ImageDraw.Draw(im)

def poly(points, fill, outline=None, width=1):
    p = [(round(x * AA), round(y * AA)) for x, y in points]
    d.polygon(p, fill=fill)
    if outline:
        d.line(p + [p[0]], fill=outline, width=max(1, round(width * AA)), joint='curve')

def line(points, fill, width=1):
    d.line([(round(x * AA), round(y * AA)) for x, y in points], fill=fill, width=max(1, round(width * AA)), joint='curve')

outline = [(408,112),(552,190),(615,165),(720,217),(720,268),(772,294),(720,320),(668,294),(668,346),
           (616,372),(564,346),(512,372),(460,346),(408,372),(148,242),
           (200,216),(148,190),(200,164),(252,190),(304,164),(356,138)]

# Raised terrain: vertical sides, then a continuous paving surface.
poly([(x,y+27) for x,y in outline], '#a77d53')
poly([(x,y+14) for x,y in outline], '#b1a78d')
for a,b in zip(outline, outline[1:]+outline[:1]):
    if b[0] <= a[0] or b[1] >= a[1]:
        dark=b[0]<a[0] and b[1]>a[1]
        poly([(a[0],a[1]+14),(b[0],b[1]+14),(b[0],b[1]+27),(a[0],a[1]+27)], '#805f3e' if dark else '#a77d53')
        poly([a,b,(b[0],b[1]+14),(a[0],a[1]+14)], '#979385' if dark else '#c2beac')
poly(outline, '#cfccb8')

# Restrict tile seams/roads to the independently traced ground silhouette.
ground = Image.new('RGB', im.size, '#cfccb8')
gd = ImageDraw.Draw(ground)
for i in range(-8, 10):
    x, y = 408 + i * 52, 112 + i * 26
    gd.line([(int((x-500)*AA),int((y+250)*AA)),(int((x+500)*AA),int((y-250)*AA))], fill='#a7a591', width=AA)
    x, y = 408 - i * 52, 112 + i * 26
    gd.line([(int((x-500)*AA),int((y-250)*AA)),(int((x+500)*AA),int((y+250)*AA))], fill='#a7a591', width=AA)

# Road junctions and broad, rounded western bend. All coordinates are scene
# geometry; this is deliberately not a masked copy of the source screenshot.
road = '#61615e'
# Visible road edge polygons were measured against the reference. They are
# editable scene geometry; the output contains no reference scene pixels.
road_polygons = [
    [(382,127),(395,133),(395,144),(419,156),(419,133),(395,121)],
    [(579,197),(628,172),(635,176),(635,193),(601,210)],
    [(635,177),(651,184),(635,192)],
    [(282,190),(305,179),(356,205),(413,176),(413,185),(420,190),(419,198),
     (407,191),(369,210),(367,214),(368,242),(359,253),(357,249),(323,232),
     (325,225),(322,222),(330,218),(329,214)],
    [(316,223),(331,230),(329,242),(293,260),(286,266),(285,272),(291,277),
     (414,338),(490,300),(492,296),(446,273),(446,251),(460,257),(524,225),
     (524,239),(519,243),(519,250),(487,266),(484,269),(591,323),(586,324),
     (582,328),(582,341),(504,302),(428,340),(427,345),(445,354),(446,365),
     (435,372),(420,372),(420,363),(259,283),(251,276),(249,272),(249,264),(258,254)],
    [(599,347),(600,350),(628,364),(628,379),(654,366),(654,354),(609,332),(608,342)],
]
for points in road_polygons:
    gd.polygon([(round(x*AA),round(y*AA)) for x,y in points],fill=road)

# The center sidewalk is a diamond island around the red glazed tower.
gd.polygon([(x*AA,y*AA) for x,y in [(286,268),(364,229),(493,295),(414,335)]], fill='#d5d1bd')
gd.line([(x*AA,y*AA) for x,y in [(286,268),(364,229),(493,295),(414,335),(286,268)]], fill='#a6a491',width=AA)
for a,b in [((310,256),(438,320)),((337,243),(465,307)),((312,281),(390,242)),((363,307),(442,268))]:
    gd.line([(int(a[0]*AA),int(a[1]*AA)),(int(b[0]*AA),int(b[1]*AA))],fill='#b6b29d',width=AA)

# Zebra crossing, four narrow painted strips parallel to the road's other axis.
for n in range(4):
    x, y = 343 + n*5, 321 - n*2.5
    gd.polygon([(int(px*AA),int(py*AA)) for px,py in [(x,y),(x+11,y+5.5),(x+14,y+4),(x+3,y-1.5)]], fill='#f1f1e9')
mask = Image.new('L',im.size,0)
ImageDraw.Draw(mask).polygon([(int(x*AA),int(y*AA)) for x,y in outline],fill=255)
im.paste(ground,(0,0),mask)
d = ImageDraw.Draw(im)

# A short descending entrance ramp, with two raised cream curbs.
poly([(408,374),(479,371),(502,421),(497,443),(428,445)], '#a77d53')
poly([(408,374),(479,371),(502,421),(500,432),(430,434)], '#b9b6a3')
poly([(434,374),(467,374),(485,421),(451,422)], '#686865')
poly([(451,422),(485,421),(482,432),(448,433)], '#60605e')
poly([(415,374),(434,374),(451,422),(432,423)], '#e3dfc7')
poly([(408,374),(415,374),(432,423),(430,434),(411,383)], '#c8c5b2')
poly([(432,423),(451,422),(448,433),(430,434)], '#c3c0ad')
poly([(467,373),(482,372),(502,421),(485,421)], '#e3dfc7')
poly([(485,421),(502,421),(500,432),(482,432)], '#bdbba9')

def tree(cx, cy, size=22):
    # cy is the bottom of the trunk; light comes from upper left in original art.
    line([(cx,cy),(cx,cy-17)], '#80613d', 5)
    r=size/2
    top=cy-34
    poly([(cx,top),(cx+r,top+6),(cx,top+12),(cx-r,top+6)], '#8ebe48')
    poly([(cx-r,top+6),(cx,top+12),(cx,top+26),(cx-r,top+20)], '#75a334')
    poly([(cx,top+12),(cx+r,top+6),(cx+r,top+20),(cx,top+26)], '#5e8a2d')

def lamp(x,y):
    line([(x+1,y),(x+1,y-33),(x+4,y-35),(x+15,y-30)], '#aaa99d', 4)
    line([(x,y),(x,y-33),(x+3,y-35),(x+14,y-30)], '#deded5', 2)

def wall():
    poly([(616,247),(668,273),(668,293),(616,267)], '#a85753')
    poly([(668,273),(721,247),(721,266),(668,293)], '#914b48')
    line([(616,247),(668,273),(721,247)], '#e6e4ce', 4)
    line([(668,275),(668,290)], '#e0c4ae', 1)

def vent():
    poly([(642,217),(667,205),(692,217),(667,230)], '#b6b39e')
    poly([(642,213),(667,201),(692,213),(667,226)], '#e0ddc4')
    poly([(658,198),(667,193),(677,198),(667,203)], '#8ac6d4')
    poly([(658,198),(667,203),(667,219),(658,214)], '#75afbe')
    poly([(667,203),(677,198),(677,214),(667,219)], '#619cac')

layout = json.loads((OUT/'scene-layout.json').read_text(encoding='utf-8'))
sprites = layout.get('sprites', layout.get('placements', []))
commands = []
building_depth = {b['id']:b.get('footprintCenter',b.get('tileCenter',[0,0]))[1] for b in layout.get('buildings',[])}
for index,s in enumerate(sprites):
    commands.append(((building_depth.get(s.get('building'),s['y']), -s['y']), 'sprite', s))

# Custom props are inserted by their ground depth after sprite ordering.
# Building groups share their base y. Top floors must be drawn after lower ones.
if sprites and all('order' not in s and 'zOrder' not in s for s in sprites):
    commands=[]
    for index,s in enumerate(sprites):
        commands.append((s.get('groundY',s.get('ground_y',s['y']+Image.open(ROOT/'assets'/f"buildingTiles_{int(s['id']):03d}.png").height*s.get('scale',layout.get('scale',.8)))), 'sprite', s))

# Draw props after sprites for consistent visible silhouettes. The western lamp
# is clear of all facades and the northern tree overlaps only the low back shop.
hidden_tree_drawn=False
for _,_,s in sorted(commands, key=lambda c:c[0]):
    if s.get('building')=='tan-tower' and not hidden_tree_drawn:
        tree(427,198,24)
        hidden_tree_drawn=True
    sid = int(s['id'])
    source = Image.open(ROOT/'assets'/f'buildingTiles_{sid:03d}.png').convert('RGBA')
    scale = s.get('scale',layout.get('scale',.8))
    if s.get('category') == 'base':
        # The pack includes a complete terrain tile below every base. The
        # reconstruction shares one continuous terrain, so retain the building
        # silhouette and let the vector terrain supply the paving and sides.
        building_mask = Image.new('L',source.size,0)
        ImageDraw.Draw(building_mask).polygon([(66,0),(116,25),(116,60),(66,85),(16,60),(16,25)],fill=255)
        alpha=np.asarray(source.getchannel('A')).copy()
        alpha=np.minimum(alpha,np.asarray(building_mask))
        source.putalpha(Image.fromarray(alpha))
    if s.get('whiteRoof',False):
        pixels=np.asarray(source).copy()
        rim=Image.new('L',source.size,0)
        rd=ImageDraw.Draw(rim)
        cx=source.width/2
        rd.polygon([(cx,0),(source.width,25),(cx,50),(0,25)],fill=255)
        rd.polygon([(cx,7),(source.width-11,25),(cx,43),(11,25)],fill=0)
        bright=(np.asarray(rim)>0)&(pixels[:,:,3]>0)
        pixels[:,:,:3][bright]=255
        source=Image.fromarray(pixels)
    source=source.resize((round(source.width*scale*AA),round(source.height*scale*AA)),Image.Resampling.LANCZOS)
    im.paste(source,(round(s['x']*AA),round(s['y']*AA)),source)

d = ImageDraw.Draw(im)
tree(388,181,24)
lamp(261,252)
lamp(572,205)
lamp(633,214)
wall()
vent()
tree(595,356,24)
tree(634,336,24)

im=im.resize((W,H),Image.Resampling.LANCZOS)
im.save(OUT/'albedo.png')
(OUT/'scenery-geometry.json').write_text(json.dumps({'outline':outline,'screenSize':[W,H],'attribution':'Assets by Kenney (CC0)','terrain':'vector reconstruction; no scene pixels copied'},indent=2))
print(f'Composed {len(sprites)} source sprites and vector scenery → generated/albedo.png')
