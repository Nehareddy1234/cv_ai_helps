"""Compose whole-AOI SAM regions and conservatively classify broad RGB land cover.

SAM is a segmentation model, not a semantic land-cover classifier. This script
uses resolution-matched examples from the previous test scene to label SAM and
explicitly tagged edge-completion regions. All labels require review.
"""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess
import sys
import xml.etree.ElementTree as ET
import numpy as np
import geopandas as gpd
import rasterio
from rasterio.features import rasterize, shapes
from rasterio.windows import Window, from_bounds
from rasterio.warp import reproject, transform_bounds, Resampling
from scipy import ndimage as ndi
from skimage.color import rgb2hsv, rgb2lab
from skimage.measure import label as connected
from skimage.segmentation import felzenszwalb
from shapely import make_valid
from shapely.geometry import shape
from shapely.ops import unary_union
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import confusion_matrix
import joblib

ROOT=Path(__file__).resolve().parent
TEST=ROOT.parent/'samgeo_esri_test'
OUT=ROOT/'output'
CACHE=ROOT/'cache'
NAMES={1:'Water',2:'Trees / dense woody vegetation',3:'Crops / grass / low vegetation',
       4:'Bare soil / rock / sparse ground',8:'Uncertain / mixed'}
COLORS={1:'36,137,239',2:'35,132,67',3:'164,214,94',4:'200,140,71',8:'156,156,156'}

def save_json(path,value):
    tmp=path.with_suffix('.tmp'); tmp.write_text(json.dumps(value,indent=2)); tmp.replace(path)

def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()

def features(rgb):
    f=rgb.astype('float32')/255
    r,g,b=f.transpose(2,0,1)
    hsv=rgb2hsv(f); lab=rgb2lab(f)
    # Colour features only: do not transfer metre-scale texture or road distance
    # from the sub-metre scene to the coarse whole-region imagery.
    return np.stack([r,g,b,hsv[:,:,0],hsv[:,:,1],hsv[:,:,2],lab[:,:,0]/100,
                     lab[:,:,1]/128,lab[:,:,2]/128,2*g-r-b,g/(r+.01),b/(g+.01)],axis=-1)

