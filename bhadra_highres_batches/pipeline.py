"""Original-resolution SAM/region/scene-classifier pipeline, spatially parameterized.

The original numbered visual-review IDs are NEVER transferred to new batches.
Reviewed references only act through their actual georeferenced intersections.
"""
import json
import time
import numpy as np
import geopandas as gpd
import rasterio
from rasterio.features import rasterize,shapes
from scipy import ndimage as ndi
from skimage.measure import label as connected
from skimage.segmentation import felzenszwalb
from skimage.color import rgb2hsv,rgb2lab
from shapely.geometry import shape,box,Point
from shapely import make_valid
from common import *

reference=load_original('classify_full_rectangle')
composition=load_original('compose_full_rectangle')
NAMES=reference.NAMES

def burn(items,shape_,transform):
    items=list(items)
    return rasterize(items,out_shape=shape_,transform=transform,dtype='uint8') if items else np.zeros(shape_,'uint8')

def context(transform,shape_):
    h,w=shape_; left,top=transform*(0,0); right,bottom=transform*(w,h)
    extent=box(left,bottom,right,top)
    path=TEST/'output/reviewed_with_industrial.gpkg'
    def read(layer):
        frame=gpd.read_file(path,layer=layer).to_crs(32643)
        return frame[frame.intersects(extent)].copy()
    reviewed=read('reviewed_classes'); buildings=read('buildings_reference'); structures=read('industrial_structures')
    roads=gpd.read_file(TEST/'output/full_classification/context.gpkg',layer='reviewed_road_regions').to_crs(32643)
    roads=roads[roads.intersects(extent.buffer(60))]
    ref=burn(zip(reviewed.geometry,reviewed.class_id),shape_,transform)
    footprints=[(g,5) for g in buildings.geometry]+[(r.geometry,5 if r.subtype=='Roofed building' else 6) for r in structures.itertuples()]
    fixed=burn(footprints,shape_,transform)
    road_core=ndi.binary_erosion(burn([(g,1) for g in roads.geometry],shape_,transform)>0,iterations=2)
    road_zone=burn([(g.buffer(6),1) for g in roads.geometry],shape_,transform)>0
    road_distance=(np.minimum(ndi.distance_transform_edt(~road_core)*abs(transform.a),50)/50).astype('float32') if road_core.any() else np.ones(shape_,'float32')
    return {'reference':ref,'fixed':fixed,'footprints':footprints,'road_zone':road_zone,
            'road_distance':road_distance,'supported_road_polygons':len(roads),'accepted_footprints':len(footprints)}

def features(rgb,road_distance):
    f=rgb.astype('float32')/255; r,g,b=f.transpose(2,0,1)
    hsv=rgb2hsv(f); lab=rgb2lab(f); intensity=f.mean(2)
    texture=[]
    for size in (3,9,21):
        mean=ndi.uniform_filter(intensity,size=size)
        texture.append(np.sqrt(np.maximum(0,ndi.uniform_filter(intensity**2,size=size)-mean**2)))
    return np.stack([r,g,b,hsv[:,:,0],hsv[:,:,1],hsv[:,:,2],lab[:,:,0]/100,lab[:,:,1]/128,
        lab[:,:,2]/128,2*g-r-b,g/(r+.01),b/(g+.01),*texture,road_distance],axis=-1).astype('float32')

