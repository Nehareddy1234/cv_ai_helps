"""Merge selected thematic categories without extending or filling their geometry."""
from pathlib import Path
import argparse
import hashlib
import json
import xml.etree.ElementTree as ET
import numpy as np
import geopandas as gpd
import rasterio
from rasterio.features import rasterize

ROOT=Path(__file__).resolve().parent
SOURCE=ROOT/'output/full_classification'
OUT=ROOT/'output/combined_classes'
SELECTED={1,2,5,6,7}
NAMES={1:'Combined selected features',3:'Crops / grass / low vegetation',
       4:'Bare soil / rock / sparse ground',8:'Uncertain / mixed'}
COLORS={1:'23,190,207',3:'164,214,94',4:'200,140,71',8:'156,156,156'}

def main(include_uncertain=False):
    global OUT, SELECTED, NAMES
    if include_uncertain:
        OUT=ROOT/'output/combined_classes_with_uncertain'
        SELECTED=SELECTED | {8}
        NAMES={code:name for code,name in NAMES.items() if code!=8}
        NAMES[1]='Combined selected features + uncertain'
    OUT.mkdir(exist_ok=True)
    path=SOURCE/'classified_regions.gpkg'
    before=hashlib.sha256(path.read_bytes()).hexdigest()
    original=gpd.read_file(path,layer='classified_regions')
    grouped=original.rename(columns={'class_id':'source_class_id','class_name':'source_class_name'}).copy()
    grouped['class_id']=grouped.source_class_id.where(~grouped.source_class_id.isin(SELECTED),1)
    grouped['class_name']=grouped.class_id.map(NAMES)
    assert len(grouped)==len(original) and grouped.segment_id.is_unique
    assert all(a.equals_exact(b,0) for a,b in zip(grouped.geometry,original.geometry))
    rows=[]
    for code,part in grouped.groupby('class_id'):
        geom=part.geometry.union_all()
        rows.append({'class_id':int(code),'class_name':NAMES[int(code)],
            'source_regions':len(part),'source_classes':','.join(map(str,sorted(part.source_class_id.unique()))),
            'area_m2':geom.area,'geometry':geom})
    dissolved=gpd.GeoDataFrame(rows,crs=original.crs)
    target=OUT/'combined_classes.gpkg'
    grouped.to_file(target,layer='reclassified_regions',driver='GPKG')
    dissolved.to_file(target,layer='combined_classes',driver='GPKG')
    dissolved[dissolved.class_id==1].to_file(target,layer='combined_selected_only',driver='GPKG')
    expected=original[original.class_id.isin(SELECTED)].geometry.union_all()
    actual=dissolved[dissolved.class_id==1].geometry.iloc[0]
    assert actual.symmetric_difference(expected).area<.01
    union=dissolved.geometry.union_all()
    overlap=float(dissolved.area.sum()-union.area)
    assert abs(overlap)<.01 and dissolved.is_valid.all()
    assert union.symmetric_difference(original.geometry.union_all()).area<.01
    remaining=sorted(set(original.class_id.unique())-SELECTED)
    for code in remaining:
        a=dissolved[dissolved.class_id==code].geometry.iloc[0]
        b=original[original.class_id==code].geometry.union_all()
        assert a.symmetric_difference(b).area<.01
    with rasterio.open(SOURCE/'classified_regions.tif') as src:
        labels=src.read(1); profile=src.profile.copy(); transform=src.transform
    merged=labels.copy(); merged[np.isin(labels,list(SELECTED))]=1
    with rasterio.open(OUT/'combined_classes.tif','w',**profile) as dst:
        dst.write(merged,1); dst.update_tags(classes=json.dumps(NAMES),
            combined_source_class_ids=','.join(map(str,sorted(SELECTED))),method='Category merge/dissolve only; no new inference')
    saved=gpd.read_file(target,layer='combined_classes')
    reconstructed=rasterize(list(zip(saved.geometry,saved.class_id)),out_shape=merged.shape,transform=transform,dtype='uint8')
    assert np.array_equal(merged,reconstructed)
    assert hashlib.sha256(path.read_bytes()).hexdigest()==before
    root=ET.Element('qgis',version='3.40',styleCategories='Symbology')
    renderer=ET.SubElement(root,'renderer-v2',type='categorizedSymbol',attr='class_id',symbollevels='0')
    cats=ET.SubElement(renderer,'categories'); symbols=ET.SubElement(renderer,'symbols')
    for code,name in NAMES.items():
        ET.SubElement(cats,'category',value=str(code),symbol=str(code),label=name,render='true',type='long')
        symbol=ET.SubElement(symbols,'symbol',name=str(code),type='fill',alpha='1')
        layer=ET.SubElement(symbol,'layer',**{'class':'SimpleFill','enabled':'1','pass':'0','locked':'0'})
        opts=ET.SubElement(layer,'Option',type='Map')
        for key,value in {'color':COLORS[code]+(','+'18' if code==8 else ',55'),
            'outline_color':COLORS[code]+',235','outline_width':'.18','outline_width_unit':'MM',
            'outline_style':'solid','style':'solid','joinstyle':'round'}.items():
            ET.SubElement(opts,'Option',name=key,value=value,type='QString')
    ET.ElementTree(root).write(OUT/'combined_classes.qml',encoding='utf-8',xml_declaration=True)
    report={'passed':True,'merged_source_class_ids':sorted(SELECTED),
        'merged_source_class_names':original.loc[original.class_id.isin(SELECTED),'class_name'].unique().tolist(),
        'merged_source_region_count':int(original.class_id.isin(SELECTED).sum()),
        'merged_area_m2':actual.area,'total_regions_preserved':len(original),
        'remaining_class_ids':list(map(int,remaining)),'dissolved_class_count':len(saved),
        'overlap_m2':overlap,'vector_raster_identical':True,'original_classification_unchanged':True,
        'source_sha256':before,'limitations':['Merging does not improve or validate the original classification',
            'Industrial means the existing engineered-structure footprints, not a newly expanded industrial-site boundary',
            'Disconnected pieces remain multipart; no gaps are filled or convex hulls created',
            'Original score/method attributes in reclassified_regions describe the source classifications']}
    (OUT/'verification.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--include-uncertain',action='store_true',help='Also merge class 8; write a separate output directory')
    main(parser.parse_args().include_uncertain)
