"""Build an exhaustive, unlabeled partition from SAM proposals and gap regions.

SAM does not guarantee exhaustive coverage. Remaining pixels are explicitly
tagged as edge-based gap completion, NOT misrepresented as SAM detections.
Accepted building/industrial footprints are retained without semantic labels.
"""
from pathlib import Path
import argparse
import json
import xml.etree.ElementTree as ET
import numpy as np
import rasterio
from rasterio.features import shapes, rasterize
from scipy import ndimage as ndi
from skimage.measure import label as connected_labels
from skimage.segmentation import felzenszwalb, find_boundaries
import geopandas as gpd
from shapely.geometry import shape, box
from shapely import make_valid
from shapely.ops import unary_union
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'output/full_rectangle'

def polygons_only(g):
    if g.geom_type in ('Polygon','MultiPolygon'): return g
    return unary_union([polygons_only(p) for p in g.geoms if 'Polygon' in p.geom_type or p.geom_type=='GeometryCollection'])

def outline_style(path):
    root=ET.Element('qgis',version='3.40',styleCategories='Symbology')
    renderer=ET.SubElement(root,'renderer-v2',type='singleSymbol',symbollevels='0')
    symbol=ET.SubElement(ET.SubElement(renderer,'symbols'),'symbol',name='0',type='fill',alpha='1')
    layer=ET.SubElement(symbol,'layer',**{'class':'SimpleFill','enabled':'1','pass':'0','locked':'0'})
    opts=ET.SubElement(layer,'Option',type='Map')
    for k,v in {'color':'255,229,127,0','style':'no','outline_color':'255,229,127,255',
        'outline_style':'solid','outline_width':'.14','outline_width_unit':'MM','joinstyle':'round'}.items():
        ET.SubElement(opts,'Option',name=k,value=v,type='QString')
    ET.ElementTree(root).write(path,encoding='utf-8',xml_declaration=True)

def merge_slivers(labels,valid,protected_ids,min_pixels=40):
    """Merge small connected remnants into a touching substantial region.

    Never grow, shrink or merge preserved footprints. The longest shared pixel
    boundary chooses the neighbor; this is documented geometric post-processing.
    """
    components=connected_labels(labels,background=0,connectivity=1)
    sizes=np.bincount(components.ravel())
    objects=ndi.find_objects(components)
    protected=np.isin(labels,list(protected_ids))
    merged=0; pixel_count=0
    for idx,sl in enumerate(objects,start=1):
        if sl is None or sizes[idx]>=min_pixels: continue
        if protected[sl][components[sl]==idx].any(): continue
        y,x=sl
        window=(slice(max(0,y.start-1),min(labels.shape[0],y.stop+1)),
                slice(max(0,x.start-1),min(labels.shape[1],x.stop+1)))
        current=components[window]==idx
        neighbors=ndi.binary_dilation(current)&~current&valid[window]&~protected[window]
        neighbors &= sizes[components[window]]>=min_pixels
        choices,counts=np.unique(labels[window][neighbors],return_counts=True)
        keep=choices>0
        if not keep.any(): continue
        chosen=choices[keep][np.argmax(counts[keep])]
        labels[window][current]=chosen
        merged+=1; pixel_count+=int(current.sum())
    return {'merged_fragments':merged,'reassigned_pixels':pixel_count,'minimum_pixels':min_pixels}

