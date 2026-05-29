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
from scipy import stats


def tvalue(mean, stderr):
    return mean / stderr


def pvalue(tvalue, dof):
    return 2 * (1 - np.abs(np.tanh(tvalue / np.sqrt(dof))))


def compute_trend(rasters):
    # Number of time steps
    t = rasters.shape[0]

    # Create an array of time steps
    time_steps = np.arange(t)

    # Reshape rasters to 2D: (time, space)
    rasters_2d = rasters.reshape(t, -1)
    
    # Calculate the per-pixel trend for each pixel using np.polyfit
    trends_2d, intercepts = np.polyfit(time_steps, rasters_2d, 1)
    
    # Reshape the trends back to the original shape
    trends = trends_2d.reshape(rasters.shape[1:])
    
    first4 = rasters[:3]
    last4 = rasters[-3:]
    
    first4_yr_avg = np.median(first4, axis=0)
    last4_yr_avg = np.median(last4, axis=0)
    
    # Calculate the percentage difference by using the mean of the first 3 years and the slope
    frac_diff = last4_yr_avg - first4_yr_avg
    
    relative_diff = frac_diff / first4_yr_avg
    
    # Calculate residuals
    residuals = rasters_2d - (trends_2d * time_steps[:, np.newaxis] + intercepts)
    
    residual_sum_of_squares = np.sum(residuals**2, axis=0)
    
    # Calculate the standard error of the slope
    standard_error = np.sqrt(residual_sum_of_squares / (t - 2)) / np.sqrt(np.sum((time_steps - np.mean(time_steps))**2))
    
    # Calculate the t-value
    t_values = trends_2d / standard_error
    
    # Calculate the degrees of freedom
    dof = t - 2  # Subtract 2 for the slope and intercept parameters
    
    # Calculate the p-value using the t-distribution
    p_values = 2 * stats.t.sf(np.abs(t_values), dof)
    
    # Reshape p-values to the original shape
    p_values = p_values.reshape(rasters.shape[1:])
    sig = p_values < 0.05

    trend_sig = sig * trends,
    frac_diff_sig = sig * frac_diff
    relative_diff_sig = sig * relative_diff

    return trends, p_values, frac_diff, relative_diff, trend_sig, frac_diff_sig, relative_diff_sig

def compute_diff(rasters):
    first4 = rasters[:4]
    last4 = rasters[-4:]
    
    first4_yr_avg = np.median(first4, axis=0)
    last4_yr_avg = np.median(last4, axis=0)
    
    #first4_yr_avg = np.where(first4_yr_avg <= 0.1, 0, first4_yr_avg)
    #last4_yr_avg = np.where(last4_yr_avg <= 0.1, 0, last4_yr_avg)
    
    # Calculate the percentage difference by using the mean of the first 3 years and the slope
    frac_diff = last4_yr_avg - first4_yr_avg
    
    # np .where to mask out pixels with less than 10% changw
    frac_diff_mask = np.where((frac_diff <= 0.1) & (frac_diff >= -0.1), 0, 1)
    
    first_yr_mask = np.where(first4_yr_avg <= 0.01, 0, 1)
    
    # Perform calculations with error handling for division by zero
    with np.errstate(divide='ignore', invalid='ignore'):
                   
        relative_diff = (frac_diff / first4_yr_avg) * 100
        
        # Mask out pixels with less than 1% tree cover in the first year and less than 10% change
        relative_diff = relative_diff * first_yr_mask * frac_diff_mask
        
    
    return frac_diff, relative_diff, first4_yr_avg, last4_yr_avg


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

    raster_fps = sorted(glob.glob(f'{landsat_prediction_dir}/{landsat_grid_id}/**/*{prediction_suffix}.tif', recursive=True))
    
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
    
    try:
        # read agricultural mask with window
        with rasterio.open("/nfs/Other_data/gfsad30mcropland/gfsad30mcropland_africa.vrt") as src:
            window = rasterio.windows.from_bounds(*row.geometry.bounds, transform=src.transform)
            ag_mask = src.read(1, window=window)
            
            # zoom agriculture mask to the same size as the landsat prediction using scipy zoom
            width_zoom_factor = rst_src.shape[1] / ag_mask.shape[0]
            height_zoom_factor = rst_src.shape[2] / ag_mask.shape[1]
            ag_mask = zoom(ag_mask, [width_zoom_factor, height_zoom_factor], order=1)
    except Exception as e:
        print(e)
        return
        
    for raster in raster_fps:
        
        masked_fp = raster.replace(".tif", "_masked.tif")
        ag_fp = raster.replace(".tif", "_ag.tif")
        masked_ag_fp = raster.replace(".tif", "_masked_ag.tif")
    
        if os.path.exists(masked_fp) and os.path.exists(ag_fp) and os.path.exists(masked_ag_fp) and overwrite == False:
            tqdm.tqdm.write(f'Already processed {raster}')
            return
        
        with rasterio.open(raster) as r:
            try:
                rst = r.read(1)
                
                min_height = np.min([r.shape[0] for r in [rst, ps_mask, ag_mask]])
                min_width = np.min([r.shape[1] for r in [rst, ps_mask, ag_mask]])
                
                rst = np.expand_dims(rst, 0)
                
                # crop raster to the smallest raster
                rst = rst[:, :min_height, :min_width]
                
                # crop ps_mask to the smallest raster
                ps_mask = ps_mask[:min_height, :min_width]
                
                # crop ag_mask to the smallest raster
                ag_mask = ag_mask[:min_height, :min_width]
                
                
            except ValueError as e:
                tqdm.tqdm.write(f'Error reading raster {raster}: {e}')
                return

            try: 
                #mask out the landsat prediction with the planetscope mask
                out_rst = rst * np.expand_dims(ps_mask, 0)
                
                if overwrite == True or not os.path.exists(masked_fp):
                    with rasterio.open(raster_fps[0]) as src:
                        out_meta = src.meta.copy()
                        out_meta.update({"driver": "GTiff",
                                        "count": out_rst.shape[0],
                                        "height": out_rst.shape[1],
                                        "width": out_rst.shape[2],
                                        "transform": src.transform})
                        with rasterio.open(masked_fp, "w", **out_meta) as dest:
                            dest.write(out_rst)
            except Exception as e:
                print(e)
                pass    
                
            ag = rst * np.expand_dims(ag_mask, 0)
            tree_ag = rst * np.expand_dims(ag_mask, 0) * np.expand_dims(ps_mask, 0)
            
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
                except Exception as e:
                    print(e)
                    pass
                
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


