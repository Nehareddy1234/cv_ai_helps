"""Integrate visually accepted industrial SAM masks without changing originals."""
from pathlib import Path
import json
import hashlib
import xml.etree.ElementTree as ET
import numpy as np
import geopandas as gpd
import rasterio
from rasterio.features import rasterize
from shapely.geometry import Point, Polygon
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'output'
# Filled only after inspecting industrial_candidates_preview.png.
ACCEPTED=['tank_west','tank_south','tank_east','roof_northwest','roof_north',
          'roof_central','roof_small','process_rectangular','process_pad']
REJECTED={'roof_northeast':'SAM included the adjacent tree/shadow; not a reliable roof boundary'}

def red_style():
    root=ET.Element('qgis',version='3.40',styleCategories='Symbology')
    rend=ET.SubElement(root,'renderer-v2',type='singleSymbol',symbollevels='0')
    symbols=ET.SubElement(rend,'symbols')
    symbol=ET.SubElement(symbols,'symbol',name='0',type='fill',alpha='1')
    layer=ET.SubElement(symbol,'layer',**{'class':'SimpleFill','enabled':'1','pass':'0','locked':'0'})
    opts=ET.SubElement(layer,'Option',type='Map')
    for k,v in {'color':'243,75,73,85','outline_color':'180,30,30,255','outline_width':'.30','outline_width_unit':'MM','outline_style':'solid','style':'solid','joinstyle':'round'}.items():
        ET.SubElement(opts,'Option',name=k,value=v,type='QString')
    ET.ElementTree(root).write(OUT/'industrial_structures.qml',encoding='utf-8',xml_declaration=True)

