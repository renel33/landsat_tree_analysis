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
    with rasterio.open("/mnt/sdd/downloads_on_drive_d/potapov/2000/2000_potapov.vrt") as src:
        window = rasterio.windows.from_bounds(*row.geometry.bounds, transform=src.transform)
        ag_mask_2000 = src.read(1, window=window)
        ag_mask_2000 = np.where(ag_mask_2000 == 244, 1, 0)
    
    with rasterio.open("/mnt/sdd/downloads_on_drive_d/potapov/2020/2020_potapov.vrt") as src:
        window = rasterio.windows.from_bounds(*row.geometry.bounds, transform=src.transform)
        ag_mask_2020 = src.read(1, window=window)
        ag_mask_2020 = np.where(ag_mask_2020 == 244, 1, 0)
        
    if rst_src.shape[0] == 0 or ag_mask_2000.shape[0] == 0 or ag_mask_2020.shape[0] == 0:
        print(rst_src.shape, ag_mask_2000.shape, ag_mask_2020.shape)
          
    # zoom agriculture mask to the same size as the landsat prediction using scipy zoom
    width_zoom_factor = rst_src.shape[1] / ag_mask_2000.shape[0]
    height_zoom_factor = rst_src.shape[2] / ag_mask_2000.shape[1]
    ag_mask_2000 = zoom(ag_mask_2000, [width_zoom_factor, height_zoom_factor], order=1)
    ag_mask_2020 = zoom(ag_mask_2020, [width_zoom_factor, height_zoom_factor], order=1)
    ag_mask_2000 = np.expand_dims(ag_mask_2000, 0)
    ag_mask_2020 = np.expand_dims(ag_mask_2020, 0)
    
    return ag_mask_2000, ag_mask_2020


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
    
    if os.path.exists(raster_fps[0].replace(".tif", "_ag.tif")) and overwrite == False:
                tqdm.tqdm.write(f'Already processed {raster_fps[0]}')
                return
    
    try:      
        
        ps_mask = crop2planet(row, raster_fps, grid_id)
        ag_mask, ag_mask_2020 = crop2cropland(row, raster_fps)
          
        for raster in raster_fps:
        
            ag_fp = raster.replace(".tif", "_ag.tif")
            ag_2020_fp = raster.replace(".tif", "_ag_2020.tif")
            ps_fp = raster.replace(".tif", "_ps_no_dilation.tif")
            
            with rasterio.open(raster) as r:
                try:
                    rst = r.read()
                    
                    min_height = np.min([r.shape[1] for r in [rst, ag_mask]])
                    min_width = np.min([r.shape[2] for r in [rst, ag_mask]])
                    
                    # crop raster to the smallest raster
                    rst = rst[:, :min_height, :min_width]
                    
                    # crop ag_mask to the smallest raster
                    ag_mask = ag_mask[:, :min_height, :min_width]
                    ag_mask_2020 = ag_mask_2020[:, :min_height, :min_width]
                    ps_mask = ps_mask[:, :min_height, :min_width]
                    
                    
                except ValueError as e:
                    tqdm.tqdm.write(f'Error reading raster {raster}: {e}')
                    return
                
                # Perform calculations with error handling for division by zero
                with np.errstate(divide='ignore', invalid='ignore'):
                    ag = np.where(ag_mask != 0, rst * ag_mask, 0)
                    ag_2020 = np.where(ag_mask_2020 != 0, rst * ag_mask_2020, 0)
                    ps = np.where(ps_mask != 0, ag * ps_mask, 0)
                
                if not os.path.exists(ag_fp) or overwrite == True:
                    try:
                        with rasterio.open(raster_fps[0]) as src:
                            out_meta = src.meta.copy()
                            out_meta.update({"driver": "GTiff",
                                            "count": ag.shape[0],
                                            "height": ag.shape[1],
                                            "width": ag.shape[2],
                                            "transform": src.transform})
                            with rasterio.open(ag_fp, "w", **out_meta) as dest:
                                dest.write(ag)
                        
                        #print(f'Wrote {ag_fp}')
                    except Exception as e:
                        print(e)
                        pass
                    
                if not os.path.exists(ps_fp) or overwrite == True:
                    try:
                        with rasterio.open(raster_fps[0]) as src:
                            out_meta = src.meta.copy()
                            out_meta.update({"driver": "GTiff",
                                            "count": ps.shape[0],
                                            "height": ps.shape[1],
                                            "width": ps.shape[2],
                                            "transform": src.transform})
                            with rasterio.open(ps_fp, "w", **out_meta) as dest:
                                dest.write(ps)
                        
                        #print(f'Wrote {ps_fp}')
                    except Exception as e:
                        print(e)
                        pass
                    
                
                if not os.path.exists(ag_2020_fp) or overwrite == True:
                    try:
                        with rasterio.open(raster_fps[0]) as src:
                            out_meta = src.meta.copy()
                            out_meta.update({"driver": "GTiff",
                                            "count": ag_2020.shape[0],
                                            "height": ag_2020.shape[1],
                                            "width": ag_2020.shape[2],
                                            "transform": src.transform})
                            with rasterio.open(ag_2020_fp, "w", **out_meta) as dest:
                                dest.write(ag_2020)
                        
                        #print(f'Wrote {ag_2020_fp}')
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
    
    #crop_mask = "/nfs/Other_data/ESA_WorldCover_10m/ESA_WorldCover_10m.vrt"
    #"/nfs/Other_data/gfsad30mcropland/gfsad30mcropland_africa.vrt"
    
    # remove null rows
    shape = shape[~shape["id"].isnull()]
    print(len(shape.index))

    landsat_prediction_dir = '/mnt/sdd/ls789gf'
    ps_prediction_dir = "/nfs/Users/Martin/Tree_explorer/tree_cover/Africa"

    prediction_suffix = "silver_sweep_9"
    prefix = "trend"

    # calculate individual tree stats
    tree_stats(shape, landsat_prediction_dir, prediction_suffix, prefix, False, True)
    