def proposals(job,sam,rgb):
    import torch
    folder=batch_dir(job['batch_id']); cache=folder/'sam'; cache.mkdir(exist_ok=True)
    manifest=json.loads(MANIFEST.read_text())
    identity={'image_sha256':digest(folder/'esri_rgb.tif'),'checkpoint_sha256':manifest['checkpoint_sha256'],
        'params':PARAMS,'tiles':TILES,'image_size':[WIDTH,HEIGHT]}
    # JSON turns tuples into lists; normalize for resumable equality checks.
    identity=json.loads(json.dumps(identity))
    if (cache/'identity.json').exists(): assert json.loads((cache/'identity.json').read_text())==identity
    else: atomic_json(cache/'identity.json',identity)
    windows=[('global',(0,0,WIDTH,HEIGHT))]+[(f'tile_{i}',window) for i,window in enumerate(TILES)]
    all_proposals=[]
    for label,(x,y,w,h) in windows:
        meta_path=cache/(label+'.json'); masks_path=cache/(label+'.npz')
        if not (meta_path.exists() and masks_path.exists()):
            state(job['batch_id'],'processing',f'SAM ViT-H {label}')
            print(f'{job["batch_id"]}: SAM {label}',flush=True); started=time.monotonic()
            with torch.inference_mode(): masks=sam.mask_generator.generate(rgb[y:y+h,x:x+w])
            arrays={}; rows=[]
            for j,m in enumerate(masks):
                yy,xx=np.where(m['segmentation'])
                if not len(xx): continue
                x0=int(xx.min()); x1=int(xx.max())+1; y0=int(yy.min()); y1=int(yy.max())+1
                key=f'm{j}'; arrays[key]=m['segmentation'][y0:y1,x0:x1].copy()
                internal=(x>0 and x0<=2) or (y>0 and y0<=2) or (x+w<WIDTH and x1>=w-2) or (y+h<HEIGHT and y1>=h-2)
                rows.append({'key':key,'bbox':[x+x0,y+y0,x1-x0,y1-y0],'area_px':len(xx),
                    'sam_score':float(m['predicted_iou']),'stability':float(m['stability_score']),
                    'internal_edge':bool(internal),'global':label=='global','source_key':label+'_'+key})
            del masks
            tmp=masks_path.with_suffix('.tmp')
            with tmp.open('wb') as stream: np.savez_compressed(stream,**arrays)
            tmp.replace(masks_path)
            atomic_json(meta_path,{'masks':rows,'seconds':time.monotonic()-started})
            print(f'{job["batch_id"]}: saved {label}, {len(rows)} masks',flush=True)
            del arrays
        with np.load(masks_path) as arrays:
            for row in json.loads(meta_path.read_text())['masks']:
                if not row['global'] and (row['internal_edge'] or row['area_px']>1024*768*.65 or row['area_px']<40): continue
                all_proposals.append({**row,'mask':arrays[row['key']].copy()})
    return all_proposals

def compose(rgb,transform,props,ctx):
    h,w=rgb.shape[:2]; valid=np.zeros((h,w),bool); valid[2:-2,2:-2]=True
    labels=np.zeros((h,w),'int32'); metadata={}; next_id=1
    for p in sorted(props,key=lambda p:p['area_px'],reverse=True):
        x,y,pw,ph=p['bbox']; mask=p['mask']; view=labels[y:y+ph,x:x+pw]
        present,counts=np.unique(view[mask],return_counts=True); nonzero=present>0
        if nonzero.any():
            dominant=int(present[nonzero][np.argmax(counts[nonzero])]); common=int(counts[nonzero].max())
            if common/p['area_px']>.9 and .85<metadata[dominant]['area_px']/p['area_px']<1.15: continue
        view[mask]=next_id
        metadata[next_id]={'source_key':p['source_key'],'origin':'SAM automatic',
            'sam_score':p['sam_score'],'area_px':p['area_px']}; next_id+=1
    labels[~valid]=0
    components=connected(labels,background=0,connectivity=1)
    sizes=np.bincount(components.ravel()); tiny=sizes<40; tiny[0]=False
    labels[tiny[components]]=0
    protected=set()
    for index,(geom,cls) in enumerate(ctx['footprints']):
        mask=(burn([(geom,1)],(h,w),transform)>0)&valid
        if not mask.any(): continue
        labels[mask]=next_id; protected.add(next_id)
        metadata[next_id]={'source_key':f'accepted_spatial_footprint_{index}','origin':'Preserved footprint',
            'sam_score':None,'area_px':int(mask.sum())}; next_id+=1
    gaps=(labels==0)&valid; gap_percent=float(100*gaps.sum()/valid.sum())
    edge=felzenszwalb(rgb,scale=350,sigma=.9,min_size=100,channel_axis=-1)
    gap_start=next_id; labels[gaps]=edge[gaps].astype('int32')+gap_start
    cleanup=composition.merge_slivers(labels,valid,protected)
    final=connected(labels,background=0,connectivity=1).astype('int32')
    ids,first=np.unique(final,return_index=True)
    parents={int(i):int(labels.ravel()[at]) for i,at in zip(ids,first) if i}
    rows=[]
    for geom,value in shapes(final,mask=valid,transform=transform,connectivity=4):
        i=int(value); parent=parents[i]
        meta=metadata[parent] if parent<gap_start else {'origin':'Edge-based gap completion','source_key':f'edge_gap_{parent-gap_start}','sam_score':None}
        g=polygon_only(make_valid(shape(geom)))
        rows.append({'segment_id':i,'origin':meta['origin'],'proposal_id':meta['source_key'],
            'sam_score':meta['sam_score'],'area_m2':g.area,'geometry':g})
    return gpd.GeoDataFrame(rows,crs=32643),final,{'gap_completion_pixel_percent':gap_percent,'sliver_cleanup':cleanup}