def main():
    assert ACCEPTED, 'Visual review must select candidates before integration'
    source_path=ROOT.parent/'samgeo/output/bhadra_classified_buildings.gpkg'
    original_sha=hashlib.sha256(source_path.read_bytes()).hexdigest()
    base=gpd.read_file(OUT/'reviewed_test_classes.gpkg',layer='reviewed_classes')
    buildings=gpd.read_file(OUT/'reviewed_test_classes.gpkg',layer='buildings_reference')
    existing=buildings.geometry.union_all()
    candidates=gpd.read_file(OUT/'industrial_candidates.gpkg',layer='candidates')
    selected=candidates[candidates.object_id.isin(ACCEPTED)].copy()
    assert len(selected)==len(ACCEPTED)
    rows=[]; occupied=existing; skipped=[]
    for _,row in selected.iterrows():
        geom=row.geometry
        if row.subtype=='Circular tank / treatment unit':
            # Footprint includes the interior of a tank; tiny image-texture
            # holes are not separate land-cover regions within the structure.
            assert geom.geom_type=='Polygon'
            geom=Polygon(geom.exterior)
        overlap=geom.intersection(existing).area/geom.area
        if overlap>=.5:
            skipped.append({'object_id':row.object_id,'reason':'Already represented by accepted buildings','existing_coverage':overlap})
            continue
        geom=geom.difference(occupied)
        assert geom.is_valid and geom.area>2
        record=row.to_dict(); record.update(geometry=geom,area_m2=geom.area,review='Visually reviewed; subtype unverified')
        rows.append(record); occupied=occupied.union(geom)
    structures=gpd.GeoDataFrame(rows,crs=base.crs)
    new_union=structures.geometry.union_all()
    cleaned=base.copy(); cleaned.geometry=cleaned.geometry.difference(new_union)
    cleaned=cleaned[~cleaned.is_empty].copy(); cleaned['area_m2']=cleaned.area
    target=OUT/'reviewed_with_industrial.gpkg'
    structures.to_file(target,layer='industrial_structures',driver='GPKG')
    cleaned.to_file(target,layer='reviewed_classes',driver='GPKG')
    buildings.to_file(target,layer='buildings_reference',driver='GPKG')
    with rasterio.open(OUT/'reviewed_classes.tif') as src:
        labels=src.read(1); profile=src.profile.copy(); transform=src.transform; tags=src.tags()
    added=rasterize([(g,5) for g in structures.geometry],out_shape=labels.shape,transform=transform,dtype='uint8')
    labels[added==5]=5
    # Reference buildings are now represented explicitly in the combined raster.
    bmask=rasterize([(g,5) for g in buildings.geometry],out_shape=labels.shape,transform=transform,dtype='uint8')
    labels[bmask==5]=5
    with rasterio.open(OUT/'reviewed_classes_with_industrial.tif','w',**profile) as dst:
        dst.write(labels,1)
        dst.update_tags(**tags)
        classes=json.loads(tags.get('classes','{}')); classes['5']='Buildings / industrial structures'
        dst.update_tags(classes=json.dumps(classes))
        dst.update_tags(class_5='Buildings / industrial structures; see vector subtype',status='Partial test; visual interpretation, not field validated')
    report={'added_features':len(structures),'accepted_candidates':ACCEPTED,'rejected_candidates':REJECTED,'skipped_duplicates':skipped,
        'subtypes':structures.subtype.value_counts().to_dict(),
        'invalid_geometries':int((~structures.is_valid).sum()+(~cleaned.is_valid).sum()),
        'new_structure_overlap_m2':float(structures.area.sum()-new_union.area),
        'existing_building_overlap_m2':float(new_union.intersection(existing).area),
        'landcover_structure_overlap_m2':float(cleaned.geometry.union_all().intersection(new_union).area),
        'landcover_area_removed_m2':float(base.area.sum()-cleaned.area.sum()),
        'original_buildings_sha256':original_sha,
        'original_buildings_unchanged':original_sha==hashlib.sha256(source_path.read_bytes()).hexdigest(),
        'limitations':['Industrial subtype is based on image appearance, not field verification','No extra water basins or tree-filled beds are asserted to be roofed buildings','Only the pictured industrial crop is updated']}
    assert report['invalid_geometries']==0
    for key in ['new_structure_overlap_m2','existing_building_overlap_m2','landcover_structure_overlap_m2']:
        assert abs(report[key])<.01, key
    assert report['original_buildings_unchanged']
    # All three target circular objects must be represented, including their centre.
    prompts=json.loads((OUT/'industrial_prompts.json').read_text())['objects']
    for name in ['tank_west','tank_south','tank_east']:
        assert name in structures.object_id.values
        x,y=prompts[name]['positive_audit']
        pt=Point(*(transform*((x-20)*2660/2005,(y-30)*1446/1090)))
        assert structures[structures.object_id==name].geometry.union_all().covers(pt),name
    # Removing structures must not modify landcover outside their footprints.
    assert base.geometry.union_all().symmetric_difference(cleaned.geometry.union_all()).difference(new_union.buffer(.001)).area<.01
    (OUT/'industrial_review.json').write_text(json.dumps(report,indent=2))
    red_style()
    with rasterio.open(ROOT/'data/esri_test_aligned.tif') as src:
        rgb=src.read().transpose(1,2,0); bounds=src.bounds; t=src.transform
    fig,axs=plt.subplots(1,2,figsize=(15,9),sharex=True,sharey=True)
    for ax in axs:
        ax.imshow(rgb,extent=(bounds.left,bounds.right,bounds.bottom,bounds.top))
        low=t*((730-20)*2660/2005,(960-30)*1446/1090)
        high=t*((1140-20)*2660/2005,(540-30)*1446/1090)
        ax.set_xlim(low[0],high[0]); ax.set_ylim(low[1],high[1]); ax.set_axis_off()
    axs[0].set_title('Esri source — industrial area')
    axs[1].set_title('Added buildings / industrial structures (red)')
    color={1:'#268bea',2:'#36ac55',3:'#badc63',4:'#c78740'}
    for cls,c in color.items():
        part=cleaned[cleaned.class_id==cls]
        part.plot(ax=axs[1],facecolor=c,edgecolor=c,alpha=.15,linewidth=.5)
    buildings.boundary.plot(ax=axs[1],color='#f34b49',linewidth=.65)
    structures.plot(ax=axs[1],facecolor='#f34b49',edgecolor='#b41e1e',alpha=.35,linewidth=1)
    structures.boundary.plot(ax=axs[1],color='#b41e1e',linewidth=.8)
    fig.tight_layout(); fig.savefig(OUT/'industrial_reviewed_preview.png',dpi=145)
    print(json.dumps(report,indent=2))

if __name__=='__main__': main()
