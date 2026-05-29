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


def crop2planet(row, raster_fps, grid_id):
    
    ps_raster_fp = "/home/rene1337/RSCPH/tree_explorer_africa.vrt"
    
    with rasterio.open(ps_raster_fp) as src:
            rst_src = rasterio.open(raster_fps[0]).read()
            
            window = rasterio.windows.from_bounds(*row.geometry.bounds, transform=src.transform)
            
            ps_mask = np.where(src.read(1, window=window) > 15, 1, 0)
            
            # zoom landsat prediction to the same size as the planetscope prediction using scipy zoom
            width_zoom_factor = rst_src.shape[1] / ps_mask.shape[0]
            height_zoom_factor = rst_src.shape[2] / ps_mask.shape[1]
            ps_mask = zoom(ps_mask, [width_zoom_factor, height_zoom_factor], order=1)
            
            # Dilate the ps_mask by 1 pixel
            #ps_mask = binary_dilation(ps_mask, iterations=1)
            ps_mask = np.expand_dims(ps_mask, 0)
            return ps_mask
        
        
def crop2cropland(row, raster_fps):
    rst_src = rasterio.open(raster_fps[0]).read()
        
    # read agricultural mask with window
    with rasterio.open("/mnt/sdd/downloads_on_drive_d/potapov/2000/potapov_2000_2.vrt") as src:
        window = rasterio.windows.from_bounds(*row.geometry.bounds, transform=src.transform)
        ag_mask_2000 = src.read(1, window=window)
        ag_mask_2000 = np.where(ag_mask_2000 == 244, 1, 0)
        
    if rst_src.shape[0] == 0 or ag_mask_2000.shape[0] == 0:
        print(rst_src.shape, ag_mask_2000.shape)
     # Perform calculations with error handling for division by zero
    with np.errstate(divide='ignore', invalid='ignore'):
    # zoom agriculture mask to the same size as the landsat prediction using scipy zoom
        width_zoom_factor = rst_src.shape[1] / ag_mask_2000.shape[0]
        height_zoom_factor = rst_src.shape[2] / ag_mask_2000.shape[1]
        ag_mask_2000 = zoom(ag_mask_2000, [width_zoom_factor, height_zoom_factor], order=1)

    ag_mask_2000 = np.expand_dims(ag_mask_2000, 0)

    return ag_mask_2000


