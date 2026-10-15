"""Create a conservative, explicitly reviewed semantic test overlay.

SAM supplies boundaries. Classes below are analyst interpretations of this one
Esri RGB scene, not learned predictions or transferable land-cover rules.
Unknown/mixed objects remain unclassified. Existing buildings take precedence.
"""
from pathlib import Path
import json
import xml.etree.ElementTree as ET
import numpy as np
import rasterio
from rasterio.features import shapes, rasterize
from scipy import ndimage as ndi
import geopandas as gpd
from shapely.geometry import shape, box, Polygon
from affine import Affine
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from skimage.segmentation import find_boundaries

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'output'
NAMES={1:'Water',2:'Tree and woody vegetation',3:'Cultivated fields / plantations',4:'Open ground / sparse cover'}
COLORS={1:'#268bea',2:'#36ac55',3:'#badc63',4:'#c78740'}
# Reviewed against aligned_sam_audit.png. Small ambiguous masks excluded.
REVIEWED={
  1:[68,70],
  2:[33,35,38,40,46,53,55,59,61,64,65,69,72],
  3:[32,34,43,47,48,49,52,56,62,66,73],
  4:[39,45,50,54,57,58,63,67,71],
}
REVIEWED_LAND_PROMPTS={'open_central':4,'trees_lower_left':2}

def remove_small(mask,minimum):
    labs,n=ndi.label(mask)
    sizes=np.bincount(labs.ravel())
    keep=sizes>=minimum; keep[0]=False
    return keep[labs]

def write_style():
    root=ET.Element('qgis',version='3.40',styleCategories='Symbology')
    renderer=ET.SubElement(root,'renderer-v2',type='categorizedSymbol',attr='class_id',symbollevels='0',enableorderby='0')
    categories=ET.SubElement(renderer,'categories'); symbols=ET.SubElement(renderer,'symbols')
    for k,name in NAMES.items():
        ET.SubElement(categories,'category',value=str(k),symbol=str(k),label=name,render='true',type='long')
        symbol=ET.SubElement(symbols,'symbol',name=str(k),type='fill',alpha='1',clip_to_extent='1')
        layer=ET.SubElement(symbol,'layer',**{'class':'SimpleFill','enabled':'1','pass':'0','locked':'0'})
        opts=ET.SubElement(layer,'Option',type='Map')
        color=','.join(str(int(COLORS[k][i:i+2],16)) for i in (1,3,5))
        for key,val in {'color':color+',28','outline_color':color+',255','outline_width':'.23','outline_width_unit':'MM','outline_style':'solid','style':'solid','joinstyle':'round'}.items():
            ET.SubElement(opts,'Option',name=key,value=val,type='QString')
    ET.ElementTree(root).write(OUT/'reviewed_test_classes.qml',encoding='utf-8',xml_declaration=True)

