"""Throttled Esri acquisition with explicit missing-tile detection and native LOD audit."""
import io
import json
import math
import time
import numpy as np
import requests
from PIL import Image
import rasterio
from rasterio.transform import from_origin
from rasterio.warp import transform_bounds,reproject,Resampling
from common import *

SERVICE='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer'
HALF_WORLD=20037508.342789244

def get(session,url):
    for attempt in range(5):
        response=session.get(url,timeout=(15,60))
        if response.status_code in (429,500,502,503,504):
            if attempt==4: response.raise_for_status()
            delay=min(60,max(2**(attempt+1),int(response.headers.get('Retry-After','0')) if response.headers.get('Retry-After','').isdigit() else 0))
            time.sleep(delay); continue
        response.raise_for_status(); return response
    raise RuntimeError('Imagery retries exhausted')

class MissingTile(RuntimeError): pass


def download(job):
    manifest=json.loads(MANIFEST.read_text())
    for zoom in range(manifest['zoom'],manifest.get('minimum_zoom',18)-1,-1):
        try: return download_at_zoom(job,zoom)
        except MissingTile:
            if zoom==manifest.get('minimum_zoom',18): raise
            print(f'{job["batch_id"]}: zoom {zoom} unavailable; checking next supported detail level',flush=True)
    raise MissingTile('No supported high-detail Esri imagery')


def download_at_zoom(job,zoom):
    folder=batch_dir(job['batch_id']); target=folder/'esri_rgb.tif'
    manifest=json.loads(MANIFEST.read_text()); rx,ry=manifest['pixel_size']
    expected=from_origin(job['image_left'],job['image_top'],rx,ry)
    if target.exists():
        metadata=json.loads((folder/'imagery.json').read_text())
        assert metadata.get('missing_tile_checked'), 'Cached imagery predates missing-tile validation; inspect before rebuilding'
        assert digest(target)==metadata['sha256']
        with rasterio.open(target) as src:
            assert src.shape==(HEIGHT,WIDTH) and src.transform.almost_equals(expected) and src.crs.to_epsg()==32643
        return target
    cache=folder/'xyz'; cache.mkdir(exist_ok=True)
    span=2*HALF_WORLD/(2**zoom); native=span/256
    bounds=transform_bounds(32643,3857,job['image_left'],job['image_top']-HEIGHT*ry,
                           job['image_left']+WIDTH*rx,job['image_top'],densify_pts=21)
    x0=math.floor((bounds[0]+HALF_WORLD)/span); x1=math.floor((bounds[2]+HALF_WORLD)/span)
    y0=math.floor((HALF_WORLD-bounds[3])/span); y1=math.floor((HALF_WORLD-bounds[1])/span)
    mosaic=np.zeros(((y1-y0+1)*256,(x1-x0+1)*256,3),'uint8')
    session=requests.Session(); session.headers['User-Agent']='Bhadra-local-SAM-classification/1.0'
    metadata_path=ROOT/'esri_service.json'
    if not metadata_path.exists():
        service=get(session,SERVICE+'?f=pjson').json()
        assert 'error' not in service and zoom in [x['level'] for x in service['tileInfo']['lods']]
        atomic_json(metadata_path,service)
    done=0; total=(x1-x0+1)*(y1-y0+1)
    for y in range(y0,y1+1):
        for x in range(x0,x1+1):
            path=cache/f'{zoom}_{y}_{x}.jpg'
            if not path.exists():
                try: response=get(session,f'{SERVICE}/tile/{zoom}/{y}/{x}?blankTile=false')
                except requests.HTTPError as exc:
                    if exc.response.status_code==404: raise MissingTile(f'No Esri tile {zoom}/{y}/{x}') from exc
                    raise
                if response.headers.get('blank-tile','').lower()=='true': raise MissingTile(f'Blank Esri tile {zoom}/{y}/{x}')
                if 'image' not in response.headers.get('Content-Type',''):
                    raise ValueError('Esri returned non-image content; no fabricated tile inserted')
                raw=response.content
                with Image.open(io.BytesIO(raw)) as im: assert im.size==(256,256)
                temp=path.with_suffix('.tmp'); temp.write_bytes(raw); temp.replace(path)
                time.sleep(.25)  # Single downloader, at most four requests/second.
            with Image.open(path) as im: tile=np.asarray(im.convert('RGB'))
            assert tile.shape==(256,256,3),'Invalid Esri tile shape'
            # The service's gray missing-data graphic has text and nonzero
            # variance; a simple variance test does not detect it.
            gray=np.all(tile==tile[:,:,0:1],axis=2)
            if gray.mean()>.99 and np.median(tile)>180: raise MissingTile(f'Placeholder tile {zoom}/{y}/{x}')
            mosaic[(y-y0)*256:(y-y0+1)*256,(x-x0)*256:(x-x0+1)*256]=tile
            done+=1
            if done%25==0: print(f'{job["batch_id"]}: imagery {done}/{total}',flush=True)
    output=np.zeros((3,HEIGHT,WIDTH),'uint8')
    source_t=from_origin(-HALF_WORLD+x0*span,HALF_WORLD-y0*span,native,native)
    for band in range(3):
        reproject(mosaic[:,:,band],output[band],src_transform=source_t,src_crs=3857,
                  dst_transform=expected,dst_crs=32643,resampling=Resampling.bilinear)
    assert np.mean(np.all(output==0,axis=0))<.0001,'Blank pixels after reprojection'
    temporary=target.with_suffix('.partial.tif')
    with rasterio.open(temporary,'w',driver='GTiff',width=WIDTH,height=HEIGHT,count=3,dtype='uint8',
            crs=32643,transform=expected,compress='deflate',tiled=True) as dst: dst.write(output)
    temporary.replace(target)
    atomic_json(folder/'imagery.json',{'sha256':digest(target),'retrieved_utc':utc(),
        'service':SERVICE,'zoom':zoom,'native_mercator_pixel_m':native,'target_utm_pixel_m':[rx,ry],
        'xyz_tiles':total,'missing_tile_checked':True,
        'warning':'Sampling does not establish effective ground resolution or imagery date; actual available native zoom is recorded'})
    return target