def classify(rgb,ids,regions,transform,ctx,model):
    X=features(rgb,ctx['road_distance']).reshape(-1,16)
    assert model.n_features_in_==16 and np.isfinite(X).all()
    n=int(ids.max())+1; flat=ids.ravel(); counts=np.bincount(flat,minlength=n)
    scores=np.zeros((n,9),'float64'); votes=np.zeros((n,9),'int64')
    for start in range(0,len(X),180000):
        stop=min(len(X),start+180000); pp=model.predict_proba(X[start:stop]); ll=flat[start:stop]
        win=model.classes_[pp.argmax(1)]
        for col,cls in enumerate(model.classes_):
            scores[:,cls]+=np.bincount(ll,weights=pp[:,col],minlength=n)
            votes[:,cls]+=np.bincount(ll,weights=win==cls,minlength=n).astype('int64')
    scores/=np.maximum(counts[:,None],1); votes_fraction=votes/np.maximum(counts[:,None],1)
    def fraction(mask): return np.bincount(flat,weights=mask.ravel(),minlength=n)/np.maximum(counts,1)
    ref_fractions=np.stack([fraction(ctx['reference']==c) for c in range(9)],axis=1)
    fixed_fractions=np.stack([fraction(ctx['fixed']==c) for c in range(9)],axis=1)
    r,g,b=rgb.astype('float32').transpose(2,0,1)/255; exg=2*g-r-b
    road_fraction=fraction(ctx['road_zone']); green_fraction=fraction((exg>.045)&(g>r*1.04))
    water_fraction=fraction((r<g*.97)&(b>g*.72)&(r<.36)&(g<.48))
    near=fraction(ndi.distance_transform_edt(ctx['fixed']!=5)*abs(transform.a)<15) if (ctx['fixed']==5).any() else np.zeros(n)
    records=[]
    for row in regions.itertuples():
        i=row.segment_id; raw=int(scores[i].argmax()); order=np.sort(scores[i]); margin=float(order[-1]-order[-2])
        score=float(scores[i,raw]); dominance=float(votes_fraction[i,raw]); cls=raw
        method='RGB/texture random forest + segment voting'; status='Automatic estimate'; reason=''
        prior=int(np.argmax(ref_fractions[i,1:5]))+1; overlap=float(ref_fractions[i,prior])
        footprint=int(np.argmax(fixed_fractions[i,5:7]))+5
        if fixed_fractions[i,footprint]>.95:
            cls=footprint; method='Accepted footprint'; status='Reference footprint'
        elif overlap>=.65 and (prior!=1 or water_fraction[i]>.60):
            cls=prior; method='Reviewed-region overlap'; status='Reviewed overlap'
            if prior==4 and road_fraction[i]>.55 and votes_fraction[i,7]>.45:
                cls=7; method='Road context + forest vote'; status='Automatic estimate'
        else:
            if dominance<.60 or score<.47 or margin<.10:
                cls=8; reason='Mixed or weak spectral/texture votes'
            elif raw==1 and water_fraction[i]<.60:
                cls=8; reason='Water-like model vote lacks enough RGB water evidence'
            elif raw==7 and road_fraction[i]<.30:
                cls=8; reason='Paved-looking surface outside supported road corridor'
            elif raw==5:
                rect=row.geometry.minimum_rotated_rectangle
                rectangularity=row.geometry.area/rect.area if rect.area else 0
                corners=list(rect.exterior.coords)
                sides=[Point(corners[j]).distance(Point(corners[j+1])) for j in range(4)]
                aspect=max(sides)/max(min(sides),1e-6)
                if not (score>.78 and dominance>.85 and 12<row.area_m2<2500 and rectangularity>.72
                        and green_fraction[i]<.20 and aspect<4 and near[i]>.4):
                    cls=8; reason='Roof-like appearance without a reliable footprint'
        if method=='Reviewed-region overlap' and cls==4 and green_fraction[i]>.65:
            cls=8; reason='Broad ground reference conflicts with strong vegetation signal'
        if cls==8: status='Needs review'
        records.append({'class_id':cls,'class_name':NAMES[cls],'suggested_class':NAMES[raw],
            'model_score':score,'vote_fraction':dominance,'vote_margin':margin,
            'method':method,'review_status':status,'review_reason':reason})
    result=regions.copy()
    for key in records[0]: result[key]=[r[key] for r in records]
    return result