def training():
    """Aggregate previous scene labels onto the actual Esri grid, without guessing IDs."""
    OUT.mkdir(exist_ok=True)
    image=ROOT/'data/esri_world_imagery.tif'
    with rasterio.open(TEST/'output/full_classification/classified_regions.tif') as src:
        old=src.read(1); old_t=src.transform; old_crs=src.crs; old_bounds=src.bounds
    with rasterio.open(image) as src:
        bounds=transform_bounds(old_crs,src.crs,*old_bounds,densify_pts=21)
        win=from_bounds(*bounds,transform=src.transform)
        x=int(np.floor(win.col_off)); y=int(np.floor(win.row_off))
        w=int(np.ceil(win.col_off+win.width))-x; h=int(np.ceil(win.row_off+win.height))-y
        win=Window(x,y,w,h)
        rgb=src.read(window=win).transpose(1,2,0); t=src.window_transform(win); crs=src.crs
    fractions=np.zeros((8,h,w),'float32')
    for cls in range(1,9):
        reproject((old==cls).astype('float32'),fractions[cls-1],src_transform=old_t,src_crs=old_crs,
                  dst_transform=t,dst_crs=crs,resampling=Resampling.average)
    winner=fractions.argmax(axis=0)+1; purity=fractions.max(axis=0)
    keep=(purity>=.75)&np.isin(winner,[1,2,3,4])
    # Exclude partially covered bounding pixels and black imagery.
    keep[:1,:]=False; keep[-1:,:]=False; keep[:,:1]=False; keep[:,-1:]=False
    keep &= np.any(rgb>0,axis=-1)
    xx,yy=np.meshgrid(np.arange(w)+x,np.arange(h)+y)
    X=features(rgb)[keep]; Y=winner[keep]
    counts={NAMES[c]:int((Y==c).sum()) for c in (1,2,3,4)}
    assert min(counts.values())>=20, f'Insufficient resolution-matched examples: {counts}'
    held=(((xx[keep]//8)*3+yy[keep]//8)%5)==0
    assert set(Y[~held])=={1,2,3,4}
    model=RandomForestClassifier(n_estimators=160,max_depth=14,min_samples_leaf=3,
             class_weight='balanced_subsample',n_jobs=2,random_state=20261015)
    model.fit(X[~held],Y[~held]); prediction=model.predict(X[held])
    agreement={'description':'Spatial-block agreement with transferred scene labels, NOT independent field accuracy',
               'held_samples':int(held.sum()),'classes':[1,2,3,4],
               'confusion_matrix':confusion_matrix(Y[held],prediction,labels=[1,2,3,4]).tolist()}
    model.fit(X,Y)
    joblib.dump(model,OUT/'broad_landcover_model.joblib',compress=3)
    np.savez_compressed(OUT/'training_samples.npz',X=X,labels=Y,pixel_x=xx[keep],pixel_y=yy[keep],held=held)
    report={'source_classification_sha256':digest(TEST/'output/full_classification/classified_regions.tif'),
            'image_sha256':digest(image),'source_window':[x,y,w,h],'purity_minimum':.75,
            'counts':counts,'features':'RGB, HSV, Lab, excess green and visible ratios',
            'classification_classes':NAMES,'spatial_label_agreement':agreement,
            'limitations':['Training labels come from one small scene and are not surveyed ground truth',
                'Performance over the rest of Bhadra is unvalidated; every automatic label needs review',
                'No reliable individual buildings, industrial structures or roads at this image resolution',
                'No NIR, elevation or road-distance features are used']}
    save_json(OUT/'training_report.json',report)
    print(json.dumps(report),flush=True)
    return model

def polygons_only(g):
    if g.geom_type in ('Polygon','MultiPolygon'): return g
    return unary_union([polygons_only(p) for p in getattr(g,'geoms',[]) if 'Polygon' in p.geom_type or p.geom_type=='GeometryCollection'])

def compose(rgb,transform,crs,aoi):
    manifest=json.loads((CACHE/'manifest.json').read_text())
    assert manifest['image_sha256']==digest(ROOT/'data/esri_world_imagery.tif')
    assert manifest['aoi_sha256']==digest(ROOT/'data/bhadra_boundary.geojson')
    assert all((CACHE/f'tile_{j["tile"]}.json').exists() for j in manifest['jobs']), 'SAM tiles incomplete'
    valid=rasterize([(aoi,1)],out_shape=rgb.shape[:2],transform=transform,all_touched=True,dtype='uint8')>0
    has_image=np.any(rgb>0,axis=-1)
    proposals=[]; rejected=0
    global_meta=json.loads((CACHE/'global.json').read_text())
    assert global_meta['image_sha256']==manifest['image_sha256']
    with np.load(CACHE/'global.npz') as arrays:
        for p in global_meta['masks']:
            if p['area_px']<40 or p['area_px']>rgb.shape[0]*rgb.shape[1]*.85:
                rejected+=1; continue
            proposals.append({**p,'mask':arrays[p['key']].copy(),'proposal':f'global_{p["key"]}'})
    for job in manifest['jobs']:
        i=job['tile']; records=json.loads((CACHE/f'tile_{i}.json').read_text())['masks']
        with np.load(CACHE/f'tile_{i}.npz') as arrays:
            for p in records:
                if p['internal_edge'] or p['area_px']<40 or p['area_px']>1024*1024*.85:
                    rejected+=1; continue
                proposals.append({**p,'mask':arrays[p['key']].copy(),'proposal':f'tile_{i}_{p["key"]}'})
    proposals.sort(key=lambda m:m['area_px'],reverse=True)
    labels=np.zeros(rgb.shape[:2],'int32'); metadata={}; next_id=1
    for p in proposals:
        x,y,w,h=p['bbox']; region=p['mask']&valid[y:y+h,x:x+w]&has_image[y:y+h,x:x+w]
        if not region.any(): continue
        view=labels[y:y+h,x:x+w]
        view[region]=next_id
        metadata[next_id]={'origin':'SAM ViT-H','proposal':p['proposal'],'sam_score':p['sam_score']}
        next_id+=1
    del proposals
    components=connected(labels,background=0,connectivity=1)
    sizes=np.bincount(components.ravel()); tiny=sizes<16; tiny[0]=False
    labels[tiny[components]]=0
    del components
    gaps=valid&has_image&(labels==0)
    gap_percent=100*int(gaps.sum())/max(1,int(valid.sum()))
    print(f'SAM composition: {len(metadata)} retained proposals; {gap_percent:.1f}% image-edge completion',flush=True)
    # SAM is not exhaustive. Keep conventional gap completion explicit in origin.
    edge=felzenszwalb(rgb,scale=350,sigma=.9,min_size=40,channel_axis=-1)
    gap_start=next_id
    labels[gaps]=edge[gaps].astype('int32')+gap_start
    missing_id=gap_start+int(edge.max())+1
    labels[valid&~has_image]=missing_id
    labels[~valid]=0
    final=connected(labels,background=0,connectivity=1).astype('int32')
    ids,first=np.unique(final,return_index=True)
    parents={int(i):int(labels.ravel()[at]) for i,at in zip(ids,first) if i}
    rows=[]
    for geom,value in shapes(final,mask=valid,transform=transform,connectivity=4):
        i=int(value); parent=parents[i]
        g=polygons_only(make_valid(shape(geom).intersection(aoi)))
        if g.is_empty or g.area<=0: continue
        if parent==missing_id: meta={'origin':'No valid imagery','proposal':'no_imagery','sam_score':None}
        elif parent>=gap_start: meta={'origin':'Image-edge gap completion','proposal':f'gap_{parent-gap_start}','sam_score':None}
        else: meta=metadata[parent]
        rows.append({'segment_id':i,**meta,'geometry':g})
    frame=gpd.GeoDataFrame(rows,crs=crs)
    assert frame.segment_id.is_unique and frame.is_valid.all()
    report={'completed_sam_tiles':len(manifest['jobs']),'whole_image_context_pass':True,
            'global_inference_size':global_meta['inference_size'],
            'global_context_pixel_size_mercator_m':[abs(transform.a)*rgb.shape[1]/global_meta['inference_size'][0],
                abs(transform.e)*rgb.shape[0]/global_meta['inference_size'][1]],
            'sam_proposals_retained':len(metadata),
            'sam_proposals_rejected':rejected,'gap_completion_pixel_percent':gap_percent,
            'regions_by_origin':frame.origin.value_counts().to_dict()}
    return frame,final,valid,report

def style(path,names,colors):
    root=ET.Element('qgis',version='3.40',styleCategories='Symbology')
    renderer=ET.SubElement(root,'renderer-v2',type='categorizedSymbol',attr='class_id',symbollevels='0')
    cats=ET.SubElement(renderer,'categories'); symbols=ET.SubElement(renderer,'symbols')
    for code,name in names.items():
        ET.SubElement(cats,'category',value=str(code),symbol=str(code),label=name,render='true',type='long')
        symbol=ET.SubElement(symbols,'symbol',name=str(code),type='fill',alpha='1')
        layer=ET.SubElement(symbol,'layer',**{'class':'SimpleFill','enabled':'1','pass':'0','locked':'0'})
        opts=ET.SubElement(layer,'Option',type='Map')
        for key,value in {'color':colors[code]+',65','outline_color':colors[code]+',210','outline_width':'.12',
                'outline_width_unit':'MM','outline_style':'solid','style':'solid'}.items():
            ET.SubElement(opts,'Option',name=key,value=value,type='QString')
    ET.ElementTree(root).write(path,encoding='utf-8',xml_declaration=True)

def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--training-only',action='store_true'); args=parser.parse_args()
    if not args.training_only and not (CACHE/'global.json').exists():
        subprocess.run([sys.executable,'-u',str(ROOT/'segment_bhadra.py'),'--global-only'],check=True)
    model=training()
    if args.training_only: return
    save_json(ROOT/'progress.json',{'phase':'Composing SAM regions and classifying broad land cover'})
    with rasterio.open(ROOT/'data/esri_world_imagery.tif') as src:
        rgb=src.read().transpose(1,2,0); transform=src.transform; crs=src.crs; profile=src.profile.copy()
    boundary=gpd.read_file(ROOT/'data/bhadra_boundary.geojson').to_crs(crs)
    aoi=boundary.geometry.union_all()
    frame,ids,valid,segmentation=compose(rgb,transform,crs,aoi)
    n=int(ids.max())+1; scores=np.zeros((n,4),'float64'); votes=np.zeros((n,4),'int64')
    counts=np.bincount(ids.ravel(),minlength=n)
    green=np.zeros(n); water=np.zeros(n)
    # RGB-only warning, not a validated cloud mask. Bright neutral surfaces can
    # also be soil/concrete; conservative uncertainty is safer than invented land cover.
    bright_core=(rgb.min(axis=-1)>170)&(rgb.mean(axis=-1)>195)&((rgb.max(axis=-1).astype('int16')-rgb.min(axis=-1))<40)
    bright=ndi.binary_dilation(bright_core,iterations=2)
    shadow=ndi.binary_dilation(bright_core,iterations=12)&(rgb.mean(axis=-1)<65)
    bright_fraction=np.bincount(ids.ravel(),weights=bright.ravel(),minlength=n)/np.maximum(counts,1)
    shadow_fraction=np.bincount(ids.ravel(),weights=shadow.ravel(),minlength=n)/np.maximum(counts,1)
    for y in range(0,len(rgb),128):
        block=rgb[y:y+128]; X=features(block).reshape(-1,12); ll=ids[y:y+128].ravel()
        pp=model.predict_proba(X); win=pp.argmax(axis=1)
        for c in range(4):
            scores[:,c]+=np.bincount(ll,weights=pp[:,c],minlength=n)
            votes[:,c]+=np.bincount(ll,weights=win==c,minlength=n).astype('int64')
        r,g,b=block.astype('float32').transpose(2,0,1)/255
        green+=np.bincount(ll,weights=((2*g-r-b>.045)&(g>r*1.04)).ravel(),minlength=n)
        water+=np.bincount(ll,weights=((r<g*.97)&(b>g*.68)&(r<.42)&(g<.55)).ravel(),minlength=n)
    scores/=np.maximum(counts[:,None],1); vote_fraction=votes/np.maximum(counts[:,None],1)
    green/=np.maximum(counts,1); water/=np.maximum(counts,1)
    labels=np.zeros(n,'uint8'); records=[]
    for row in frame.itertuples():
        i=row.segment_id; win=int(scores[i].argmax()); suggestion=int(model.classes_[win]); cls=suggestion
        score=float(scores[i,win]); dominance=float(vote_fraction[i,win]); order=np.sort(scores[i]); margin=float(order[-1]-order[-2])
        reason='Whole-region estimate from resolution-matched scene examples; requires review'
        if row.origin=='No valid imagery': cls=8; reason='No valid source imagery'
        elif bright_fraction[i]>.10 or shadow_fraction[i]>.30:
            cls=8; reason='Bright neutral surface / possible cloud, or nearby dark shadow; RGB interpretation ambiguous'
        elif score<.60 or dominance<.65 or margin<.18: cls=8; reason='Weak or mixed RGB evidence'
        elif cls==1 and water[i]<.65: cls=8; reason='Water-like vote without consistent visible-band water evidence'
        elif cls==4 and green[i]>.50: cls=8; reason='Ground-like vote conflicts with vegetation signal'
        labels[i]=cls
        records.append({'class_id':cls,'class_name':NAMES[cls],'suggested_class':NAMES[suggestion],
            'model_score':score,'vote_fraction':dominance,'vote_margin':margin,'review_required':1,
            'bright_surface_fraction':float(bright_fraction[i]),'near_cloud_shadow_fraction':float(shadow_fraction[i]),
            'review_reason':reason,'method':'Resolution-matched RGB random forest + region voting'})
    for key in records[0]: frame[key]=[r[key] for r in records]
    metric=frame.to_crs(32643)
    frame['area_m2']=metric.geometry.area.to_numpy()
    points=metric.geometry.representative_point().to_crs(4326)
    frame['latitude']=points.y.to_numpy(); frame['longitude']=points.x.to_numpy()
    target=OUT/'bhadra_sam_vit_h_classification.gpkg'
    frame.to_file(target,layer='classified_regions',driver='GPKG')
    boundary.to_file(target,layer='bhadra_boundary',driver='GPKG')
    frame[frame.class_id==4].to_file(target,layer='open_ground',driver='GPKG')
    combined=frame.rename(columns={'class_id':'source_class_id','class_name':'source_class_name'}).copy()
    combined['class_id']=combined.source_class_id.where(combined.source_class_id.isin([3,4]),1)
    combined_names={1:'Combined features + uncertain',3:NAMES[3],4:NAMES[4]}
    combined['class_name']=combined.class_id.map(combined_names)
    combined.to_file(target,layer='combined_regions',driver='GPKG')
    centre_valid=rasterize([(aoi,1)],out_shape=ids.shape,transform=transform,dtype='uint8')>0
    classified=labels[ids]; classified[~centre_valid]=0
    profile.update(count=1,dtype='uint8',nodata=0,compress='lzw')
    with rasterio.open(OUT/'classified_regions.tif','w',**profile) as dst:
        dst.write(classified,1); dst.update_tags(classes=json.dumps(NAMES),status='Provisional RGB interpretation at roughly 19m sampling')
    style(OUT/'classified_regions.qml',NAMES,COLORS)
    style(OUT/'combined_regions.qml',combined_names,{1:'23,190,207',3:COLORS[3],4:COLORS[4]})
    # Independent saved-geometry coverage and raster checks.
    saved=gpd.read_file(target,layer='classified_regions')
    assert (saved.area_m2>0).all()
    stored_points=gpd.GeoSeries(gpd.points_from_xy(saved.longitude,saved.latitude),crs=4326).to_crs(saved.crs)
    assert all(g.buffer(.01).covers(p) for g,p in zip(saved.geometry,stored_points)), 'Coordinate outside its region'
    saved_open=gpd.read_file(target,layer='open_ground')
    assert set(saved_open.segment_id)==set(saved.loc[saved.class_id==4,'segment_id'])
    saved_combined=gpd.read_file(target,layer='combined_regions')
    assert len(saved_combined)==len(saved) and saved_combined.segment_id.is_unique
    union=saved.geometry.union_all()
    overlap=float(saved.area.sum()-union.area); gap=float(aoi.difference(union).area); outside=float(union.difference(aoi).area)
    assert saved.is_valid.all() and saved.segment_id.is_unique
    assert abs(overlap)<.1 and gap<.1 and outside<.1, (overlap,gap,outside)
    rebuilt=rasterize(list(zip(saved.geometry,saved.class_id)),out_shape=classified.shape,transform=transform,dtype='uint8')
    assert np.array_equal(rebuilt,classified), f'Raster/vector mismatch: {(rebuilt!=classified).sum()}'
    report={'passed':True,'area_km2':float(metric.geometry.area.sum()/1e6),'region_count':len(saved),
        'counts_by_class':saved.class_name.value_counts().to_dict(),
        'area_km2_by_class':(saved.groupby('class_name').area_m2.sum()/1e6).to_dict(),
        'uncertain_area_percent':float(saved.loc[saved.class_id==8,'area_m2'].sum()/saved.area_m2.sum()*100),
        'segmentation':segmentation,'source_pixel_size_mercator_m':list((abs(transform.a),abs(transform.e))),
        'overlap_m2_mercator':overlap,'uncovered_m2_mercator':gap,'outside_m2_mercator':outside,
        'vector_raster_identical':True,'interior_coordinates_verified':True,'open_ground_subset_verified':True,
        'model':'SAM ViT-H for boundaries; separate RGB forest for labels',
        'image_sha256':digest(ROOT/'data/esri_world_imagery.tif'),
        'aoi_sha256':digest(ROOT/'data/bhadra_boundary.geojson'),
        'limitations':json.loads((OUT/'training_report.json').read_text())['limitations']+
            ['SAM does not supply semantic class names','Gaps are completed by image-edge segmentation, with origin retained',
             'Visible clouds occur in the source; RGB bright-surface/shadow warnings are conservative and not a validated cloud mask',
             'The saved project boundary is used, not a newly verified official reserve boundary',
             'Merged output includes uncertain regions and must not be interpreted as confirmed land cover']}
    save_json(OUT/'verification.json',report)
    save_json(ROOT/'progress.json',{'phase':'Verified GeoPackage complete','region_count':len(saved),'passed':True})
    subprocess.run([sys.executable,'-u',str(ROOT/'finalize_cloud_review.py')],check=True)
    print((OUT/'verification.json').read_text(),flush=True)

if __name__=='__main__': main()
