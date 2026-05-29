import pickle
import os
from tqdm import tqdm
import numpy as np
import rasterio
from rasterio.windows import from_bounds
import pandas as pd
import geopandas as gpd

def read_and_downsample_binary(input_raster, bounds, band=1, target_res=15, base_res=1):
    """
    Read a binary high-res raster (e.g. 1 m tree cover) 
    and downsample to fractional tree cover at target resolution (e.g. 15 m).
    
    Args:
        input_raster (str): Path to raster file.
        bounds (tuple): (minx, miny, maxx, maxy) bounds of window to read.
        target_res (int): Target resolution (e.g., 15).
        base_res (int): Resolution of input raster (e.g., 1).
    
    Returns:
        np.ndarray: Fractional tree cover at target resolution.
        (profile, transform): Raster metadata for output.
    """
    with rasterio.open(input_raster) as src:
        # Get window for the geometry bounds
        window = from_bounds(*bounds, transform=src.transform)
        window_transform = rasterio.windows.transform(window, src.transform)

        # Read binary tree cover (0/1)
        data = src.read(band, window=window).astype("float32")
        
        # Handle nodata
        #if src.nodata is not None:
        #    data[data == src.nodata] = np.nan

        # Block size = how many base pixels per target pixel
        block_size = int(target_res // base_res)
        print(block_size)

        # Trim so dimensions are multiples of block_size
        h = int((data.shape[0] // block_size) * block_size)
        w = int((data.shape[1] // block_size) * block_size)
        
        data = data[:h, :w]

        # Reshape into blocks and compute mean (fractional cover)
        reshaped = data.reshape(
            h // block_size, block_size,
            w // block_size, block_size
        )
        
        fractional_cover = np.nanmean(reshaped, axis=(1, 3)).astype(np.float32)

        # Update transform and profile
        transform = window_transform * window_transform.scale(block_size, block_size)
        profile = src.profile.copy()
        profile.update({
            'transform': transform,
            'height': fractional_cover.shape[0],
            'width': fractional_cover.shape[1],
            'dtype': 'float32'
        })

    return fractional_cover, (profile, transform)


if __name__ == "__main__":
    predictions_rst = "/mnt/sdd/senegal_trends/ls789gf_{}_102022_100m.vrt"
    area_shp = "/mnt/sdd/senegal_trends/sen_intersection.gpkg"
    early_raster = "/mnt/sdd/senegal_trends/tucker_early_100m.tif"
    late_raster = "/mnt/sdd/senegal_trends/tucker_late_100m.tif"
    out_dir = "/mnt/sdd/senegal_trends/validation_change_100m_similarity"
    os.makedirs(out_dir, exist_ok=True)
    
    gdf = gpd.read_file(area_shp)

    overwrite = False
    skip = True
    
    if not skip:
        for index, row in tqdm(gdf.iterrows(), total=len(gdf)):
            
            if not overwrite and os.path.exists(f"{out_dir}/landsat_change_{row['fid']}"):
                print(f"Skipping {index}, output exists.")
                continue
            
            try:
                bounds = row.geometry.bounds
                early_year, late_year = row["early_year"], row["late_year"]

                with rasterio.open(early_raster) as src:
                    early_tucker = src.read(1, window=rasterio.windows.from_bounds(*bounds, src.transform))
                    early_tucker = np.where(early_tucker <= 0.01, 0, early_tucker)
                    profile = src.profile
                    transform = rasterio.windows.transform(rasterio.windows.from_bounds(*bounds, src.transform), src.transform)

                with rasterio.open(late_raster) as src:
                    late_tucker = src.read(1, window=rasterio.windows.from_bounds(*bounds, src.transform))
                    late_tucker = np.where(late_tucker <= 0.01, 0, late_tucker)
                    tucker_profile = src.profile
                    tucker_transform = rasterio.windows.transform(rasterio.windows.from_bounds(*bounds, src.transform), src.transform)
                    
                tucker_change = late_tucker - early_tucker
                
                with rasterio.open(predictions_rst.format(early_year)) as src:
                    early_landsat = src.read(1, window=rasterio.windows.from_bounds(*bounds, src.transform))
                    # filter out values that are less or equal to 0.1
                    #early_landsat = np.where(early_landsat <= 0.1, 0, early_landsat)
                    profile = src.profile
                    transform = rasterio.windows.transform(rasterio.windows.from_bounds(*bounds, src.transform), src.transform)

                with rasterio.open(predictions_rst.format(late_year)) as src:
                    late_landsat = src.read(1, window=rasterio.windows.from_bounds(*bounds, src.transform))
                    #late_landsat = np.where(late_landsat <= 0.1, 0, late_landsat)
                    profile = src.profile
                    transform = rasterio.windows.transform(rasterio.windows.from_bounds(*bounds, src.transform), src.transform)

                prediction_change = late_landsat - early_landsat
                
                ls_tucker = prediction_change - tucker_change
                
                # where both tucker and landsat are negative new channel
                change_cat = np.zeros_like(prediction_change, dtype=np.float32)
                change_cat[(tucker_change < 0) & (prediction_change < 0)] = 1  # both negative
                change_cat[(tucker_change > 0) & (prediction_change > 0)] = 2  # both positive
                change_cat[(tucker_change < 0) & (prediction_change > 0)] = 3  # tucker negative, landsat positive
                change_cat[(tucker_change > 0) & (prediction_change < 0)] = 4  # tucker positive, landsat negative
                change_cat[(tucker_change == 0) & (prediction_change != 0)] = 5  # tucker no change, landsat change
                change_cat[(tucker_change != 0) & (prediction_change == 0)] = 6  # tucker change, landsat no change
                change_cat[(tucker_change == 0) & (prediction_change == 0)] = 7  # both no change
            

                # Avoid division by zero
                eps = 1e-6

                # Initialize similarity channel
                similarity_pospos = np.zeros_like(prediction_change, dtype=np.float32)
                similarity_negneg = np.zeros_like(prediction_change, dtype=np.float32)
                similarity_posneg = np.zeros_like(prediction_change, dtype=np.float32)
                similarity_negpos = np.zeros_like(prediction_change, dtype=np.float32)

                # Both negative
                mask = (tucker_change < 0) & (prediction_change < 0)
                similarity_negneg[mask] = 1 - np.abs(tucker_change[mask] - prediction_change[mask]) / (np.maximum(np.abs(tucker_change[mask]), np.abs(prediction_change[mask])) + eps)
                # Both positive
                mask = (tucker_change > 0) & (prediction_change > 0)
                similarity_pospos[mask] = 1 - np.abs(tucker_change[mask] - prediction_change[mask]) / (np.maximum(np.abs(tucker_change[mask]), np.abs(prediction_change[mask])) + eps)

                # Tucker negative, Landsat positive
                mask = (tucker_change < 0) & (prediction_change > 0)
                similarity_posneg[mask] = 1 - np.abs(np.abs(tucker_change[mask]) - prediction_change[mask]) / (np.maximum(np.abs(tucker_change[mask]), prediction_change[mask]) + eps)
                # Tucker positive, Landsat negative
                mask = (tucker_change > 0) & (prediction_change < 0)
                similarity_negpos[mask] = 1 - np.abs(tucker_change[mask] - np.abs(prediction_change[mask])) / (np.maximum(tucker_change[mask], np.abs(prediction_change[mask])) + eps)

                # Optional: clamp to [0, 1] in case of numerical issues
                similarity_negneg = np.clip(similarity_negneg, 0, 1)
                similarity_pospos = np.clip(similarity_pospos, 0, 1)
                similarity_posneg = np.clip(similarity_posneg, 0, 1)
                similarity_negpos = np.clip(similarity_negpos, 0, 1)
                
                
                year_diff = late_year - early_year
                
                # make a channel with all values the year difference
                year_diff_channel = np.full_like(prediction_change, year_diff, dtype=np.float32)
                
                # stack all arrays into a single multi-band array
                out_array = np.stack([early_landsat, late_landsat, prediction_change,
                                    early_tucker, late_tucker, tucker_change, ls_tucker,
                                    change_cat, similarity_negneg, similarity_pospos, similarity_posneg, similarity_negpos, year_diff_channel])
                

                tucker_profile.update({
                    'count': out_array.shape[0],
                    'dtype': 'float32',
                    'transform': tucker_transform,
                    'height': out_array.shape[1],
                    'width': out_array.shape[2]
                })

                with rasterio.open(f"{out_dir}/landsat_change_{row['fid']}", "w", **tucker_profile) as dst:
                    dst.write(out_array)

            except Exception as e:
                #print(f"Skipping {index}: {e}")
                continue
    
    # merge all outputs into a single mosaic
    # first get list of all files
    file_list = [os.path.join(out_dir, f) for f in os.listdir(out_dir) if f.startswith("landsat_change_")]
    mosaic_out = f"{out_dir}/landsat_change_mosaic.tif"
    
    print(len(file_list))
    
    if not os.path.exists(mosaic_out):
        try:
            from rasterio.merge import merge
            src_files_to_mosaic = []
            for fp in file_list:
                src = rasterio.open(fp)
                src_files_to_mosaic.append(src)
            mosaic, out_trans = merge(src_files_to_mosaic)
            out_meta = src_files_to_mosaic[0].meta.copy()
            out_meta.update({
                "height": mosaic.shape[1],
                "width": mosaic.shape[2],
                "transform": out_trans,
                'compress': 'LZW',
                'tiled': True,
                'blockxsize': 256,
                'blockysize': 256
            })
            with rasterio.open(mosaic_out, "w", **out_meta) as dest:
                dest.write(mosaic)
            print(f"Mosaic saved to {mosaic_out}")
        except Exception as e:
            print(f"Error creating mosaic: {e}")
