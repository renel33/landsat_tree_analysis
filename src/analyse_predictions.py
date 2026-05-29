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


def tvalue(mean, stderr):
    return mean / stderr


def pvalue(tvalue, dof):
    return 2 * (1 - np.abs(np.tanh(tvalue / np.sqrt(dof))))


def compute_trend(rasters, resample=False):
    # Number of time steps
    t = rasters.shape[0]

    # Create an array of time steps
    time_steps = np.arange(t)

    # Reshape rasters to 2D: (time, space)
    rasters_2d = rasters.reshape(t, -1)
    
    # Calculate the per-pixel trend for each pixel
    trends_2d = np.polyfit(np.arange(rasters_2d.shape[0]), rasters_2d, 1)[0]
    
    # Reshape the trends back to the original shape
    trends = trends_2d.reshape(rasters.shape[1:])
    
    # Calculate residuals
    residuals = rasters_2d - (trends_2d * time_steps[:, np.newaxis])
    
    residual_sum_of_squares = np.sum(residuals**2, axis=0)
    
    # Calculate the standard error of the slope
    standard_error = np.sqrt(residual_sum_of_squares / (t - 2)) / np.sqrt(np.sum((time_steps - np.mean(time_steps))**2))
    
    # Calculate the t-value
    t_values = trends_2d / standard_error
    
    # Calculate the degrees of freedom
    dof = t - 2
    
    # Calculate the p-value
    p_values = 2 * (1 - np.abs(np.tanh(t_values / np.sqrt(dof))))
    
    # Reshape p-values to the original shape
    p_values = p_values.reshape(rasters.shape[1:])
    
    return trends, p_values


def linear_trend(array):
    N = array.shape[0]
    result = [stats.linregress(array[i,...])[0] for i in range(0, N)]
    return result


def compute_linear_trend(rasters):
    # A function that maps whatever you want to do over each pixel;
    #   needs to be a global function so it can be pickled
    years_list = []
    # Iterate through each file, combining them in order as a single array
    for i, each_file in enumerate(rasters):
        # Open the file, read in as an array
        arr = each_file
        shp = arr.shape
        arr_flat = arr.reshape((shp[0]*shp[1], 1)) # Ravel array to 1-D shape
        
        if i == 0:
            years_list.append(i + 1)
            base_array = arr_flat # The very first array is the base
            continue # Skip to the next year
        
        # Stack the arrays from each year
        base_array = np.concatenate((base_array, arr_flat), axis = 1)

        years_list.append(i + 1) # Add the year to the list

    # Create a list (generator) of the years, 1999-2024
    
    years_array = np.array(years_list)

    # Make it a 2-dimensional array to start
    years_array = years_array.reshape((1, years_array.shape[0]))
    
    # Create an array for the X data, or independent variable, i.e., the year
    shp = base_array.shape
   
    years_array = np.repeat(years_array, shp[0], axis = 0)\
    .reshape((shp[0], shp[1], 1))
    
    base_array = base_array.reshape((shp[0], shp[1], 1))

    # Now, combine X and Y data
    base_array = np.concatenate((years_array, base_array), axis = 2)

    num_processses = 30
    N = base_array.shape[0]
    
    P = (num_processses + 1) # Number of breaks (number of partitions + 1)

    # Break up the indices into (roughly) equal parts
    partitions = list(zip(np.linspace(0, N, P, dtype=int)[:-1],
            np.linspace(0, N, P, dtype=int)[1:]))

    work = partitions[:-1]
    work.append((partitions[-1][0], partitions[-1][1] + 1))
    
    # NUM_PROCESSES is however many cores you want to use
    with ProcessPoolExecutor(max_workers = num_processses) as executor:
        result = executor.map(linear_trend, [
            base_array[i:j,...] for i, j in work
        ])
    
    combined_results = list(result) # List of array chunks...
    final = np.concatenate(combined_results, axis = 0) # ...Now a single array
    final_array = np.array(final).reshape((1, rasters.shape[2], rasters.shape[1]))
    
    return final_array # ...In the original shape

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
    
    row, landsat_prediction_dir, prediction_suffix, ps_pred_dir = input_tuple
    
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
            window = rasterio.windows.from_bounds(*row.geometry.bounds, transform=src.transform)
            
            ps_mask = np.where(src.read(1, window=window) > 15, 1, 0)
            
            # zoom landsat prediction to the same size as the planetscope prediction using scipy zoom
            width_zoom_factor = rst.shape[1] / ps_mask.shape[0]
            height_zoom_factor = rst.shape[2] / ps_mask.shape[1]
            ps_mask = zoom(ps_mask, [width_zoom_factor, height_zoom_factor], order=1)
            
            # Dilate the ps_mask by 1 pixel
            ps_mask = binary_dilation(ps_mask, iterations=1)
            
    except Exception as e:
        print(e)
        return
    
    for raster in raster_fps:
        
        masked_fp = raster.replace(".tif", "_masked.tif")
        thresh_fp = raster.replace(".tif", "_thresh.tif")
        background_fp = raster.replace(".tif", "_background.tif")
    
        if os.path.exists(masked_fp) and os.path.exists(thresh_fp) and os.path.exists(background_fp):
            #tqdm.tqdm.write(f'Already processed {raster}')
            return
        
        with rasterio.open(raster) as r:
            try:
                rst = r.read(1)
                rst = np.expand_dims(rst, 0)
            except ValueError as e:
                tqdm.tqdm.write(f'Error reading raster {raster}: {e}')
                return
 
            try: 
                #mask out the landsat prediction with the planetscope mask
                out_rst = rst * np.expand_dims(ps_mask, 0)
                
                if not os.path.exists(masked_fp):
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
                
            threshold_rst = np.where(rst >= 0.1, rst, 0)
            background = np.where(rst < 0.1, rst, 0)
            
            if not os.path.exists(thresh_fp):
                with rasterio.open(raster_fps[0]) as src:
                    out_meta = src.meta.copy()
                    out_meta.update({"driver": "GTiff",
                                    "count": threshold_rst.shape[0],
                                    "height": threshold_rst.shape[1],
                                    "width": threshold_rst.shape[2],
                                    "transform": src.transform})
                    with rasterio.open(thresh_fp, "w", **out_meta) as dest:
                        dest.write(threshold_rst)
                
            if not os.path.exists(background_fp):
                with rasterio.open(raster_fps[0]) as src:
                    out_meta = src.meta.copy()
                    out_meta.update({"driver": "GTiff",
                                    "count": background.shape[0],
                                    "height": background.shape[1],
                                    "width": background.shape[2],
                                    "transform": src.transform})
                    with rasterio.open(background_fp, "w", **out_meta) as dest:
                        dest.write(background)
            

