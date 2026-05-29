import os
import glob
import rasterio
from rasterio.warp import calculate_default_transform, reproject, Resampling
import numpy as np
import tqdm

def downsample_raster(input_raster, output_raster, target_resolution=0.0025):
    """
    Downsample the input raster to the target resolution using rasterio.
    
    Parameters:
    input_raster (str): Path to the input raster file.
    output_raster (str): Path to the output downsampled raster file.
    target_resolution (float): Target resolution in meters.
    """
    with rasterio.open(input_raster) as src:
        # Check for georeferencing information
        if src.transform is None or src.crs is None:
            raise ValueError(f"Input raster {input_raster} is missing georeferencing information.")
        
        # Calculate the transform and dimensions for the new resolution
        transform, width, height = calculate_default_transform(
            src.crs, src.crs, src.width, src.height, 
            resolution=(target_resolution, target_resolution)
        )
        
        # Update the metadata with the new dimensions and transform
        kwargs = src.meta.copy()
        kwargs.update({
            'transform': transform,
            'width': width,
            'height': height
        })
        
        # Perform the resampling
        with rasterio.open(output_raster, 'w', **kwargs) as dst:
            for i in range(1, src.count + 1):
                reproject(
                    source=rasterio.band(src, i),
                    destination=rasterio.band(dst, i),
                    src_transform=src.transform,
                    src_crs=src.crs,
                    dst_transform=transform,
                    dst_crs=src.crs,
                    resampling=Resampling.bilinear
                )

# Input and output directories
input_dir = "/mnt/sdc/ls7gf"

# Find all matching files and process them
input_rasters = glob.glob(os.path.join(input_dir, "**/*trend_silver_sweep_9_ag.tif"), recursive=True)

print(len(input_rasters))

for input_raster in tqdm.tqdm(input_rasters):
    # Construct the output file path
    output_raster = input_raster.replace(".tif", "_250.tif")
    
    # Downsample the raster
    try:
        downsample_raster(input_raster, output_raster)
    except Exception as e:
        print(f"An error occurred: {e}")