def median_scaling(arr):
    median = np.nanmedian(arr)
    mad = np.nanmedian(np.abs(arr - median))
    scaled_arr = (arr - median) / mad
    return scaled_arr


def process_trends_row(input_tuple):
    
    row, landsat_prediction_dir, prediction_suffix, overwrite = input_tuple
    
    tile_id = row['id']
    
    landsat_grid_id = f"coords_{tile_id}_Landsat"

    if os.path.exists(f"{landsat_prediction_dir}/{landsat_grid_id}/relative_diff_{prediction_suffix}.tif") and overwrite == False:
        return
    
    raster_fps = sorted(glob.glob(f'{landsat_prediction_dir}/{landsat_grid_id}/**/*{prediction_suffix}.tif', recursive=True))
    
    raster_fps = [raster for raster in raster_fps if "trend" not in raster and "relative_diff" not in raster]
        
    if len(raster_fps) > 25:
            print(f"Too many rasters found for {landsat_grid_id}, skipping")
    
    try:
        # Use ProcessPoolExecutor to parallelize the raster reading
        with ProcessPoolExecutor(max_workers=25) as executor:
            rasters = list(executor.map(read_raster, raster_fps))
    except Exception as e:
        print(e)
        return

    if len(raster_fps) <= 1:
        tqdm.tqdm.write(f'No Landsat prediction found for {landsat_grid_id} for path {landsat_prediction_dir}/{landsat_grid_id}')
        return
    
    max_width = np.max([r.shape[1] for r in rasters])
    max_height = np.max([r.shape[0] for r in rasters])
    
    # zoom rasters to the same size
    rasters = [zoom(r, [max_height / r.shape[0], max_width / r.shape[1]], order=1) for r in rasters]
    
    raster_arr = np.array(rasters)
    
    frac_diff, relative_diff, first_yr, last_yr = compute_diff(raster_arr)

    out_arr = np.concatenate([frac_diff[np.newaxis], relative_diff[np.newaxis], first_yr[np.newaxis], last_yr[np.newaxis]], axis=0)

    with rasterio.open(raster_fps[0]) as src:
        out_meta = src.meta.copy()
        out_meta.update({"driver": "GTiff",
                        "count": out_arr.shape[0],
                        "height": out_arr.shape[1],
                        "width": out_arr.shape[2],
                        "transform": src.transform})
        with rasterio.open(f"{landsat_prediction_dir}/{landsat_grid_id}/relative_diff_{prediction_suffix}.tif", "w", **out_meta) as dest:
            dest.write(out_arr)
        
        print(f"Wrote relative_diff_{prediction_suffix}.tif for {landsat_grid_id}")    
        


def tree_trends(shape, landsat_prediction_dir, prediction_suffix, multiprocess=True, overwrite=False):
    rows = [(row, landsat_prediction_dir, prediction_suffix, overwrite) for index, 
                                        row in shape.iterrows()]
    if multiprocess:
        # Use ProcessPoolExecutor to parallelize the processing
        with ProcessPoolExecutor(max_workers=5) as executor:
            list(tqdm.tqdm(executor.map(process_trends_row, rows),
                                total=len(rows)))
    else:
        
        for row in tqdm.tqdm(rows):
            try:
                process_trends_row(row)
            except Exception as e:
                print(e)
                continue

if __name__ == "__main__":

    # Load shapefile
    shape = gpd.read_file('/mnt/sdc/tree_density_and_coverage/shapefiles/sahel_downloader/sahel_gee_download_only_semi_arid_final.gpkg')
    #shape = gpd.read_file('/mnt/sdc/tree_density_and_coverage/shapefiles/drylands/maradi_tiles.gpkg')

    # remove null rows
    shape = shape[~shape["id"].isnull()]
    #shape = shape[shape["id"] == "9_14_6"]
    print(len(shape.index))

    landsat_prediction_dir = '/mnt/sdd/ls789gf'
    ps_prediction_dir = "/nfs/Users/Martin/Tree_explorer/tree_cover/Africa"

    prediction_suffix = "silver_sweep_9"

    # calculate individual tree stats
    #tree_stats(shape, landsat_prediction_dir, prediction_suffix, ps_prediction_dir, False, False)
    
    # calculate trends
    tree_trends(shape, landsat_prediction_dir, prediction_suffix, False, True)