def tree_stats(shape, landsat_prediction_dir, prediction_suffix, ps_pred_dir, multiprocess=True):
    
    rows = [(row, landsat_prediction_dir, prediction_suffix, ps_pred_dir) for index, 
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
    
    row, landsat_prediction_dir, prediction_suffix, rm_outliers = input_tuple
    
    tile_id = row['id']
    
    landsat_grid_id = f"coords_{tile_id}_Landsat"

    if os.path.exists(f"{landsat_prediction_dir}/{landsat_grid_id}/outliers_{rm_outliers}_{prediction_suffix}.tif"):
        return
    
    raster_fps = sorted(glob.glob(f'{landsat_prediction_dir}/{landsat_grid_id}/**/*{prediction_suffix}.tif', recursive=True))
    
    raster_fps = [raster for raster in raster_fps if "trend" not in raster]
    
    # Use ProcessPoolExecutor to parallelize the raster reading
    with ProcessPoolExecutor(max_workers=25) as executor:
        rasters = list(executor.map(read_raster, raster_fps))

    if len(raster_fps) == 0:
        tqdm.tqdm.write(f'No Landsat prediction found for {landsat_grid_id} for path {landsat_prediction_dir}/{landsat_grid_id}')
        return
    
    min_height = np.min([r.shape[0] for r in rasters])
    min_width = np.min([r.shape[1] for r in rasters])
    # crop raster to the smallest raster
    rasters = [r[:min_height, :min_width] for r in rasters]
    
    raster_arr = np.array(rasters)
    
    raster_arr = median_scaling(raster_arr)
    
    if rm_outliers:
        trend = compute_linear_trend(raster_arr)
        print(trend.shape)
        out_arr = trend
        with rasterio.open(raster_fps[0]) as src:
            out_meta = src.meta.copy()
            out_meta.update({"driver": "GTiff",
                            "count": 1,
                            "height": out_arr.shape[1],
                            "width": out_arr.shape[2],
                            "transform": src.transform})
            with rasterio.open(f"{landsat_prediction_dir}/{landsat_grid_id}/outliers_{rm_outliers}_{prediction_suffix}.tif", "w", **out_meta) as dest:
                dest.write(out_arr)
    else:
        trend, p_value = compute_trend(raster_arr, resample=False)

        out_arr = np.concatenate([trend[np.newaxis], p_value[np.newaxis]], axis=0)
    
        with rasterio.open(raster_fps[0]) as src:
            out_meta = src.meta.copy()
            out_meta.update({"driver": "GTiff",
                            "count": 2,
                            "height": out_arr.shape[1],
                            "width": out_arr.shape[2],
                            "transform": src.transform})
            with rasterio.open(f"{landsat_prediction_dir}/{landsat_grid_id}/trend_{prediction_suffix}.tif", "w", **out_meta) as dest:
                dest.write(out_arr)


def tree_trends(shape, landsat_prediction_dir, prediction_suffix, multiprocess=True, rm_outliers=False):
    rows = [(row, landsat_prediction_dir, prediction_suffix, rm_outliers) for index, 
                                        row in shape.iterrows()]
    if multiprocess:
        # Use ProcessPoolExecutor to parallelize the processing
        with ProcessPoolExecutor(max_workers=5) as executor:
            list(tqdm.tqdm(executor.map(process_trends_row, rows),
                                total=len(rows)))
    else:
        
        for row in tqdm.tqdm(rows):
            process_trends_row(row)


if __name__ == "__main__":

    # Load shapefile
    shape = gpd.read_file('/mnt/sdc/tree_density_and_coverage/shapefiles/sahel_downloader/sahel_gee_download_only_semi_arid_final.gpkg')
    shape = gpd.read_file('/mnt/sdc/tree_density_and_coverage/shapefiles/drylands/maradi_tiles.gpkg')

    # remove null rows
    shape = shape[~shape["id"].isnull()]

    landsat_prediction_dir = '/mnt/sdc/maradi_new'
    #ps_prediction_dir = "/nfs/Users/Martin/Tree_explorer/tree_cover/Africa"

    prediction_suffix = "silver_sweep_9"

    # calculate individual tree stats
    #tree_stats(shape, landsat_prediction_dir, prediction_suffix, ps_prediction_dir, True)
    
    # calculate trends
    tree_trends(shape, landsat_prediction_dir, prediction_suffix, False, True)