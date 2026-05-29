import os
import json
import tqdm
import glob
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
import geopandas as gpd
import pandas as pd
import rasterio
import datetime
import numpy as np

CHECKPOINT_FILE = "checkpoint.json"

def read_raster(file):
    with rasterio.open(file) as src:
        return src.read()
    

def calculate_raster_statistics(raster):
    stats = {}
    stats['mean'] = float(np.mean(raster))
    stats['std'] = float(np.std(raster))
    stats['sum'] = float(np.sum(raster))
    stats['median'] = float(np.median(raster))
    stats['variance'] = float(np.var(raster))

    return stats


def dict2pandas(results_dict):

    # Initialize an empty list to store the data
    data = []

    # Loop through results_dict
    for tile_id, results in results_dict.items():
        country = results["country"]
        state = results["state"]
        satellite_dirs = results["satellite_dirs"]
        file_count = results["file_count"]
        
        for date, stats in results.items():
            if date not in ["country", "state", "satellite_dirs", "file_count"]:
                record = {
                    "tile_id": tile_id,
                    "country": country,
                    "state": state,
                    "date": date,
                    "mean": stats["mean"],
                    "std": stats["std"],
                    "sum": stats["sum"],
                    "median": stats["median"],
                    "variance": stats["variance"],
                    "satellite_dirs": satellite_dirs, 
                    "file_count": file_count
                }
                data.append(record)

    # Create a DataFrame from the list
    df = pd.DataFrame(data)

    return df

class NumpyEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, np.float32):
            return float(obj)
        return super(NumpyEncoder, self).default(obj)

def save_checkpoint(results_dict, processed_tiles):
    with open(CHECKPOINT_FILE, 'w') as f:
        json.dump({"results_dict": results_dict, "processed_tiles": processed_tiles}, f, cls=NumpyEncoder)


def load_checkpoint():
    if os.path.exists(CHECKPOINT_FILE):
        with open(CHECKPOINT_FILE, 'r') as f:
            checkpoint = json.load(f)
        return checkpoint["results_dict"], checkpoint["processed_tiles"]
    return {}, []

def main(rows, ls_gapfilled, ls_89, ls_7, suffix):
    results_dict, processed_tiles = load_checkpoint()

    for row in tqdm.tqdm(rows):
        tile_id = row["id"]
        if tile_id in processed_tiles:
            continue
        
        tile_dir = f"coords_{tile_id}_Landsat"
        
        # List all files from gapfilled imagery first
        gapfilled_files = glob.glob(f"{ls_gapfilled}/{tile_dir}/**/*{suffix}.tif", recursive=True)
        
        # Get the filenames
        gf_filenames = [os.path.basename(file) for file in gapfilled_files]
        
        # List all files from Landsat 8/9 imagery
        ls89_files = glob.glob(f"{ls_89}/{tile_dir}/**/*{suffix}.tif", recursive=True)
        
        # Check if the filenames are already in the gapfilled list
        extra_files = [file for file in ls89_files if os.path.basename(file) not in gf_filenames]
        
        # Add the extra files to the gapfilled list
        gapfilled_files.extend(extra_files)
        
        # Get all filenames again now extras have been added
        gf_filenames = [os.path.basename(file) for file in gapfilled_files]
        
        # List all files from Landsat 7 imagery
        ls7_files = glob.glob(f"{ls_7}/{tile_dir}/**/*{suffix}.tif", recursive=True)
        
        # Check if the filenames are already in the gapfilled list
        extra_files = [file for file in ls7_files if os.path.basename(file) not in gf_filenames]

        # Add the extra files to the gapfilled list
        gapfilled_files.extend(extra_files)
        
        gapfilled_files = sorted(gapfilled_files)
        
        # get count of files per satellite
        satellite_dirs = Counter([file.split("/")[3] for file in gapfilled_files])
        # get variable from Counter object
        satellite_dirs = dict(satellite_dirs)
        
        results = {}
        
        # Use ProcessPoolExecutor to parallelize the raster reading
        with ProcessPoolExecutor(max_workers=25) as executor:
            rasters = list(executor.map(read_raster, gapfilled_files))

        for raster, file in zip(rasters, gapfilled_files):
            
            if suffix == "NDVI":
                raster = raster/65536
            
            date = file.split("/")[-2]
            results[date] = calculate_raster_statistics(raster)
        
        results["satellite_dirs"] = satellite_dirs
        results["country"] = row["Country_territory__ISO3_"]
        results["state"] = row['gis_name']
        results["file_count"] = len(gapfilled_files)
        
        results_dict[tile_id] = results
        processed_tiles.append(tile_id)
        
        # Save checkpoint after processing each tile
        save_checkpoint(results_dict, processed_tiles)
    
    return results_dict
    
if __name__ == "__main__":
    ls_gapfilled = "/mnt/sdd/Sahel_Landsat_gapfilled"
    ls_89 = "/mnt/sdd/Sahel_Landsat89"
    ls_7 = "/mnt/sdd/Sahel_Landsat"
    
    analysis_shape = gpd.read_file("/mnt/sdc/tree_density_and_coverage/shapefiles/sahel_downloader/sahel_prediction_analysis.gpkg")
    suffix = "NDVI"
    
    rows = [row for index, row in analysis_shape.iterrows()]
    
    results = main(rows, ls_gapfilled, ls_89, ls_7, suffix)
    
    df = dict2pandas(results)

    df.to_csv(f"sahel_{suffix}_statistics.csv", index=False)