"""Resumable tiled SAM ViT-H inference on the existing whole-Bhadra Esri image."""
from pathlib import Path
import argparse
import hashlib
import json
import time
import numpy as np
import geopandas as gpd
import rasterio
from rasterio.features import rasterize

ROOT=Path(__file__).resolve().parent
DATA=ROOT/'data'
CACHE=ROOT/'cache'
PARAMS=dict(points_per_side=24,points_per_batch=16,pred_iou_thresh=.82,
            stability_score_thresh=.90,crop_n_layers=0,min_mask_region_area=40)

def global_pass():
    """Capture large regions without artificial internal tile boundaries."""
    from PIL import Image
    import torch
    from samgeo import SamGeo
    manifest=json.loads((CACHE/'manifest.json').read_text())
    image=DATA/'esri_world_imagery.tif'
    assert hashlib.sha256(image.read_bytes()).hexdigest()==manifest['image_sha256']
    target=CACHE/'global.json'
    if target.exists():
        assert json.loads(target.read_text())['image_sha256']==manifest['image_sha256']
        return
    with rasterio.open(image) as src:
        rgb=src.read().transpose(1,2,0)
    height,width=rgb.shape[:2]
    scale=1024/max(height,width)
    small=np.asarray(Image.fromarray(rgb).resize((round(width*scale),round(height*scale)),Image.Resampling.LANCZOS))
    torch.set_num_threads(4)
    write_json(ROOT/'progress.json',{'phase':'Whole-image SAM ViT-H context pass',
        'completed_tiles':len(manifest['jobs']),'total_tiles':len(manifest['jobs'])})
    print('Loading SAM ViT-H for whole-image context pass',flush=True)
    sam=SamGeo(model_type='vit_h',checkpoint=str(ROOT.parent/'weights/sam_vit_h_4b8939.pth'),
               automatic=True,device='cpu',sam_kwargs=PARAMS)
    start=time.time()
    with torch.inference_mode(): masks=sam.mask_generator.generate(small)
    arrays={}; records=[]
    for j,m in enumerate(masks):
        region=np.asarray(Image.fromarray(m['segmentation']).resize((width,height),Image.Resampling.NEAREST))
        yy,xx=np.where(region)
        if not len(xx): continue
        x0=int(xx.min()); x1=int(xx.max())+1; y0=int(yy.min()); y1=int(yy.max())+1
        key=f'm{j}'; arrays[key]=region[y0:y1,x0:x1]
        records.append({'key':key,'bbox':[x0,y0,x1-x0,y1-y0],'area_px':int(region.sum()),
            'sam_score':float(m['predicted_iou']),'stability':float(m['stability_score']),
            'internal_edge':False})
    np.savez_compressed(CACHE/'global.npz',**arrays)
    write_json(target,{'image_sha256':manifest['image_sha256'],'model':'SAM ViT-H','params':PARAMS,
        'inference_size':[small.shape[1],small.shape[0]],'native_size':[width,height],
        'seconds':time.time()-start,'masks':records})
    print(f'Whole-image SAM pass saved: {len(records)} proposals',flush=True)

def write_json(path,data):
    tmp=path.with_suffix('.tmp')
    tmp.write_text(json.dumps(data,indent=2))
    tmp.replace(path)

def starts(length,size=1024,stride=896):
    return sorted(set(list(range(0,max(length-size,0)+1,stride))+[max(0,length-size)]))

def main():
    CACHE.mkdir(exist_ok=True)
    image=DATA/'esri_world_imagery.tif'
    boundary=DATA/'bhadra_boundary.geojson'
    with rasterio.open(image) as src:
        rgb=src.read().transpose(1,2,0)
        aoi=gpd.read_file(boundary).to_crs(src.crs)
        mask=rasterize([(g,1) for g in aoi.geometry],out_shape=rgb.shape[:2],transform=src.transform,dtype='uint8')>0
    jobs=[]
    for y in starts(rgb.shape[0]):
        for x in starts(rgb.shape[1]):
            n=int(mask[y:y+1024,x:x+1024].sum())
            if n: jobs.append({'tile':len(jobs),'x':x,'y':y,'width':1024,'height':1024,'aoi_pixels':n})
    identity={'image_sha256':hashlib.sha256(image.read_bytes()).hexdigest(),
              'aoi_sha256':hashlib.sha256(boundary.read_bytes()).hexdigest(),
              'model':'SAM ViT-H','params':PARAMS,'jobs':jobs}
    manifest=CACHE/'manifest.json'
    if manifest.exists(): assert json.loads(manifest.read_text())==identity,'Input/cache mismatch'
    else: write_json(manifest,identity)
    todo=[j for j in jobs if not (CACHE/f'tile_{j["tile"]}.json').exists()]
    print(f'{len(jobs)} AOI-intersecting tiles, {len(todo)} remaining',flush=True)
    if not todo: return
    import torch
    from samgeo import SamGeo
    torch.set_num_threads(4)
    print('Loading SAM ViT-H checkpoint on CPU',flush=True)
    sam=SamGeo(model_type='vit_h',checkpoint=str(ROOT.parent/'weights/sam_vit_h_4b8939.pth'),
               automatic=True,device='cpu',sam_kwargs=PARAMS)
    print('Model loaded; starting full-resolution source-tile inference',flush=True)
    for job in todo:
        i=job['tile']; x=job['x']; y=job['y']; start=time.time()
        print(f'Tile {i+1}/{len(jobs)} at ({x},{y})',flush=True)
        with torch.inference_mode(): masks=sam.mask_generator.generate(rgb[y:y+1024,x:x+1024])
        arrays={}; records=[]
        for j,m in enumerate(masks):
            region=m['segmentation']; yy,xx=np.where(region)
            if not len(xx): continue
            x0=int(xx.min()); x1=int(xx.max())+1; y0=int(yy.min()); y1=int(yy.max())+1
            key=f'm{j}'
            internal=bool((x>0 and x0<=2) or (y>0 and y0<=2) or
                (x+1024<rgb.shape[1] and x1>=1022) or (y+1024<rgb.shape[0] and y1>=1022))
            arrays[key]=region[y0:y1,x0:x1]
            records.append({'key':key,'bbox':[x+x0,y+y0,x1-x0,y1-y0],'area_px':int(region.sum()),
                'sam_score':float(m['predicted_iou']),'stability':float(m['stability_score']),
                'internal_edge':internal})
        np.savez_compressed(CACHE/f'tile_{i}.npz',**arrays)
        write_json(CACHE/f'tile_{i}.json',{'job':job,'seconds':time.time()-start,'masks':records})
        done=sum((CACHE/f'tile_{j["tile"]}.json').exists() for j in jobs)
        write_json(ROOT/'progress.json',{'phase':'SAM ViT-H segmentation','completed_tiles':done,'total_tiles':len(jobs),
            'last_tile_seconds':time.time()-start})
        print(f'Tile {i+1} saved: {len(records)} proposals, {time.time()-start:.1f} seconds',flush=True)
    print('All SAM ViT-H tiles complete',flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--global-only',action='store_true')
    args=parser.parse_args()
    global_pass() if args.global_only else main()
