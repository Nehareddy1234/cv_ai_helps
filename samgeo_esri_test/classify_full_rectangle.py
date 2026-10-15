"""Scene-specific object classification; never changes the input segmentation.

Reviewed RGB examples train a random forest. Segment voting is combined with
reviewed overlaps, protected footprints and visually supported road corridors.
All scores measure evidence/agreement, NOT calibrated correctness probabilities.
"""
from pathlib import Path
import hashlib
import json
import xml.etree.ElementTree as ET
import numpy as np
import pandas as pd
import geopandas as gpd
import rasterio
from rasterio.features import rasterize
from scipy import ndimage as ndi
from skimage.color import rgb2hsv, rgb2lab
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, confusion_matrix
from shapely.geometry import LineString, Point
import joblib
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from skimage.segmentation import find_boundaries

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'output/full_classification'
OUT.mkdir(exist_ok=True)
NAMES={1:'Water',2:'Trees / dense woody vegetation',3:'Crops / grass / low vegetation',
       4:'Bare soil / rock / sparse ground',5:'Buildings / roofs',
       6:'Industrial / engineered structures',7:'Roads / tracks / paved surfaces',8:'Uncertain / mixed'}
COLORS={1:'#2489ef',2:'#238443',3:'#a4d65e',4:'#c88c47',5:'#f04d53',6:'#b54dd3',7:'#f5cd39',8:'#9c9c9c'}
# Explicit image review of numbered polygons in audit_ids_*.png. These labels
# are valid ONLY for this exact segmentation and are not inferred from SAM score.
REVIEW_SOURCE_SHA='51c70bd5096a7e1397f42a158b7666c969a9b0a536e6421e74b88afd78371bd6'
VISUAL_REVIEW={
 1:{'ids':[2066,2168,2190,2222,2263,2277,2370,2389,2484,2497,2578,1835],
    'reason':'Flat green treatment-basin water/algal surface, or white water at spillway (1835)'},
 2:{'ids':[634,1001,2350,1746,1812,1873,1548,1819,1707,1881,1943,1981,2004],
    'reason':'Visible woody canopy patch in numbered source-image audit'},
 3:{'ids':[157,1818], 'reason':'Visible low vegetation / managed planted patch'},
 4:{'ids':[562,1174,1180,1196,1249,1338,1470,1482,1714,1630,1455,2275,2363,2468,2561,2567,2471,2374],
    'reason':'Exposed riverbank/bar, rock, or dry sparse treatment-bed surface; not roof'},
 6:{'ids':[1536,1610,1677,1708,1754,1798,1932,1920,1953,2129,2212,2197],
    'reason':'Visible dam/spillway civil structure; not a roofed building'},
 7:{'ids':[20,179,260,186,427,569,1103,1876,2047],
    'reason':'Visible paved road, bridge deck or connected facility access pavement'},
}
# Additional visually interpreted water example, green treatment basin. RGB only.
EXAMPLE_POINTS={1:[(1330,1225,6)],2:[],3:[],4:[],5:[],7:[]}

def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()

def style():
    root=ET.Element('qgis',version='3.40',styleCategories='Symbology')
    renderer=ET.SubElement(root,'renderer-v2',type='categorizedSymbol',attr='class_id',symbollevels='0')
    categories=ET.SubElement(renderer,'categories'); symbols=ET.SubElement(renderer,'symbols')
    for k,name in NAMES.items():
        ET.SubElement(categories,'category',value=str(k),symbol=str(k),label=name,render='true',type='long')
        symbol=ET.SubElement(symbols,'symbol',name=str(k),type='fill',alpha='1')
        layer=ET.SubElement(symbol,'layer',**{'class':'SimpleFill','enabled':'1','pass':'0','locked':'0'})
        opts=ET.SubElement(layer,'Option',type='Map')
        c=','.join(str(int(COLORS[k][i:i+2],16)) for i in (1,3,5))
        for key,value in {'color':c+(','+'14' if k==8 else ',48'),'outline_color':c+',230',
            'outline_width':'.16','outline_width_unit':'MM','outline_style':'solid',
            'style':'solid','joinstyle':'round'}.items():
            ET.SubElement(opts,'Option',name=key,value=value,type='QString')
    ET.ElementTree(root).write(OUT/'classified_regions.qml',encoding='utf-8',xml_declaration=True)

