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


def process_tree_row(input_tuple):
    
    row, landsat_prediction_dir, prediction_suffix, overwrite = input_tuple
    
    tile_id = row['id']
    landsat_grid_id = f"coords_{tile_id}_Landsat"
    geometry = row["geometry"]
    
    country = row["Country_territory__ISO3_"]
    region = row["gis_name"]
    precip = row["DN"]

    raster_fps = sorted(glob.glob(f'{landsat_prediction_dir}/{landsat_grid_id}/**/*{prediction_suffix}.tif', recursive=True))
    
    if len(raster_fps) == 0:
        tqdm.tqdm.write(f'No Landsat prediction found for {landsat_grid_id} for path {landsat_prediction_dir}/{landsat_grid_id}')
        return (None, 0)

    results = []
    
    for raster in raster_fps:
        
        with rasterio.open(raster) as r:
            try:
                
                sigdiff = r.read(2)
                
                pos_sig_diff = abs(np.where(sigdiff > 0, sigdiff, 0)).mean()
                neg_sig_diff = abs(np.where(sigdiff < 0, sigdiff, 0)).mean()
                net_sig_diff = abs(sigdiff).mean()
                
                summed_pos_diff_m2 = abs(np.sum(np.where(sigdiff > 0, sigdiff, 0)))
                summed_neg_diff_m2 = abs(np.sum(np.where(sigdiff < 0, sigdiff, 0)))
                
                pos_pixels = np.sum(np.where(sigdiff > 0, 1, 0))
                neg_pixels = np.sum(np.where(sigdiff < 0, 1, 0))
                
                total_pixels = sigdiff.shape[0]*sigdiff.shape[1]
                
                results.append((geometry, tile_id, country, region, precip, pos_sig_diff, 
                                neg_sig_diff, net_sig_diff, summed_pos_diff_m2, summed_neg_diff_m2,
                                pos_pixels, neg_pixels, total_pixels))
                
                count =+ 1
                return (pd.DataFrame(results, columns=["geometry", "tile_id", "country", "region", "precip", 
                                                       "mean_pos_sig_diff", "mean_neg_sig_diff", "mean_net_sig_diff",
                                                       'pos_diff_m2', 'neg_diff_m2', 'pos_pixels', 'neg_pixels', 
                                                       'total_pixels']), count)
                
            except ValueError as e:
                tqdm.tqdm.write(f'Error reading raster {raster}: {e}')
                return (None, 0)
    
            
def tree_stats(shape, landsat_prediction_dir, prediction_suffix, multiprocess=True, overwrite=False):
    
    total = 0 
    rows = [(row, landsat_prediction_dir, prediction_suffix, overwrite) for index, 
                                        row in shape.iterrows()]
    if multiprocess:
        # Use ProcessPoolExecutor to parallelize the processing
        with ProcessPoolExecutor(max_workers=20) as executor:
            gdfs = list(tqdm.tqdm(executor.map(process_tree_row, rows),
                                total=len(rows)))
    else:
        gdfs = []
        for row in tqdm.tqdm(rows):
   
            result = process_tree_row(row)
            df, count = result
            total += count
            gdfs.append(df)
         
    return (gdfs, total)



if __name__ == "__main__":

    # Load shapefile
    shape = gpd.read_file('/mnt/sdc/tree_density_and_coverage/shapefiles/sahel_downloader/sahel_gee_download_only_semi_arid_final_regions_precip.gpkg')

    # remove null rows
    shape = shape[~shape["id"].isnull()]
    #shape = shape[shape["id"] == "8_15_6"]
    print(len(shape.index))

    landsat_prediction_dir = '/mnt/sdd/ls789gf'
    prediction_suffix = "significant_relative_diff_silver_sweep_9_shrub_2020"

    # calculate individual tree stats
    data = tree_stats(shape, landsat_prediction_dir, prediction_suffix, False, True)
    dfs, total = data
    df = pd.concat(dfs)
    df.to_csv(f"non_significant_rel_diff_ls789_m2_{prediction_suffix}.csv", index=False)
    
    #gdf = gpd.GeoDataFrame(df, geometry="geometry")
    #gdf.to_file(f"significant_rel_diff_ls789_m2_{prediction_suffix}.gpkg", driver="GPKG")
    
    
