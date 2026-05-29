from math import e
import geopandas as gpd
import rasterio
from rasterio.features import shapes
from rasterio.windows import from_bounds
from rasterio.merge import merge
import pandas as pd
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures import ThreadPoolExecutor
from multiprocessing import Process, Queue, Event, active_children, Manager, freeze_support
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
import time

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
    
    frac_diff_mask = np.where((frac_diff <= 0.05) & (frac_diff >= -0.05), 0, 1)
    
    first_yr_mask = np.where(first4_yr_avg <= 0.01, 0, 1)
    
    # Perform calculations with error handling for division by zero
    with np.errstate(divide='ignore', invalid='ignore'):
                   
        #relative_diff = (frac_diff / first4_yr_avg) * 100
        relative_diff = np.divide(
            frac_diff, 
            first4_yr_avg,
            out=np.zeros_like(frac_diff),
            where=first4_yr_avg != 0
            ) * 100
        
        # Mask out pixels with less than 1% tree cover in the first year and less than 10% change
        relative_diff = relative_diff * first_yr_mask * frac_diff_mask
    
    treeless_threshold = 0.01
    tree_threshold = 0.05

    tree_emergence = np.where(
        (first4_yr_avg < treeless_threshold) &
        (last4_yr_avg >= tree_threshold),
        1,
        0
    )

    tree_loss = np.where(
    (first4_yr_avg >= tree_threshold) &
    (last4_yr_avg < treeless_threshold),
    1,
    0
    )

    tree_growth = (
    (first4_yr_avg >= 0.05) &
    (frac_diff > 0.02)
    )

    # Calculate residuals
    residuals = rasters_2d - (trends_2d * time_steps[:, np.newaxis] + intercepts)
    
    residual_sum_of_squares = np.sum(residuals**2, axis=0)
    
    # Calculate the standard error of the slope
    standard_error = np.sqrt(residual_sum_of_squares / (t - 2)) / np.sqrt(np.sum((time_steps - np.mean(time_steps))**2))
    
    # Calculate the t-value
    t_values = np.divide(
        trends_2d,
        standard_error,
        out=np.zeros_like(trends_2d),
        where=standard_error != 0
        )
   
    # Calculate the degrees of freedom
    dof = t - 2  # Subtract 2 for the slope and intercept parameters
    # Calculate the p-value using the t-distribution
    
    p_values = 2 * stats.t.sf(np.abs(t_values), dof)
    
    # Reshape p-values to the original shape
    p_values = p_values.reshape(rasters.shape[1:])
    sig = p_values < 0.05

    trend_sig = sig * trends
    frac_diff_sig = sig * frac_diff
    relative_diff_sig = sig * relative_diff
        
    return trends, p_values, frac_diff, relative_diff, trend_sig, frac_diff_sig, relative_diff_sig

def compute_trend(rasters):

    t = rasters.shape[0]
    time_steps = np.arange(t)

    # reshape to (time, space)
    rasters_2d = rasters.reshape(t, -1)

    # linear trend
    trends_2d, intercepts = np.polyfit(time_steps, rasters_2d, 1)
    trends = trends_2d.reshape(rasters.shape[1:])

    # first and last periods
    first4 = rasters[:3]
    last4 = rasters[-3:]

    first4_yr_avg = np.median(first4, axis=0)
    last4_yr_avg = np.median(last4, axis=0)

    # absolute canopy change
    frac_diff = last4_yr_avg - first4_yr_avg

    # thresholds
    treeless_threshold = 0.01
    tree_threshold = 0.15
    change_threshold = 0.02

    # masks
    baseline_tree_mask = first4_yr_avg >= tree_threshold
    significant_change_mask = np.abs(frac_diff) > change_threshold

    # relative change (only where trees existed)
    relative_diff = np.zeros_like(frac_diff)

    valid_rel = baseline_tree_mask & significant_change_mask
    relative_diff[valid_rel] = (
        frac_diff[valid_rel] / first4_yr_avg[valid_rel]
    ) * 100

    # ecological change processes
    tree_emergence = (
        (first4_yr_avg < treeless_threshold) &
        (last4_yr_avg >= tree_threshold)
    )

    tree_loss = (
        (first4_yr_avg >= tree_threshold) &
        (last4_yr_avg < treeless_threshold)
    )

    tree_growth = (
        baseline_tree_mask &
        (frac_diff > change_threshold)
    )

    # regression residuals
    residuals = rasters_2d - (
        trends_2d * time_steps[:, np.newaxis] + intercepts
    )

    rss = np.sum(residuals**2, axis=0)

    standard_error = np.sqrt(rss / (t - 2)) / np.sqrt(
        np.sum((time_steps - np.mean(time_steps))**2)
    )

    t_values = np.divide(
        trends_2d,
        standard_error,
        out=np.zeros_like(trends_2d),
        where=standard_error != 0
    )

    dof = t - 2
    p_values = 2 * stats.t.sf(np.abs(t_values), dof)

    p_values = p_values.reshape(rasters.shape[1:])
    sig = p_values < 0.05

    # significance filtered outputs
    trend_sig = trends * sig
    frac_diff_sig = frac_diff * sig
    relative_diff_sig = relative_diff * sig

    return (
        trends,
        p_values,
        frac_diff,
        relative_diff,
        trend_sig,
        frac_diff_sig,
        relative_diff_sig,
        tree_emergence,
        tree_growth,
        tree_loss
    )

