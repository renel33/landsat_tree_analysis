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
import shutil


def read_raster(file):
    with rasterio.open(file) as src:
        return src.read()
    

def main(rows, ls_gapfilled = None, ls_89 = None, ls_7 = None, suffix ="", new_dir=""):
    for row in tqdm.tqdm(rows):
        tile_id = row["id"]
        
        tile_dir = f"coords_{tile_id}_Landsat"
        
        if ls_gapfilled is None:
            gapfilled_files = []
            gf_filenames = []
        
        else:
            # List all files from gapfilled imagery first
            gapfilled_files = glob.glob(f"{ls_gapfilled}/{tile_dir}/**/*{suffix}.tif", recursive=True)
            print(f"Found {len(gapfilled_files)} gapfilled files for {tile_dir}")
            # Get the filenames
            gf_filenames = [os.path.basename(file) for file in gapfilled_files]
        
        if ls_89 is None:
            ls89_files = []
            extra_files = []
            
        else:
            # List all files from Landsat 8/9 imagery
            ls89_files = glob.glob(f"{ls_89}/{tile_dir}/**/*{suffix}.tif", recursive=True)
            print(f"Found {len(ls89_files)} Landsat 8/9 files for {tile_dir}")
            # Check if the filenames are already in the gapfilled list
            extra_files = [file for file in ls89_files if os.path.basename(file) not in gf_filenames]
        
        # Add the extra files to the gapfilled list
        gapfilled_files.extend(extra_files)
        
        # Get all filenames again now extras have been added
        gf_filenames = [os.path.basename(file) for file in gapfilled_files]
        
        if ls_7 is None:
            ls7_files = []
            extra_files = []
        else:
            # List all files from Landsat 7 imagery
            ls7_files = glob.glob(f"{ls_7}/{tile_dir}/**/*{suffix}.tif", recursive=True)

            print(f"Found {len(ls7_files)} Landsat 7 files for {tile_dir}")
            # Check if the filenames are already in the gapfilled list
            extra_files = [file for file in ls7_files if os.path.basename(file) not in gf_filenames]

        # Add the extra files to the gapfilled list
        gapfilled_files.extend(extra_files)
        
        gapfilled_files = sorted(gapfilled_files)
        
        gapfilled_files = [file for file in gapfilled_files if "outliers" not in file]
        gapfilled_files = [file for file in gapfilled_files if "trend" not in file]
        
        # get count of files per satellite
        satellite_dirs = Counter([file.split("/")[3] for file in gapfilled_files])
        # get variable from Counter object
        satellite_dirs = dict(satellite_dirs)
        
        for file in gapfilled_files:
            out_dir = os.path.join(new_dir, tile_dir)
            os.makedirs(out_dir, exist_ok=True)
            out_dir = os.path.join(out_dir, file.split("/")[-2])
            os.makedirs(out_dir, exist_ok=True)
            
            out_path = os.path.join(out_dir, os.path.basename(file))
            
            if os.path.exists(out_path):
                print(f"File {out_path} already exists, skipping")
                continue
            
            #shutil.move(file, out_path)
            shutil.copy(file, out_path)

    
if __name__ == "__main__":
    ls_gapfilled = "/mnt/sdc/ls89gf"
    ls_89 = "/mnt/sdc/ls7gf"
    ls_7 = "/mnt/sdd/Sahel_Landsat"
    out_dir = "/mnt/sdd/ls789gf"
    os.makedirs(out_dir, exist_ok=True)
    
    analysis_shape = gpd.read_file("/mnt/sdc/tree_density_and_coverage/shapefiles/sahel_downloader/sahel_gee_download_only_semi_arid_final.gpkg")
    suffix = "silver_sweep_9"
    
    rows = [row for index, row in analysis_shape.iterrows()]
    
    results = main(rows, ls_gapfilled, ls_89, None, suffix, out_dir)