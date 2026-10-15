"""Generate a separate relative-path QGIS handoff; leave the user's project intact."""
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parent

def main():
    with zipfile.ZipFile(ROOT/'Bhadra_High_Resolution_Batches.qgz') as archive:
        tree=ET.ElementTree(ET.fromstring(archive.read(next(n for n in archive.namelist() if n.endswith('.qgs')))))
    for layer in tree.getroot().findall('./projectlayers/maplayer'):
        source=layer.find('datasource')
        if source is not None and source.text and '../../latest try/output/combined_classes_with_uncertain/' in source.text:
            source.text=source.text.replace('../../latest try/output/combined_classes_with_uncertain/',
                '../samgeo_esri_test/output/combined_classes_with_uncertain/')
        if source is not None and source.text and layer.findtext('provider')=='ogr':
            path=source.text.split('|',1)[0]
            assert not Path(path).is_absolute(),f'Non-portable project source: {path}'
            assert (ROOT/path).is_file(),f'Missing project source: {path}'
    title=tree.getroot().find('title')
    if title is not None: title.text='Bhadra SAM ViT-H — PARTIAL / provisional'
    target=ROOT/'Bhadra_Resume_PARTIAL.qgs'
    tree.write(target,encoding='utf-8',xml_declaration=True)
    print(target)

if __name__=='__main__': main()
