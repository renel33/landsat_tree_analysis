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
    predictions_rst = "/mnt/sdd/senegal_trends/{}_silver_sweep_9_102022.vrt"
    area_shp = "/mnt/sdc/tree_density_and_coverage/shapefiles/nasa_validation/senegal_cutlines_intersection_with_tiles_sorted_squares_960m_joined.gpkg"
    early_dir = "/mnt/sdb/senegal_model/output_predictions/20231114-1601_Model_1_martin_revised_labels_senegal_500ep_0.7norm_tversky04_06/rasters_early"
    late_dir = "/mnt/sdb/senegal_model/output_predictions/20231114-1601_Model_1_martin_revised_labels_senegal_500ep_0.7norm_tversky04_06/rasters_late"
    out_dir = "/mnt/sdd/senegal_trends/validation_change"
    os.makedirs(out_dir, exist_ok=True)
    ls_out_dir = "/mnt/sdd/senegal_trends/landsat_validation_change"
    os.makedirs(ls_out_dir, exist_ok=True)
    gdf = gpd.read_file(area_shp.replace(".gpkg", "_102022.gpkg"))

    save_path = "new_intermediate_results.pkl"
    save_every = 1000
    overwrite = True

    # --- Load checkpoint if it exists ---
    if os.path.exists(save_path) or overwrite == False:
        with open(save_path, "rb") as f:
            results = pickle.load(f)
        start_idx = results[-1]["index"] + 1  # resume after last processed row
        print(f"Resuming from iteration {start_idx}")
    else:
        results = []
        start_idx = 0
        print("Starting from scratch")
    # ------------------------------------

    for index, row in tqdm(gdf.iterrows(), total=len(gdf)):
        
        if index < start_idx:
            continue  # skip already processed rows
        
        #try:
        bounds = row.geometry.bounds
        early_year, late_year = row["early_year"], row["late_year"]

        early_raster = f"{early_dir}/{row['location']}"
        late_raster  = f"{late_dir}/{row['location_2']}"

        early_tucker, (profile, transform) = read_and_downsample_binary(early_raster, bounds, 1, 100, 0.5)
        late_tucker, (profile, transform) = read_and_downsample_binary(late_raster, bounds, 1, 100, 0.5)

        tucker_change = late_tucker - early_tucker
        tucker_change_avg = np.mean(late_tucker) - np.mean(early_tucker)
        tucker_change_sum = np.sum(late_tucker) - np.sum(early_tucker)
        
        with rasterio.open(f"{out_dir}/tucker_change_{row['fid']}", "w", **profile) as dst:
            dst.write(tucker_change, 1)

        early_data, (profile, transform) = read_and_downsample_binary(predictions_rst.format(early_year), bounds, 1, 100, 15)
        late_data, (profile, transform) = read_and_downsample_binary(late_raster.format(late_year), bounds, 1, 100, 15)

        #early_data = early_ls.read(1, window=rasterio.windows.from_bounds(*bounds, early_ls.transform))
        #late_data  = late_ls.read(1, window=rasterio.windows.from_bounds(*bounds, late_ls.transform))

        prediction_change = late_data - early_data
        
        with rasterio.open(f"{ls_out_dir}/landsat_change_{row['fid']}", "w", **profile) as dst:
            dst.write(prediction_change, 1)

        if prediction_change.size == 0:
            continue
            
            '''results_dict = {
                "index": index,
                "positive_ls_sum": prediction_change[prediction_change > 0].sum(),
                "negative_ls_sum": prediction_change[prediction_change < 0].sum(),
                "positive_tucker_sum": tucker_change_sum[tucker_change_sum > 0],
                "negative_tucker_sum": tucker_change_sum[tucker_change_sum < 0],
                "positive_ls_mean": prediction_change[prediction_change > 0].mean() if (prediction_change > 0).any() else 0,
                "negative_ls_mean": prediction_change[prediction_change < 0].mean() if (prediction_change < 0).any() else 0,
                "positive_tucker_mean": tucker_change_avg[tucker_change_avg > 0].mean() if (tucker_change_avg > 0).any() else 0,
                "negative_tucker_mean": tucker_change_avg[tucker_change_avg < 0].mean() if (tucker_change_avg < 0).any() else 0,
                "early_tucker_data_mean": np.nanmean(early_tucker),
                "late_tucker_data_mean": np.nanmean(late_tucker),
                "early_tucker_data_sum": np.nansum(early_tucker),
                "late_tucker_data_sum": np.nansum(late_tucker),
                "early_ls_data_mean": np.nanmean(early_data),
                "late_ls_data_mean": np.nanmean(late_data),
                "early_ls_data_sum": np.nansum(early_data),
                "late_ls_data_sum": np.nansum(late_data),
                "early_year": early_year,
                "late_year": late_year
            }
            
            results.append(results_dict)

            if (index + 1) % save_every == 0:
                with open(save_path, "wb") as f:
                    pickle.dump(results, f)
                print(f"Saved intermediate results at iteration {index+1}")'''

        if index == 10:
            break
            
        '''except Exception as e:
            print(f"Skipping {index}: {e}")
            continue'''

    # Convert results to DataFrame and merge back once
    
    res_df = pd.DataFrame(results).set_index("index")
    res_df = res_df.drop(columns=[c for c in res_df.columns if c in gdf.columns])
    gdf = gdf.join(res_df)

    gdf.to_file(area_shp.replace(".gpkg", "_results_new.gpkg"), driver="GPKG")