"""Prompt SAM on visually reviewed water and land points in the test image.

Coordinates are pixel positions, not inferred semantic classes from mask IDs.
The audit figure maps source pixels into the rectangle (20,30)-(2025,1120).
"""
from pathlib import Path
import json
import numpy as np
import rasterio
import torch
from samgeo import SamGeo

ROOT=Path(__file__).resolve().parent

def point(x,y):
    return [(x-20)*2660/2005, (y-30)*1446/1090]

def main():
    torch.set_num_threads(4)
    with rasterio.open(ROOT/'data/esri_test_aligned.tif') as src:
        rgb=src.read().transpose(1,2,0)
        profile=src.profile.copy()
    print('Loading prompted SamGeo',flush=True)
    sam=SamGeo(model_type='vit_h',checkpoint=str(ROOT.parent/'samgeo/weights/sam_vit_h_4b8939.pth'),automatic=False,device='cpu')
    sam.set_image(rgb)
    jobs={
      'river': {'positive':[(600,640),(770,518),(875,430),(1010,320),(1190,175),(1390,85)],
                'negative':[(570,580),(735,450),(1060,350),(1220,238),(1350,260),(960,405),(886,325)]},
      'reservoir': {'positive':[(90,965),(90,1080)],'negative':[(239,893),(283,1000),(185,700)]},
      'pond_a': {'positive':[(1055,1000)],'negative':[(1015,978),(1092,977)]},
      'pond_b': {'positive':[(1087,1050)],'negative':[(1067,1028),(1095,1070)]},
      'pond_c': {'positive':[(1150,1008)],'negative':[(1124,983),(1148,1040)]},
      'reach_lower': {'positive':[(560,600)], 'negative':[(570,560),(530,650),(680,620)]},
      'reach_middle': {'positive':[(790,440)], 'negative':[(735,450),(800,370),(800,500)]},
      'reach_upper': {'positive':[(1040,300)], 'negative':[(970,290),(1090,370),(1115,260)]},
      'reach_top': {'positive':[(1370,100)], 'negative':[(1280,210),(1440,200)]},
      'basin_1': {'positive':[(1000,973)], 'negative':[(1025,988),(969,940)]},
      'basin_2': {'positive':[(1016,1030)], 'negative':[(1035,1003),(1038,1052)]},
      'basin_3': {'positive':[(1042,1095)], 'negative':[(1060,1067),(1003,1094)]},
      'basin_4': {'positive':[(1070,940)], 'negative':[(1055,918),(1095,959)]},
      'basin_5': {'positive':[(1090,974)], 'negative':[(1090,959),(1096,994)]},
      'basin_6': {'positive':[(1114,1009)], 'negative':[(1096,994),(1124,1028)]},
      'basin_7': {'positive':[(1125,1047)], 'negative':[(1124,1028),(1135,1064)]},
      'basin_8': {'positive':[(1155,1084)], 'negative':[(1135,1064),(1165,1104)]},
    }
    masks={}; scores={}
    for name,job in jobs.items():
        xy=np.asarray([point(*p) for p in job['positive']+job['negative']],dtype=np.float32)
        labs=np.array([1]*len(job['positive'])+[0]*len(job['negative']))
        with torch.inference_mode():
            result,score,_=sam.predictor.predict(point_coords=xy,point_labels=labs,multimask_output=False)
        masks[name]=result[0]; scores[name]=float(score[0])
        print(name, int(result[0].sum()), scores[name],flush=True)
    np.savez_compressed(ROOT/'output/prompted_water_masks.npz',**masks)
    (ROOT/'output/water_prompts.json').write_text(json.dumps({'prompts_in_audit_image':jobs,'sam_scores_not_class_probabilities':scores},indent=2))

if __name__=='__main__': main()
