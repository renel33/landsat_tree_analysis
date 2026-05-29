import rasterio
import numpy as np
import os 
import glob
import tqdm
import matplotlib.pyplot as plt
import geopandas as gpd
from collections import Counter
import pandas as pd
from concurrent.futures import ProcessPoolExecutor


def read_raster(file):
    with rasterio.open(file) as src:
        return src.read()
    

def calculate_raster_statistics(raster):
    stats = {}
    stats['mean'] = np.mean(raster)
    stats['std'] = np.std(raster)
    stats['sum'] = np.sum(raster)
    stats['median'] = np.median(raster)
    stats['variance'] = np.var(raster)

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
                    "percentile_25": stats["percentile_25"],
                    "percentile_75": stats["percentile_75"],
                    "satellite_dirs": satellite_dirs, 
                    "file_count": file_count
                }
                data.append(record)

    # Create a DataFrame from the list
    df = pd.DataFrame(data)

    return df


def main(rows, ls_gapfilled, ls_89, ls_7, suffix):
    results_dict = {}

    for row in tqdm.tqdm(rows):
        tile_id = row["id"]
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
            date = file.split("/")[-2]
            results[date] = calculate_raster_statistics(raster)
        
        results["satellite_dirs"] = satellite_dirs
        results["country"] = row["Country_territory__ISO3_"]
        results["state"] = row['gis_name']
        results["file_count"] = len(gapfilled_files)
        
        results_dict[tile_id] = results
    
    return results_dict
    
if __name__ == "__main__":
    ls_gapfilled = "/mnt/sdd/Sahel_Landsat_gapfilled"
    ls_89 = "/mnt/sdd/Sahel_Landsat89"
    ls_7 = "/mnt/sdd/Sahel_Landsat"
    analysis_shape = gpd.read_file("/mnt/sdc/tree_density_and_coverage/shapefiles/sahel_downloader/sahel_prediction_analysis.gpkg")
    suffix = "masked"
    rows = [row for index, row in analysis_shape.iterrows()]
    
    results = main(rows, ls_gapfilled, ls_89, ls_7, suffix)
    
    df = dict2pandas(results)

    df.to_csv("sahel_masked_statistics.csv", index=False)
    
    
    
    