'''def compute_trend(rasters):
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
    
    return trends, p_values'''


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


def median_scaling(arr):
    median = np.nanmedian(arr)
    mad = np.nanmedian(np.abs(arr - median))
    scaled_arr = (arr - median) / mad
    return scaled_arr


def get_raster_paths(row, landsat_prediction_dir, prediction_suffix, overwrite=False):
    input_data = []
    for row in rows:
        tile_id = row['id']
        
        landsat_grid_id = f"coords_{tile_id}_Landsat"
        
        out_path = f"/mnt/sdd/senegal_trends/{landsat_grid_id}/"
        os.makedirs(out_path, exist_ok=True)
        final_out_path = os.path.join(out_path, f"trend_{prediction_suffix}.tif")
        
        if os.path.exists(final_out_path) and overwrite == False:
            print(f"trend_{prediction_suffix}.tif already exists for {landsat_grid_id}")
            continue
        
        raster_fps = sorted(glob.glob(f'{landsat_prediction_dir}/{landsat_grid_id}/**/*{prediction_suffix}.tif', recursive=True))

        raster_fps = [raster for raster in raster_fps if "trend" not in raster and "outliers" not in raster and "relative" not in raster and "significant" not in raster]

        if len(raster_fps) > 26:
            print(f"Too many rasters found for {landsat_grid_id}, skipping")
        
        if len(raster_fps) == 0:
            print(f'No Landsat prediction found for {landsat_grid_id} for path {landsat_prediction_dir}/{landsat_grid_id}')
            continue
        
        return_data = [raster_fps, final_out_path]
        input_data.append(return_data)
    
    return input_data


def read_raster(file):
    with rasterio.open(file) as src:
        return src.read(1)


def reader(reading_queue, loaded_queue):
    while True:
        try:
            data = reading_queue.get()
            if data is None:
                #print(f"receiving end of list signal from file queue")
                if not end_of_reading_queue.is_set() and reading_queue.empty():
                    #print(f"sending end of reading signal")
                    # process finishing queue
                    loaded_queue.put(None)
                    end_of_reading_queue.set()
                # waiting for all processes to finish
                end_of_writing_queue.wait()
                break
            
            raster_fps, out_path = data
            del data
            
            #rasters = [rasterio.open(f).read(1) for f in raster_fps]

            with ThreadPoolExecutor() as executor:
                rasters = list(executor.map(read_raster, raster_fps))

            rst_profile = rasterio.open(raster_fps[0]).profile
            
            max_width = np.max([r.shape[1] for r in rasters])
            max_height = np.max([r.shape[0] for r in rasters])
            
            # zoom rasters to the same size
            rasters = [zoom(r, [max_height / r.shape[0], max_width / r.shape[1]], order=1) for r in rasters]
            
            raster_arr = np.array(rasters)

            print(f"Loaded raster array with shape {raster_arr.shape}, {loaded_queue.qsize()} in loaded queue, {reading_queue.qsize()} in reading queue, {active_children()} active children")
            
            #raster_arr = median_scaling(raster_arr)
            
            loaded_queue.put([raster_arr, rst_profile, out_path])
        
        except Exception as e:
            print(f"Error: {e}")
            continue
        

