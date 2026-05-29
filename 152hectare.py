import geopandas as gpd
import rasterio
from rasterio.features import shapes
from rasterio.windows import from_bounds
from rasterio.merge import merge
import pandas as pd
from concurrent.futures import ProcessPoolExecutor
import os
import tqdm
import numpy as np
import glob
from scipy.ndimage import zoom
import matplotlib.pyplot as plt
from scipy import stats
from scipy.stats import linregress
from scipy.ndimage import binary_dilation



def read_raster(file):
    with rasterio.open(file) as src:
        return src.read(1)
    

def format_id(id):
    if id < 10 and id >= 0:
        return f'0000{id}'
    elif id < 100 and id >= 10:
        return f'000{id}'
    elif id < 1000 and id >= 100:
        return f'00{id}'
    elif id > -10 and id < 0:
        return f'-000{abs(id)}'
    elif id > -100 and id < -10:
        return f'-00{abs(id)}'
    elif id > -1000 and id < -100:
        return f'-0{abs(id)}'
    

def process_tree_row(input_tuple):
    
    row, landsat_prediction_dir, prediction_suffix, prefix, overwrite = input_tuple
    
    tile_id = row['id']
    
    landsat_grid_id = f"coords_{tile_id}_Landsat"

    raster_fps = sorted(glob.glob(f'{landsat_prediction_dir}/{landsat_grid_id}/**/*{prediction_suffix}.tif', recursive=True))
    
    raster_fps = [r for r in raster_fps if prefix in r]
    
    if len(raster_fps) == 0:
        tqdm.tqdm.write(f'No Landsat prediction found for {landsat_grid_id} for path {landsat_prediction_dir}/{landsat_grid_id}')
        return
    
    try:
        
        for raster in raster_fps:
        
            ag_fp = raster.replace(".tif", "_hct.tif")
        
            if os.path.exists(ag_fp) and overwrite == False:
                tqdm.tqdm.write(f'Already processed {raster}')
                return
            
            with rasterio.open(raster) as r:
                try:
                    rst = r.read()
                    
                    min_height = np.min([r.shape[1] for r in [rst]])
                    min_width = np.min([r.shape[2] for r in [rst]])
                    
                    #rst = np.expand_dims(rst, 0)
                    
                    # crop raster to the smallest raster
                    rst = rst[:, :min_height, :min_width]
                    
                    
                except ValueError as e:
                    tqdm.tqdm.write(f'Error reading raster {raster}: {e}')
                    return
                
                sig_trend_hct = (rst[3]*214)/10000
                sig_diff_hct = (rst[4]*214)/10000
                
                out_array = np.stack([sig_trend_hct, sig_diff_hct], axis=0)
                
                if not os.path.exists(ag_fp) or overwrite == True:
                    try:
                        with rasterio.open(raster_fps[0]) as src:
                            out_meta = src.meta.copy()
                            
                            out_meta.update({"driver": "GTiff",
                                            "count": out_array.shape[0],
                                            "height": out_array.shape[1],
                                            "width": out_array.shape[2],
                                            "transform": src.transform})
                            with rasterio.open(ag_fp, "w", **out_meta) as dest:
                                dest.write(out_array)
                        
                        print(f'Wrote {ag_fp}')
                    except Exception as e:
                        print(e)
                        pass
    except Exception as e:
        print(e)
        return
        

def tree_stats(shape, landsat_prediction_dir, prediction_suffix, prefix, multiprocess=True, overwrite=False):
    
    rows = [(row, landsat_prediction_dir, prediction_suffix, prefix, overwrite) for index, 
                                        row in shape.iterrows()]
    if multiprocess:
        # Use ProcessPoolExecutor to parallelize the processing
        with ProcessPoolExecutor(max_workers=5) as executor:
            gdfs = list(tqdm.tqdm(executor.map(process_tree_row, rows),
                                total=len(rows)))
    else:
        gdfs = []
        for row in tqdm.tqdm(rows):
            process_tree_row(row)
    
    return gdfs


if __name__ == "__main__":
    
    # Load shapefile
    shape = gpd.read_file('/mnt/sdc/tree_density_and_coverage/shapefiles/sahel_downloader/sahel_gee_download_only_semi_arid_final.gpkg')
    
    crop_mask = "/nfs/Other_data/ESA_WorldCover_10m/ESA_WorldCover_10m.vrt"
    #"/nfs/Other_data/gfsad30mcropland/gfsad30mcropland_africa.vrt"
    
    # remove null rows
    shape = shape[~shape["id"].isnull()]
    print(len(shape.index))
    
    landsat_prediction_dir = '/mnt/sdd/ls789gf'
    ps_prediction_dir = "/nfs/Users/Martin/Tree_explorer/tree_cover/Africa"

    prediction_suffix = "silver_sweep_9"
    prefix = "trend"

    # calculate individual tree stats
    tree_stats(shape, landsat_prediction_dir, prediction_suffix, prefix, False, False)
    