def main():
    global OUT
    parser=argparse.ArgumentParser()
    parser.add_argument('--preview-incomplete',action='store_true',help='Preview completed caches in a separate folder; not the finished result')
    args=parser.parse_args()
    cache=OUT
    available=[i for i in range(6) if (cache/f'tile_{i}.json').exists()]
    if args.preview_incomplete:
        OUT=ROOT/'output/full_rectangle_preview'
        OUT.mkdir(exist_ok=True)
    else:
        assert len(available)==6, 'Complete all six SAM tiles first'
    with rasterio.open(ROOT/'data/esri_test_aligned.tif') as src:
        rgb=src.read().transpose(1,2,0); profile=src.profile.copy(); transform=src.transform; crs=src.crs
    h,w=rgb.shape[:2]
    valid=np.zeros((h,w),bool); valid[2:-2,2:-2]=True
    proposals=[]; rejected={'internal_tile_edge':0,'tile_filling_mask':0,'tiny':0,'near_duplicate':0}
    with rasterio.open(ROOT/'output/sam_masks_aligned.tif') as src: old=src.read(1)
    for v in np.unique(old):
        if not v: continue
        yy,xx=np.where(old==v); x0=int(xx.min()); x1=int(xx.max())+1; y0=int(yy.min()); y1=int(yy.max())+1
        proposals.append({'mask':old[y0:y1,x0:x1]==v,'bbox':[x0,y0,x1-x0,y1-y0],
            'area_px':len(xx),'source_key':f'global_sam_{v}','origin':'SAM automatic','sam_score':None})
    total_tile_proposals=0
    for i in available:
        records=json.loads((cache/f'tile_{i}.json').read_text())
        with np.load(cache/f'tile_{i}.npz') as arrays:
            for m in records['masks']:
                total_tile_proposals+=1
                if m['internal_edge']: rejected['internal_tile_edge']+=1; continue
                if m['area_px']>1024*768*.65: rejected['tile_filling_mask']+=1; continue
                if m['area_px']<40: rejected['tiny']+=1; continue
                proposals.append({**m,'mask':arrays[m['key']].copy(),'source_key':f'tile_{i}_{m["key"]}','origin':'SAM automatic'})
    proposals.sort(key=lambda m:m['area_px'],reverse=True)
    labels=np.zeros((h,w),np.int32); metadata={}; next_id=1
    for p in proposals:
        x,y,pw,ph=p['bbox']; mask=p['mask']; view=labels[y:y+ph,x:x+pw]
        present,counts=np.unique(view[mask],return_counts=True)
        nonzero=present>0
        if nonzero.any():
            dominant=int(present[nonzero][np.argmax(counts[nonzero])]); common=int(counts[nonzero].max())
            original_area=metadata[dominant]['area_px']
            if common/p['area_px']>.9 and .85<original_area/p['area_px']<1.15:
                rejected['near_duplicate']+=1; continue
        view[mask]=next_id
        metadata[next_id]={k:p[k] for k in ('source_key','origin','sam_score','area_px')}
        next_id+=1
    labels[~valid]=0
    # Remove disconnected slivers caused by nesting/overlap, not entire objects.
    components=connected_labels(labels,background=0,connectivity=1)
    sizes=np.bincount(components.ravel()); tiny=sizes<40; tiny[0]=False
    labels[tiny[components]]=0
    sam_pixels=int((labels[valid]>0).sum())
    retained_sam_proposals=len(metadata)
    # These previously accepted footprints retain boundaries but no class names.
    protected_ids=set()
    for layer in ('buildings_reference','industrial_structures'):
        frame=gpd.read_file(ROOT/'output/reviewed_with_industrial.gpkg',layer=layer).to_crs(crs)
        for index,geom in enumerate(frame.geometry):
            footprint=rasterize([(geom,1)],out_shape=(h,w),transform=transform,dtype='uint8')>0
            footprint &= valid
            if not footprint.any(): continue
            labels[footprint]=next_id
            protected_ids.add(next_id)
            metadata[next_id]={'source_key':f'preserved_{layer}_{index}','origin':'Preserved footprint',
                'sam_score':None,'area_px':int(footprint.sum())}
            next_id+=1
    gap=(labels==0)&valid
    gap_count=int(gap.sum()); primary_count=int(valid.sum())-gap_count
    print(f'SAM and preserved footprints cover {primary_count/valid.sum():.1%}; completing {gap_count/valid.sum():.1%} of pixels from image edges',flush=True)
    # Conventional colour/edge graph segmentation, not a second learned model.
    # Initially only uncovered pixels use these regions. Subsequent sliver
    # cleanup may merge tiny remnants, but never changes preserved footprints.
    edge_regions=felzenszwalb(rgb,scale=350,sigma=.9,min_size=100,channel_axis=-1)
    gap_start=next_id
    labels[gap]=edge_regions[gap].astype(np.int32)+gap_start
    labels[~valid]=0
    cleanup=merge_slivers(labels,valid,protected_ids)
    final=connected_labels(labels,background=0,connectivity=1).astype(np.int32)
    ids,first=np.unique(final,return_index=True)
    parent_ids={int(i):int(labels.ravel()[at]) for i,at in zip(ids,first) if i}
    assert (final[valid]>0).all() and (final[~valid]==0).all()
    rows=[]
    for geom,value in shapes(final,mask=valid,transform=transform,connectivity=4):
        idx=int(value); parent=parent_ids[idx]
        if parent>=gap_start:
            m={'source_key':f'edge_gap_{parent-gap_start}','origin':'Edge-based gap completion','sam_score':None}
        else: m=metadata[parent]
        geometry=polygons_only(make_valid(shape(geom)))
        rows.append({'segment_id':idx,'origin':m['origin'],'proposal_id':m['source_key'],
            'sam_score':m['sam_score'],'area_m2':geometry.area,'geometry':geometry})
    regions=gpd.GeoDataFrame(rows,crs=crs)
    # All checks are geometric coverage, NOT object-detection accuracy claims.
    x0,y0=transform*(2,h-2); x1,y1=transform*(w-2,2)
    expected=box(x0,y0,x1,y1)
    union=regions.geometry.union_all()
    overlap=float(regions.area.sum()-union.area)
    gap_area=float(expected.difference(union).area)
    outside=float(union.difference(expected).area)
    assert regions.is_valid.all() and regions.segment_id.is_unique
    assert abs(overlap)<.01 and gap_area<.01 and outside<.01
    regions.to_file(OUT/'unlabelled_regions.gpkg',layer='regions',driver='GPKG')
    gpd.GeoDataFrame([{'name':'Full saved Esri test rectangle','geometry':expected}],crs=crs).to_file(OUT/'unlabelled_regions.gpkg',layer='test_extent',driver='GPKG')
    profile.update(count=1,dtype='int32',nodata=0,compress='lzw')
    with rasterio.open(OUT/'unlabelled_regions.tif','w',**profile) as dst:
        dst.write(final,1); dst.update_tags(type='Region IDs only; no semantic classes',gap_completion='Image-edge based; see vector origin field')
    report={'provisional':args.preview_incomplete,'completed_tiles':len(available),
        'region_count':len(regions),'regions_by_origin':regions.origin.value_counts().to_dict(),
        'area_by_origin_m2':regions.groupby('origin').area_m2.sum().to_dict(),
        'coverage_percent':100*(1-gap_area/expected.area),'valid_image_pixels':int(valid.sum()),
        'sam_pixels_before_footprints':sam_pixels,'gap_completion_pixel_percent':100*gap_count/valid.sum(),
        'tile_proposals':total_tile_proposals,'retained_sam_proposals_before_footprints':retained_sam_proposals,
        'proposal_rejections':rejected,'invalid_geometries':int((~regions.is_valid).sum()),
        'sliver_cleanup':cleanup,
        'overlap_m2':overlap,'uncovered_m2':gap_area,'outside_rectangle_m2':outside,
        'rectangle_bounds':list(expected.bounds),'crs':str(crs),
        'limitations':['100% geometric coverage does not mean every physical object is correctly delineated',
            'Edge-based gap completion is not a direct SAM prediction','No land-cover classes have been assigned',
            'Small non-footprint fragments are merged by longest shared boundary; SAM boundaries are post-processed',
            'Two-pixel layout-frame border excluded; image sampling approximately 0.485 m']}
    (OUT/'coverage_report.json').write_text(json.dumps(report,indent=2))
    outline_style(OUT/'unlabelled_regions.qml')
    boundaries=find_boundaries(final,mode='inner')&valid
    overlay=np.zeros((h,w,4)); overlay[boundaries]=[1,.90,.5,.85]
    fig,ax=plt.subplots(figsize=(17,9))
    ax.imshow(rgb); ax.imshow(overlay); ax.set_axis_off()
    prefix='PROVISIONAL — ' if args.preview_incomplete else ''
    ax.set_title(f'{prefix}Full test rectangle — {len(regions):,} unlabeled regions; outlines only')
    fig.tight_layout(); fig.savefig(OUT/'unlabelled_overview.png',dpi=160); plt.close(fig)
    fig,axs=plt.subplots(1,2,figsize=(14,9))
    for ax in axs: ax.imshow(rgb); ax.set_xlim(1000,1490); ax.set_ylim(1230,700); ax.set_axis_off()
    axs[1].imshow(overlay)
    axs[0].set_title('Esri source detail'); axs[1].set_title('Unlabeled region boundaries')
    fig.tight_layout(); fig.savefig(OUT/'unlabelled_detail.png',dpi=140); plt.close(fig)
    print(json.dumps(report,indent=2),flush=True)

if __name__=='__main__': main()
