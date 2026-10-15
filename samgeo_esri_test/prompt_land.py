"""Additional scene-specific SAM prompts for uncovered soil and canopy patches."""
from pathlib import Path
import json
import numpy as np
import rasterio
import torch
from samgeo import SamGeo
from prompt_water import point
ROOT=Path(__file__).resolve().parent
torch.set_num_threads(4)
with rasterio.open(ROOT/'data/esri_test_aligned.tif') as src:
    rgb=src.read().transpose(1,2,0)
print('Loading SAM for uncovered land patches',flush=True)
sam=SamGeo(model_type='vit_h',checkpoint=str(ROOT.parent/'samgeo/weights/sam_vit_h_4b8939.pth'),automatic=False,device='cpu')
sam.set_image(rgb)
jobs={
 'open_central': {'class_id':4,'positive':[(650,860),(680,955)],'negative':[(610,785),(770,855),(500,900),(855,790),(940,890)],'box':(490,650,1090,1118)},
 'trees_lower_left': {'class_id':2,'positive':[(470,890),(530,960)],'negative':[(650,900),(580,1100),(290,960)],'box':(280,760,670,1118)},
 'trees_lower_middle': {'class_id':2,'positive':[(1250,1000)],'negative':[(1280,1050),(1150,1000),(1390,940)],'box':(1150,870,1430,1118)},
 'open_riverbank': {'class_id':4,'positive':[(540,410)],'negative':[(560,485),(610,315),(370,480)],'box':(300,280,870,600)},
}
masks={}; scores={}
for name,job in jobs.items():
    xy=np.array([point(*p) for p in job['positive']+job['negative']],dtype=np.float32)
    labs=np.array([1]*len(job['positive'])+[0]*len(job['negative']))
    x0,y0,x1,y1=job['box']; bbox=np.array(point(x0,y0)+point(x1,y1),dtype=np.float32)
    with torch.inference_mode():
        result,score,_=sam.predictor.predict(point_coords=xy,point_labels=labs,box=bbox,multimask_output=False)
    masks[name]=result[0]; scores[name]=float(score[0])
    print(name,int(result[0].sum()),scores[name],flush=True)
np.savez_compressed(ROOT/'output/prompted_land_masks.npz',**masks)
(ROOT/'output/land_prompts.json').write_text(json.dumps({'prompts_in_audit_image':jobs,'sam_scores_not_class_probabilities':scores},indent=2))
