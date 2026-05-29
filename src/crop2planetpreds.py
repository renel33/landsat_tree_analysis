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
    
    row, landsat_prediction_dir, prediction_suffix, ps_pred_dir, overwrite = input_tuple
    
    tile_id = row['id']
    
    grid_id = f"{format_id(int(tile_id.split('_')[0]))}_{format_id(int(tile_id.split('_')[1]))}"
    
    landsat_grid_id = f"coords_{tile_id}_Landsat"

    raster_fps = sorted(glob.glob(f'{landsat_prediction_dir}/{landsat_grid_id}/**/*trend_{prediction_suffix}.tif', recursive=True))
    
    if len(raster_fps) == 0:
        tqdm.tqdm.write(f'No Landsat prediction found for {landsat_grid_id} for path {landsat_prediction_dir}/{landsat_grid_id}')
        return

    # read planetscope prediction
    ps_prediction = glob.glob(f'{ps_pred_dir}/*.tif')
    ps_raster_fp = [raster for raster in ps_prediction if grid_id in raster]
    
    if len(ps_raster_fp) == 0 or len(ps_raster_fp) < 4:
        tqdm.tqdm.write(f'No PlanetScope prediction found for {grid_id}')
        return

    out_merged_path = "/nfs/Users/Rene/flo_predictions"
    out_raster_fp = f"{out_merged_path}/ps_tree_cover_{grid_id}_merged.tif"
    
    if not os.path.exists(out_raster_fp):
        print(f'Merging PlanetScope predictions for {grid_id}')
        #merge ps_raster_list to one raster
        with rasterio.open(ps_raster_fp[0]) as src:
            ps_raster_list = [rasterio.open(raster) for raster in ps_raster_fp]
            out_image, out_transform = merge(ps_raster_list)
            print(out_image.shape)
            out_meta = src.meta.copy()
            out_meta.update({"height": out_image.shape[1],
                            "width": out_image.shape[2],
                            "transform": out_transform})
            with rasterio.open(out_raster_fp, "w", **out_meta) as dest:
                dest.write(out_image)
    
    # read planetscope prediction
    ps_prediction = glob.glob(f'{out_merged_path}/*.tif')
    ps_raster_fp = [raster for raster in ps_prediction if grid_id in raster]
    ps_raster_fp = ps_raster_fp[0]
    
    #load ps raster
    try:
        with rasterio.open(ps_raster_fp) as src:
            rst_src = rasterio.open(raster_fps[0]).read()
            
            window = rasterio.windows.from_bounds(*row.geometry.bounds, transform=src.transform)
            
            ps_mask = np.where(src.read(1, window=window) > 15, 1, 0)
            
            # zoom landsat prediction to the same size as the planetscope prediction using scipy zoom
            width_zoom_factor = rst_src.shape[1] / ps_mask.shape[0]
            height_zoom_factor = rst_src.shape[2] / ps_mask.shape[1]
            ps_mask = zoom(ps_mask, [width_zoom_factor, height_zoom_factor], order=1)
            
            # Dilate the ps_mask by 1 pixel
            ps_mask = binary_dilation(ps_mask, iterations=1)
            
    except Exception as e:
        print(e)
        return
    
        
    for raster in raster_fps:
        
        masked_ag_fp = raster.replace(".tif", "_masked.tif")
    
        if os.path.exists(masked_ag_fp) and overwrite == False:
            tqdm.tqdm.write(f'Already processed {raster}')
            return
        
        with rasterio.open(raster) as r:
            try:
                rst = r.read(1)
                
                min_height = np.min([r.shape[0] for r in [rst, ps_mask]])
                min_width = np.min([r.shape[1] for r in [rst, ps_mask]])
                
                rst = np.expand_dims(rst, 0)
                
                # crop raster to the smallest raster
                rst = rst[:, :min_height, :min_width]
                
                # crop ps_mask to the smallest raster
                ps_mask = ps_mask[:min_height, :min_width]
            
                
            except ValueError as e:
                tqdm.tqdm.write(f'Error reading raster {raster}: {e}')
                return

            
            tree_ag = rst * np.expand_dims(ps_mask, 0)
            
            
            if not os.path.exists(masked_ag_fp) or overwrite == True:
                try:
                    with rasterio.open(raster_fps[0]) as src:
                        out_meta = src.meta.copy()
                        out_meta.update({"driver": "GTiff",
                                        "count": tree_ag.shape[0],
                                        "height": tree_ag.shape[1],
                                        "width": tree_ag.shape[2],
                                        "transform": src.transform})
                        with rasterio.open(masked_ag_fp, "w", **out_meta) as dest:
                            dest.write(tree_ag)
                except Exception as e:
                    print(e)
                    pass
            
    
def tree_stats(shape, landsat_prediction_dir, prediction_suffix, ps_pred_dir, multiprocess=True, overwrite=False):
    
    rows = [(row, landsat_prediction_dir, prediction_suffix, ps_pred_dir, overwrite) for index, 
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

    import time
    #time.sleep(60*60*2)
    # Load shapefile
    shape = gpd.read_file('/mnt/sdc/tree_density_and_coverage/shapefiles/sahel_downloader/sahel_gee_download_only_semi_arid_final.gpkg')
    #shape = gpd.read_file('/mnt/sdc/tree_density_and_coverage/shapefiles/drylands/maradi_tiles.gpkg')

    # remove null rows
    shape = shape[~shape["id"].isnull()]
    #shape = shape[shape["id"] == "8_15_6"]
    print(len(shape.index))

    landsat_prediction_dir = '/mnt/sdc/ls789gf'
    ps_prediction_dir = "/nfs/Users/Martin/Tree_explorer/tree_cover/Africa"

    prediction_suffix = "silver_sweep_9"

    # calculate individual tree stats
    tree_stats(shape, landsat_prediction_dir, prediction_suffix, ps_prediction_dir, False, True)