def main():
    with rasterio.open(ROOT/'data/esri_test_aligned.tif') as src:
        rgb=src.read(); profile=src.profile.copy(); transform=src.transform; crs=src.crs; bounds=src.bounds
    with rasterio.open(OUT/'sam_masks_aligned.tif') as src: sam=src.read(1)
    labels=np.zeros(sam.shape,dtype=np.uint8)
    for cls,ids in REVIEWED.items(): labels[np.isin(sam,ids)]=cls
    # Only these two candidates passed the separate visual prompt audit.
    land_masks=np.load(OUT/'prompted_land_masks.npz')
    for name,cls in REVIEWED_LAND_PROMPTS.items():
        labels[(labels==0)&land_masks[name]]=cls
    # Restrict water prompts to water-like pixels to protect islands/trees.
    r,g,b=ndi.gaussian_filter(rgb.astype(np.float32),sigma=(0,1,1))
    water_evidence=(r<90)&(r<g*.94)&(b>g*.73)&(g<115)
    prompted=np.load(OUT/'prompted_water_masks.npz')
    prompt_scores=json.loads((OUT/'water_prompts.json').read_text())['sam_scores_not_class_probabilities']
    proposed=np.isin(sam,REVIEWED[1])
    for name in prompted.files:
        if prompt_scores[name]>=.5: proposed |= prompted[name]
    # Grow SAM-derived water seeds only through connected water-like pixels.
    # This recovers missed river reaches, not arbitrary disconnected shadows.
    # Visually reviewed land masks are barriers; islands are never hole-filled.
    land_barrier=np.isin(sam,REVIEWED[2]+REVIEWED[3]+REVIEWED[4])
    allowed=water_evidence & ~land_barrier
    # Reviewed search corridor, not a hand-drawn output boundary. Restrict
    # growth to the main river; otherwise blue-gray dam faces can connect to
    # the reservoir seeds. Outside it, retain only the original SAM proposals.
    corridor_points=[(175,880),(180,800),(300,690),(450,490),(650,390),
        (880,320),(1050,230),(1200,130),(1300,30),(1500,30),(1490,170),
        (1380,350),(1240,440),(1110,470),(970,490),(780,645),(560,760),(400,890)]
    corridor=rasterize([(Polygon(corridor_points),1)],out_shape=sam.shape,
        transform=Affine(2005/2660,0,20,0,1090/1446,30),dtype='uint8')>0
    water=ndi.binary_propagation(proposed & allowed,mask=allowed & (corridor|proposed))
    water=ndi.binary_closing(water,iterations=2)
    water=remove_small(water,100)
    # Do not fill polygon holes: islands and exposed bars must remain land.
    labels[labels==1]=0
    labels[water]=1
    # Exclude confident greenery within broad open-ground masks.
    greenery=(g>r*1.10)&(g>b*1.2)
    labels[(labels==4)&ndi.binary_opening(greenery,iterations=2)]=0
    # Remove tiny disconnected fragments instead of reporting them as objects.
    for cls in NAMES:
        valid=remove_small(labels==cls,100)
        labels[(labels==cls)&~valid]=0
    buildings=gpd.read_file(ROOT.parent/'samgeo/output/bhadra_classified_buildings.gpkg').to_crs(crs)
    bounds_geom=box(*bounds)
    buildings=buildings[buildings.intersects(bounds_geom)]
    buildings=buildings.copy(); buildings.geometry=buildings.geometry.intersection(bounds_geom)
    building_mask=rasterize([(x,1) for x in buildings.geometry],out_shape=sam.shape,transform=transform,dtype='uint8')>0
    labels[building_mask]=0
    # Remove the fractional layout-frame border from inference coverage.
    labels[:2,:]=0; labels[:,:2]=0; labels[-2:,:]=0; labels[:,-2:]=0
    profile.update(count=1,dtype='uint8',nodata=0)
    with rasterio.open(OUT/'reviewed_classes.tif','w',**profile) as dst:
        dst.write(labels,1)
        dst.update_tags(classes=json.dumps(NAMES),method='SAM boundaries + scene-specific visual review + SAM-seeded RGB water refinement',status='Test area; visual interpretation; not field validated')
    building_union=buildings.geometry.union_all()
    rows=[]
    for geom,value in shapes(labels,mask=labels>0,transform=transform):
        geometry=shape(geom).difference(building_union)
        if geometry.area<20: continue
        method='SAM-seeded RGB refinement' if int(value)==1 else 'SAM + visual review'
        rows.append({'class_id':int(value),'class_name':NAMES[int(value)],'method':method,'quality':'Visual interpretation; unvalidated','area_m2':geometry.area,'geometry':geometry})
    features=gpd.GeoDataFrame(rows,crs=crs)
    features.to_file(OUT/'reviewed_test_classes.gpkg',layer='reviewed_classes',driver='GPKG')
    buildings.to_file(OUT/'reviewed_test_classes.gpkg',layer='buildings_reference',driver='GPKG')
    # Geometry integrity checks operate on actual exported geometries.
    union=features.geometry.union_all()
    overlap=float(features.area.sum()-union.area)
    building_overlap=float(union.intersection(buildings.geometry.union_all()).area)
    # Exact vector subtraction gives the accepted buildings precedence.
    report={'class_counts':features.class_name.value_counts().to_dict(),
        'class_area_m2':features.groupby('class_name').area_m2.sum().to_dict(),
        'invalid_geometries':int((~features.is_valid).sum()),
        'class_overlap_m2':overlap,'building_edge_overlap_m2':building_overlap,
        'unclassified_fraction':float((labels==0).mean()),
        'reviewed_sam_ids':REVIEWED,'water_holes_preserved':True,
        'accepted_land_prompts':REVIEWED_LAND_PROMPTS,
        'rejected_land_prompts':{'trees_lower_middle':'Selected roofs/mixed settlement, not canopy','open_riverbank':'Mixed surface; unreliable extent'},
        'water_growth_search_corridor_audit_pixels':corridor_points,
        'scope':'Only the saved layout test footprint; no full-Bhadra classification',
        'limitations':['Visual RGB interpretation, not field validated','Some shadows, dry vegetation and bare soil remain ambiguous','Vegetation class is canopy/patch extent, not individual botanical tree identity']}
    assert report['invalid_geometries']==0
    assert abs(overlap)<.01
    assert building_overlap<.01
    (OUT/'classification_review.json').write_text(json.dumps(report,indent=2))
    write_style()
    # A georeferenced visual audit with the accepted reference buildings.
    fig,axes=plt.subplots(1,2,figsize=(20,7),sharex=True,sharey=True)
    extent=(bounds.left,bounds.right,bounds.bottom,bounds.top)
    for ax in axes:
        ax.imshow(rgb.transpose(1,2,0),extent=extent)
        ax.set_axis_off()
    axes[0].set_title('Esri source — corrected map coordinates')
    axes[1].set_title('Reviewed SAM test classes — buildings preserved')
    for cls,name in NAMES.items():
        subset=features[features.class_id==cls]
        subset.plot(ax=axes[1],facecolor=COLORS[cls],edgecolor=COLORS[cls],alpha=.23,linewidth=.45)
        subset.boundary.plot(ax=axes[1],color=COLORS[cls],linewidth=.45)
    buildings.boundary.plot(ax=axes[1],color='#f34b49',linewidth=.4)
    fig.legend(handles=[Patch(color=COLORS[k],label=v) for k,v in NAMES.items()]+[Patch(color='#f34b49',label='Existing buildings')],loc='lower center',ncol=3)
    fig.tight_layout(rect=(0,.08,1,1)); fig.savefig(OUT/'reviewed_test_preview.png',dpi=160); plt.close(fig)
    print(json.dumps(report,indent=2))

if __name__=='__main__': main()