def crop2shrubland(row, raster_fps):
    rst_src = rasterio.open(raster_fps[0]).read()
    
    with rasterio.open("/mnt/sdd/downloads_on_drive_d/potapov/2020/2020_potapov_2.vrt") as src:
        window = rasterio.windows.from_bounds(*row.geometry.bounds, transform=src.transform)
        mask_2020 = src.read(1, window=window)
        shrub_mask_2020 = np.where((mask_2020 > 8) & (mask_2020 < 24), 1, 0)
        
    # find where values overlap
    shrub_mask_2020 = np.where(shrub_mask_2020 == 1, 1, 0)
    
    if rst_src.shape[0] == 0 or shrub_mask_2020.shape[0] == 0:
        print(rst_src.shape, shrub_mask_2020.shape)
        
     # Perform calculations with error handling for division by zero
    with np.errstate(divide='ignore', invalid='ignore'):
        # zoom agriculture mask to the same size as the landsat prediction using scipy zoom
        width_zoom_factor = rst_src.shape[1] / shrub_mask_2020.shape[0]
        height_zoom_factor = rst_src.shape[2] / shrub_mask_2020.shape[1]
        shrub_mask_2020 = zoom(shrub_mask_2020, [width_zoom_factor, height_zoom_factor], order=1)
        shrub_mask_2020 = np.expand_dims(shrub_mask_2020, 0)

    return shrub_mask_2020


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
    
    grid_id = f"{format_id(int(tile_id.split('_')[0]))}_{format_id(int(tile_id.split('_')[1]))}"
    
    landsat_grid_id = f"coords_{tile_id}_Landsat"

    raster_fps = sorted(glob.glob(f'{landsat_prediction_dir}/{landsat_grid_id}/**/*{prediction_suffix}.tif', recursive=True))
    
    raster_fps = [r for r in raster_fps if prefix in r]
    
    if len(raster_fps) == 0:
        tqdm.tqdm.write(f'No Landsat prediction found for {landsat_grid_id} for path {landsat_prediction_dir}/{landsat_grid_id}')
        return
    
    if os.path.exists(raster_fps[0].replace(".tif", "_shrub_2020.tif")) and overwrite == False:
                tqdm.tqdm.write(f'Already processed {raster_fps[0]}')
                return
    if os.path.exists(raster_fps[0].replace(".tif", "_crop_2000.tif")) and overwrite == False:
                tqdm.tqdm.write(f'Already processed {raster_fps[0]}')
                return
    
    try:      
        
        shrub_mask_2020 = crop2shrubland(row, raster_fps)
        crop_mask_2000 = crop2cropland(row, raster_fps)
          
        for raster in raster_fps:
        
            shrub_2020_fp = raster.replace(".tif", "_shrub_2020.tif")
            crop_2000_fp = raster.replace(".tif", "_crop_2000.tif")
            
            with rasterio.open(raster) as r:
                try:
                    rst = r.read()
                    
                    min_height = np.min([r.shape[1] for r in [rst, shrub_mask_2020, crop_mask_2000]])
                    min_width = np.min([r.shape[2] for r in [rst, shrub_mask_2020, crop_mask_2000]])
                    
                    # crop raster to the smallest raster
                    rst = rst[:, :min_height, :min_width]
                    
                    # crop ag_mask to the smallest raster
                    shrub_mask_2020 = shrub_mask_2020[:, :min_height, :min_width]
                    crop_mask_2000 = crop_mask_2000[:, :min_height, :min_width]
                    
                    
                except ValueError as e:
                    tqdm.tqdm.write(f'Error reading raster {raster}: {e}')
                    return
                
                # Perform calculations with error handling for division by zero
                with np.errstate(divide='ignore', invalid='ignore'):
                   
                    shrub_2020 = np.where(shrub_mask_2020 != 0, rst * shrub_mask_2020, 0)
                    crop_2000 = np.where(crop_mask_2000 != 0, rst * crop_mask_2000, 0)
                
                if not os.path.exists(shrub_2020_fp) or overwrite == True:
                    try:
                        with rasterio.open(raster_fps[0]) as src:
                            out_meta = src.meta.copy()
                            out_meta.update({"driver": "GTiff",
                                            "count": shrub_2020.shape[0],
                                            "height": shrub_2020.shape[1],
                                            "width": shrub_2020.shape[2],
                                            "transform": src.transform})
                            with rasterio.open(shrub_2020_fp, "w", **out_meta) as dest:
                                dest.write(shrub_2020)
                        
                        #print(f'Wrote {shrub_2020_fp}')
                    except Exception as e:
                        print(e)
                        pass
                    
                if not os.path.exists(crop_2000_fp) or overwrite == True:
                    try:
                        with rasterio.open(raster_fps[0]) as src:
                            out_meta = src.meta.copy()
                            out_meta.update({"driver": "GTiff",
                                            "count": crop_2000.shape[0],
                                            "height": crop_2000.shape[1],
                                            "width": crop_2000.shape[2],
                                            "transform": src.transform})
                            with rasterio.open(crop_2000_fp, "w", **out_meta) as dest:
                                dest.write(crop_2000)
                        
                        #print(f'Wrote {shrub_2020_fp}')
                    except Exception as e:
                        print(e)
                        pass
                
    except Exception as e:
        print(e)
        # print line where error occured
        import traceback
        print(traceback.format_exc())
        return
        

def tree_stats(shape, landsat_prediction_dir, prediction_suffix, prefix, multiprocess=True, overwrite=False):
    
    rows = [(row, landsat_prediction_dir, prediction_suffix, prefix, overwrite) for index, 
                                        row in shape.iterrows()]
    if multiprocess:
        # Use ProcessPoolExecutor to parallelize the processing
        with ProcessPoolExecutor(max_workers=20) as executor:
            gdfs = list(tqdm.tqdm(executor.map(process_tree_row, rows),
                                total=len(rows)))
    else:
        gdfs = []
        for row in tqdm.tqdm(rows):
            process_tree_row(row)
    
    return gdfs


if __name__ == "__main__":

    # Load shapefile
    shape = gpd.read_file('/mnt/sdc/tree_density_and_coverage/shapefiles/sahel_downloader/sahel_gee_download_only_semi_arid_final_regions_precip.gpkg')
    
    # remove null rows
    shape = shape[~shape["id"].isnull()]
    print(len(shape.index))

    landsat_prediction_dir = '/mnt/sdd/ls789gf'
    ps_prediction_dir = "/nfs/Users/Martin/Tree_explorer/tree_cover/Africa"

    prediction_suffix = "silver_sweep_9"
    prefix = "significant_relative_diff"

    # calculate individual tree stats
    tree_stats(shape, landsat_prediction_dir, prediction_suffix, prefix, True, False)
    
