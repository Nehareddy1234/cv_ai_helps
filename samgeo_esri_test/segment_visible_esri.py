"""Rerun SAM on the correctly aligned saved Esri test image.

New mask IDs require fresh visual review; this does not overwrite the reviewed
baseline. It does not download imagery or guess coordinates from a live canvas.
"""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
OUTPUT = ROOT / "output"
DATA.mkdir(exist_ok=True)
OUTPUT.mkdir(exist_ok=True)

IMAGE = DATA / "esri_test_aligned.tif"
MASK = OUTPUT / "sam_rerun_unreviewed.tif"
VECTOR = OUTPUT / "sam_rerun_unreviewed.gpkg"
CHECKPOINT = ROOT.parent / "samgeo" / "weights" / "sam_vit_h_4b8939.pth"


def main() -> None:
    # Avoid this project directory shadowing the installed samgeo package.
    here = str(ROOT)
    sys.path = [p for p in sys.path if str(Path(p).resolve()) != here]
    from samgeo import SamGeo
    import torch
    import rasterio
    import geopandas as gpd
    from rasterio.features import shapes
    from shapely.geometry import shape
    torch.set_num_threads(4)

    if not IMAGE.exists():
        raise FileNotFoundError('Run refine_test_area.py to reconstruct the saved layout georeferencing first.')
    print("Loading SAM ViT-H on CPU", flush=True)
    sam = SamGeo(model_type="vit_h", checkpoint=str(CHECKPOINT), automatic=True,
                 device="cpu", sam_kwargs={"points_per_side": 12,
                 "pred_iou_thresh": 0.86, "stability_score_thresh": 0.92,
                 "crop_n_layers": 0, "min_mask_region_area": 80})
    print("Segmenting the visible test area", flush=True)
    sam.generate(source=str(IMAGE), output=str(MASK), foreground=True, unique=True)
    with rasterio.open(MASK) as src:
        labels = src.read(1)
        rows = [{'sam_id':int(v), 'geometry':shape(g)} for g,v in
                shapes(labels, mask=labels>0, transform=src.transform)]
        gpd.GeoDataFrame(rows, crs=src.crs).to_file(VECTOR, layer='unreviewed_segments', driver='GPKG')
    print(VECTOR, flush=True)


if __name__ == "__main__":
    main()