def processor(loaded_queue, writing_queue, num_writers, num_items):
    while True:
        try:
            data = loaded_queue.get()
            print(f"processing new image, {loaded_queue.qsize()} in loaded queue, {writing_queue.qsize()} in writing queue")
            if data is None:
                #print(f"receiving end of list signal from loaded queue")
                [writing_queue.put(None) for wp in range(num_writers)]
                break
            
            #print(loaded_queue.qsize())
            
            raster_arr, src_profile, out_path = data
            
            del data

            trends, p_values, frac_diff, relative_diff, trend_sig, frac_diff_sig, relative_diff_sig, tree_emergence, tree_growth, tree_loss = compute_trend(raster_arr)

            out_arr = np.concatenate([trends[np.newaxis], p_values[np.newaxis], frac_diff[np.newaxis], 
                                      relative_diff[np.newaxis], trend_sig[np.newaxis],
                                      frac_diff_sig[np.newaxis], relative_diff_sig[np.newaxis],
                                      tree_emergence[np.newaxis], tree_growth[np.newaxis], tree_loss[np.newaxis]], axis=0)
            
            band_names = [
                "trends",
                "p_values",
                "frac_diff",
                "relative_diff",
                "trend_sig",
                "frac_diff_sig",
                "relative_diff_sig",
                "tree_emergence",
                "tree_growth",
                "tree_loss"
            ]

            writing_queue.put([out_arr, src_profile, out_path, band_names])
        except Exception as e:
            print(f"Error: {e}")
            continue
    end_of_writing_queue.wait()


def writer(writing_queue):
    while True:
        try:
            data = writing_queue.get()
            if data is None:
                #print(f"receiving end of list signal from writing queue")
                if not end_of_writing_queue.is_set() and writing_queue.empty():
                    #print(f"sending end of writing signal")
                    # process finishing queue
                    end_of_writing_queue.set()
                end_of_writing_queue.wait()
                break
            print(f"writing new image, {writing_queue.qsize()} in writing queue")
            out_arr, src_profile, out_path, band_names = data
            src_profile.update({"count": out_arr.shape[0], "dtype": "float32", "driver": "GTiff"})
            del data
            
            with rasterio.open(out_path, "w", **src_profile) as dest:
                dest.write(out_arr)
                for i, band_name in enumerate(band_names, start=1):
                    dest.update_tags(i, name=band_name)
        except Exception as e:
            print(f"Error: {e}")
            continue
        print(f"Saved {out_path}")
        

if __name__ == "__main__":
    
    
    start = time.time()

    num_readers = 10
    loaded_queue_maxsize = 30
    num_processors = 5
    num_writers = 5
    writing_queue_maxsize = 30
    # Load shapefile
    shape = gpd.read_file('/mnt/sdc/tree_density_and_coverage/shapefiles/sahel_downloader/sahel_gee_download_only_semi_arid_final.gpkg')
    #shape["id"] = shape["id"]
    # remove null rows
    shape = shape[~shape["id"].isnull()]
    #shape = shape[shape["id"] == "-18_17_4"]
    print(len(shape.index))

    landsat_prediction_dir = '/mnt/sdd/ls789gf'
    ps_prediction_dir = "/nfs/Users/Martin/Tree_explorer/tree_cover/Africa"

    prediction_suffix = "silver_sweep_9"
    
    rows = [row for idx, row in shape.iterrows()]
    
    input_data = get_raster_paths(rows, landsat_prediction_dir, prediction_suffix, overwrite=True)
    
    reading_queue = Queue()
    [reading_queue.put(ti) for ti in input_data]
    [reading_queue.put(None) for rp in range(num_readers)]

    end_of_reading_queue = Event()
    end_of_writing_queue = Event()

    loaded_queue = Queue(maxsize=loaded_queue_maxsize)  # limiting the loading queue size
    readers = []
    for i in range(num_readers):
        reader_p = Process(target=reader, args=(reading_queue, loaded_queue))
        reader_p.daemon = True
        reader_p.start()
        readers.append(reader_p)
    print("Readers started")

    writing_queue = Queue(maxsize=writing_queue_maxsize)  # limiting the writing queue size
    
    writers = []
    for i in range(num_writers):
        writer_p = Process(target=writer, args=(writing_queue,))
        writer_p.daemon = True
        writer_p.start()
        writers.append(writer_p)
    print("Writers started")

    processors = []
    for i in range(num_processors):
        processor_p = Process(target=processor, args=(loaded_queue, writing_queue, num_writers, len(rows), ))
        processor_p.daemon = True
        processor_p.start()
        processors.append(processor_p)
    print("processors started")
    
    #processor(loaded_queue, writing_queue, num_writers, len(rows))  # Queue stuff to all reader_p()
    print("Waiting for all processes to end...")
    
    [reader_p.join() for reader_p in readers]
    [writer_p.join() for writer_p in writers]
    [processor_p.join() for processor_p in processors]
    
    print(f"Finished in {(time.time() - start)/3600} hours")