def main():
    source_path=ROOT/'output/full_rectangle/unlabelled_regions.gpkg'
    source_sha=digest(source_path)
    assert source_sha==REVIEW_SOURCE_SHA, 'Review labels belong to a different segmentation'
    regions=gpd.read_file(source_path,layer='regions').sort_values('segment_id').reset_index(drop=True)
    with rasterio.open(ROOT/'data/esri_test_aligned.tif') as src:
        rgb=src.read().transpose(1,2,0); t=src.transform; crs=src.crs; profile=src.profile.copy()
    with rasterio.open(ROOT/'output/full_rectangle/unlabelled_regions.tif') as src: ids=src.read(1)
    valid=ids>0; h,w=ids.shape; n=int(ids.max())+1
    reviewed=gpd.read_file(ROOT/'output/reviewed_with_industrial.gpkg',layer='reviewed_classes')
    reference=rasterize(list(zip(reviewed.geometry,reviewed.class_id)),out_shape=ids.shape,transform=t,dtype='uint8')
    buildings=gpd.read_file(ROOT/'output/reviewed_with_industrial.gpkg',layer='buildings_reference')
    structures=gpd.read_file(ROOT/'output/reviewed_with_industrial.gpkg',layer='industrial_structures')
    fixed=rasterize([(g,5) for g in buildings.geometry]+[(r.geometry,5 if r.subtype=='Roofed building' else 6)
        for r in structures.itertuples()],out_shape=ids.shape,transform=t,dtype='uint8')
    road_frames=regions[regions.segment_id.isin(VISUAL_REVIEW[7]['ids'])].copy()
    road_frames.to_file(OUT/'context.gpkg',layer='reviewed_road_regions',driver='GPKG')
    # Use actual visually reviewed region pixels instead of roughly digitized
    # centerlines. This corrects the initial context's alignment error.
    road_core=ndi.binary_erosion(np.isin(ids,VISUAL_REVIEW[7]['ids']),iterations=2)
    road_zone=rasterize([(g.buffer(6),1) for g in road_frames.geometry],out_shape=ids.shape,transform=t,dtype='uint8')>0
    road_distance=np.minimum(ndi.distance_transform_edt(~road_core)*abs(t.a),50).astype('float32')/50
    print('Extracting RGB, colour, multiscale texture and road-context features',flush=True)
    f=rgb.astype('float32')/255; r,g,b=f.transpose(2,0,1)
    hsv=rgb2hsv(f); lab=rgb2lab(f)
    intensity=f.mean(axis=2); exg=2*g-r-b
    feature_names=['red','green','blue','hue','saturation','value','lab_L','lab_a','lab_b','excess_green',
                   'green_red_ratio','blue_green_ratio','texture_3','texture_9','texture_21','road_distance']
    texture=[]
    for size in (3,9,21):
        mean=ndi.uniform_filter(intensity,size=size)
        texture.append(np.sqrt(np.maximum(0,ndi.uniform_filter(intensity**2,size=size)-mean**2)))
    features=np.stack([r,g,b,hsv[:,:,0],hsv[:,:,1],hsv[:,:,2],lab[:,:,0]/100,lab[:,:,1]/128,lab[:,:,2]/128,
        exg,g/(r+.01),b/(g+.01),*texture,road_distance],axis=-1).astype('float32')
    train_labels=np.zeros(ids.shape,'uint8')
    for cls in (1,2,3,4):
        clean=ndi.binary_erosion(reference==cls,iterations=3)
        if cls==1: clean &= (r<g)&(b>g*.68)
        if cls==2: clean &= (exg>.035)&(g>r)
        if cls==4: clean &= exg<.07
        train_labels[clean]=cls
    train_labels[ndi.binary_erosion(fixed==5,iterations=2)]=5
    # Road examples require low vegetation signal and are not taken from trees or water.
    road_samples=road_core&(exg<.06)&(intensity>.23)&(fixed==0)
    train_labels[road_samples]=7
    yy,xx=np.ogrid[:h,:w]
    for cls,points in EXAMPLE_POINTS.items():
        for x,y,radius in points: train_labels[(xx-x)**2+(yy-y)**2<=radius**2]=cls
    # Context-reviewed water basins and exposed bars teach the forest the
    # green-water and concrete/rock confusions observed in the first pass.
    for cls in (1,2,3,4,7):
        region_examples=ndi.binary_erosion(np.isin(ids,VISUAL_REVIEW[cls]['ids']),iterations=3)
        train_labels[region_examples&(fixed==0)]=cls
    train_labels[~valid]=0
    train_flat=train_labels.ravel(); X=features.reshape(-1,features.shape[-1])
    rng=np.random.default_rng(20261015)
    selected=[]
    for cls in (1,2,3,4,5,7):
        choices=np.flatnonzero(train_flat==cls)
        assert len(choices)>50, f'Insufficient training examples for {cls}'
        selected.append(rng.choice(choices,size=min(8000,len(choices)),replace=False))
    selected=np.concatenate(selected); ys=train_flat[selected]
    # A fixed spatial-block holdout tests label agreement, NOT independent field accuracy.
    rows=selected//w; cols=selected%w
    held=((rows//192)*3+cols//192)%5==0
    clf=RandomForestClassifier(n_estimators=120,max_depth=20,min_samples_leaf=6,
        class_weight='balanced_subsample',n_jobs=3,random_state=20261015)
    clf.fit(X[selected[~held]],ys[~held]); held_pred=clf.predict(X[selected[held]])
    validation={'description':'Spatial-block agreement with scene-interpreted labels, not field accuracy',
        'block_pixels':192,'train_samples':int((~held).sum()),'holdout_samples':int(held.sum()),
        'classes':clf.classes_.tolist(),'confusion_matrix':confusion_matrix(ys[held],held_pred,labels=clf.classes_).tolist(),
        'report':classification_report(ys[held],held_pred,output_dict=True,zero_division=0)}
    (OUT/'spatial_label_agreement.json').write_text(json.dumps(validation,indent=2))
    print('Fitting final forest; predicting all image pixels',flush=True)
    clf.fit(X[selected],ys)
    joblib.dump(clf,OUT/'scene_random_forest.joblib',compress=3)
    np.savez_compressed(OUT/'training_samples.npz',pixel_indices=selected,classes=ys,spatial_holdout=held)
    scores=np.zeros((n,9),dtype='float64'); votes=np.zeros((n,9),dtype='int64')
    flat_ids=ids.ravel(); counts=np.bincount(flat_ids,minlength=n)
    pixel_pred=np.zeros(h*w,'uint8')
    for start in range(0,len(X),180000):
        stop=min(len(X),start+180000); pp=clf.predict_proba(X[start:stop]); ll=flat_ids[start:stop]
        win=clf.classes_[pp.argmax(axis=1)]; pixel_pred[start:stop]=win
        for col,cls in enumerate(clf.classes_):
            scores[:,cls]+=np.bincount(ll,weights=pp[:,col],minlength=n)
            votes[:,cls]+=np.bincount(ll,weights=win==cls,minlength=n).astype('int64')
    scores/=np.maximum(counts[:,None],1); votes_fraction=votes/np.maximum(counts[:,None],1)
    def fraction(mask): return np.bincount(flat_ids,weights=mask.ravel(),minlength=n)/np.maximum(counts,1)
    ref_fractions=np.stack([fraction(reference==c) for c in range(9)],axis=1)
    fixed_fractions=np.stack([fraction(fixed==c) for c in range(9)],axis=1)
    road_fraction=fraction(road_zone); green_fraction=fraction((exg>.045)&(g>r*1.04))
    blue_water_fraction=fraction((r<g*.97)&(b>g*.72)&(r<.36)&(g<.48))
    means=np.stack([np.bincount(flat_ids,weights=channel.ravel(),minlength=n)/np.maximum(counts,1)
                    for channel in (r,g,b,texture[1],texture[2])],axis=1)
    building_near=fraction(ndi.distance_transform_edt(fixed!=5)*abs(t.a)<15)
    reviewed_objects={i:(cls,entry['reason']) for cls,entry in VISUAL_REVIEW.items() for i in entry['ids']}
    labels=np.zeros(n,'uint8'); records=[]
    for row in regions.itertuples():
        i=row.segment_id; raw=int(np.argmax(scores[i])); order=np.sort(scores[i]); margin=float(order[-1]-order[-2])
        model_score=float(scores[i,raw]); dominance=float(votes_fraction[i,raw]); cls=raw
        evidence=model_score; method='RGB/texture random forest + segment voting'; reason=''; status='Automatic estimate'
        prior=int(np.argmax(ref_fractions[i,1:5]))+1; overlap=float(ref_fractions[i,prior])
        footprint=int(np.argmax(fixed_fractions[i,5:7]))+5
        if fixed_fractions[i,footprint]>.95:
            cls=footprint; evidence=float(fixed_fractions[i,footprint]); method='Accepted footprint'; status='Reference footprint'
        elif overlap>=.65 and (prior!=1 or blue_water_fraction[i]>.60):
            cls=prior; evidence=overlap; method='Reviewed-region overlap'; status='Reviewed overlap'
            # A previously broad ground polygon must not swallow a visible road.
            if prior==4 and road_fraction[i]>.55 and votes_fraction[i,7]>.45:
                cls=7; evidence=float(scores[i,7]); method='Road context + forest vote'; status='Automatic estimate'
        else:
            if dominance<.60 or model_score<.47 or margin<.10:
                cls=8; reason='Mixed or weak spectral/texture votes'
            elif raw==1 and blue_water_fraction[i]<.60:
                cls=8; reason='Water-like model vote lacks enough RGB water evidence'
            elif raw==7 and road_fraction[i]<.30:
                cls=8; reason='Paved-looking surface outside supported road corridor'
            elif raw==5:
                rect=row.geometry.minimum_rotated_rectangle
                rectangularity=row.geometry.area/rect.area if rect.area else 0
                corners=list(rect.exterior.coords)
                sides=[Point(corners[j]).distance(Point(corners[j+1])) for j in range(4)]
                aspect=max(sides)/max(min(sides),1e-6)
                if not (model_score>.78 and dominance>.85 and 12<row.area_m2<2500 and rectangularity>.72
                        and green_fraction[i]<.20 and aspect<4 and building_near[i]>.4):
                    cls=8; reason='Roof-like appearance without a reliable footprint'
        # Direct contradictory evidence must not silently inherit a broad review label.
        if method=='Reviewed-region overlap' and cls==4 and green_fraction[i]>.65:
            cls=8; reason='Broad ground reference conflicts with strong vegetation signal'
        if i in reviewed_objects:
            assert row.origin!='Preserved footprint', 'Manual review must not replace an accepted footprint'
            cls,reason=reviewed_objects[i]; evidence=None; method='Explicit visual object review'; status='Visually interpreted'
        if cls==8: status='Needs review'
        labels[i]=cls
        records.append({'segment_id':i,'class_id':cls,'class_name':NAMES[cls],
            'suggested_class':NAMES[raw],'evidence_score':round(evidence,4) if evidence is not None else None,
            'model_score':round(model_score,4),'vote_fraction':round(dominance,4),'vote_margin':round(margin,4),
            'method':method,'review_status':status,'review_reason':reason,
            'reviewed_overlap':round(overlap,4),'road_overlap':round(float(road_fraction[i]),4),
            'green_fraction':round(float(green_fraction[i]),4),'water_rgb_fraction':round(float(blue_water_fraction[i]),4)})
    result=regions.merge(pd.DataFrame(records),on='segment_id',validate='one_to_one')
    assert len(result)==len(regions) and result.class_id.between(1,8).all()
    assert all(a.equals_exact(b,0) for a,b in zip(result.geometry,regions.geometry))
    classified=labels[ids]; classified[~valid]=0
    result.to_file(OUT/'classified_regions.gpkg',layer='classified_regions',driver='GPKG')
    result[result.class_id==8].to_file(OUT/'classified_regions.gpkg',layer='needs_review',driver='GPKG')
    extent=gpd.read_file(source_path,layer='test_extent')
    extent.to_file(OUT/'classified_regions.gpkg',layer='test_extent',driver='GPKG')
    result.drop(columns='geometry').to_csv(OUT/'region_classification.csv',index=False)
    profile.update(count=1,dtype='uint8',nodata=0,compress='lzw')
    with rasterio.open(OUT/'classified_regions.tif','w',**profile) as dst:
        dst.write(classified,1); dst.update_tags(classes=json.dumps(NAMES),status='Image interpretation; not field validated',
            method='Random forest RGB/texture + reviewed overlap + protected footprints + road context')
    style()
    report={'region_count':len(result),'counts_by_class':result.class_name.value_counts().to_dict(),
        'area_m2_by_class':result.groupby('class_name').area_m2.sum().to_dict(),
        'uncertain_area_percent':100*result.loc[result.class_id==8,'area_m2'].sum()/result.area_m2.sum(),
        'original_segmentation_sha256':source_sha,'original_segmentation_unchanged':digest(source_path)==source_sha,
        'geometry_unchanged':True,'feature_names':feature_names,
        'feature_importances':dict(zip(feature_names,clf.feature_importances_.tolist())),
        'training_samples_by_class':{NAMES[int(c)]:int((ys==c).sum()) for c in np.unique(ys)},
        'class_names':NAMES,'explicit_visual_object_review':VISUAL_REVIEW,'additional_examples':EXAMPLE_POINTS,
        'limitations':['No independent ground truth; scores are evidence/forest agreement, not calibrated probabilities',
            'Tree canopy versus low vegetation/plantation is ambiguous in RGB imagery',
            'Bare ground includes exposed rock and sparse dry cover',
            'Road context comes from visually reviewed region footprints, not surveyed road boundaries',
            'Some SAM regions mix surfaces; uncertain regions retain a suggested class for review',
            'Engineered structures include accepted tanks/process units and visually identified dam/spillway structures',
            'Original SAM and edge-completed region boundaries are retained unchanged']}
    assert report['original_segmentation_unchanged']
    (OUT/'classification_report.json').write_text(json.dumps(report,indent=2))
    # Transparent fill and coloured boundaries, never a uniform opaque mask.
    rgba=np.zeros((9,4),float)
    for c,color in COLORS.items(): rgba[c]=[*[int(color[j:j+2],16)/255 for j in (1,3,5)],.24 if c!=8 else .05]
    overlay=rgba[classified]; edges=find_boundaries(ids,mode='inner')&valid
    overlay[edges,3]=.85
    fig,ax=plt.subplots(figsize=(19,11)); ax.imshow(rgb); ax.imshow(overlay); ax.set_axis_off()
    ax.set_title('Full test rectangle — provisional image-based categories; grey = uncertain')
    fig.legend(handles=[Patch(color=COLORS[c],label=name) for c,name in NAMES.items()],loc='lower center',ncol=4,fontsize=9)
    fig.tight_layout(rect=(0,.07,1,.97)); fig.savefig(OUT/'classification_overview.png',dpi=145,bbox_inches='tight'); plt.close(fig)
    for name,(x0,x1,y0,y1) in {'industrial':(950,1530,700,1440),'river':(520,1430,180,790),
                               'settlement_fields':(1740,2658,150,1100)}.items():
        fig,axs=plt.subplots(1,2,figsize=(14,8))
        for ax in axs: ax.imshow(rgb); ax.set_xlim(x0,x1); ax.set_ylim(y1,y0); ax.set_axis_off()
        axs[1].imshow(overlay); axs[0].set_title('Esri RGB'); axs[1].set_title('Image-based classes; grey = uncertain')
        fig.tight_layout(); fig.savefig(OUT/f'classification_{name}.png',dpi=130); plt.close(fig)
    print(json.dumps({k:report[k] for k in ('region_count','counts_by_class','uncertain_area_percent','geometry_unchanged')},indent=2),flush=True)

if __name__=='__main__': main()