def run_batch(job,sam,model):
    folder=batch_dir(job['batch_id']); target=folder/'classified.gpkg'
    if target.exists() and (folder/'verification.json').exists():
        report=json.loads((folder/'verification.json').read_text())
        assert report['gpkg_sha256']==digest(target) and report['passed']
        return report
    with rasterio.open(folder/'esri_rgb.tif') as src:
        rgb=src.read().transpose(1,2,0); transform=src.transform; profile=src.profile.copy()
    ctx=context(transform,rgb.shape[:2]); props=proposals(job,sam,rgb)
    state(job['batch_id'],'processing','Composing full-resolution SAM regions')
    regions,ids,segmentation=compose(rgb,transform,props,ctx); del props
    state(job['batch_id'],'processing','Original 16-feature classifier and region rules')
    frame=classify(rgb,ids,regions,transform,ctx,model)
    owned=owned_geometry(job['batch_id'])
    frame=frame[frame.intersects(owned)].copy()
    frame.geometry=frame.geometry.map(lambda g:polygon_only(make_valid(g.intersection(owned))))
    frame=frame[~frame.is_empty & (frame.area>0)].copy()
    frame=normalize(frame,job['batch_id'],transform.a)
    checks=verify_regions(frame,owned)
    frame.to_file(target,layer='classified_regions',driver='GPKG')
    saved=gpd.read_file(target,layer='classified_regions'); verify_regions(saved,owned)
    classified=rasterize(zip(saved.geometry,saved.class_id),out_shape=rgb.shape[:2],transform=transform,dtype='uint8')
    expected=rasterize([(owned,1)],out_shape=rgb.shape[:2],transform=transform,dtype='uint8')>0
    assert np.array_equal(classified>0,expected)
    profile.update(count=1,dtype='uint8',nodata=0)
    with rasterio.open(folder/'classes.tif','w',**profile) as dst: dst.write(classified,1)
    report={'passed':True,'batch_id':job['batch_id'],'geometry':checks,'segmentation':segmentation,
        'counts_by_class':saved.class_name.value_counts().to_dict(),'area_m2_by_class':saved.groupby('class_name').area_m2.sum().to_dict(),
        'context':{k:ctx[k] for k in ('supported_road_polygons','accepted_footprints')},
        'image_sha256':digest(folder/'esri_rgb.tif'),'gpkg_sha256':digest(target),
        'classifier_sha256':digest(TEST/'output/full_classification/scene_random_forest.joblib'),
        'pipeline_sha256':digest(Path(__file__)),'pixel_size_m':[transform.a,-transform.e],
        'limitations':['Same scene classifier, not independent whole-AOI accuracy',
            'Scene-specific numbered overrides are not transferred','Road/roof/industrial labels need supported local context or new visual review',
            'SAM and explicitly tagged image-edge gap completion remain distinct','Batch-edge objects can be split; core partitions prevent overlaps']}
    atomic_json(folder/'verification.json',report)
    return report
