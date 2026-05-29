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


def read_raster(file):
    with rasterio.open(file) as src:
        return src.read(1)


def process_tree_row(input_tuple):
    
    row, landsat_prediction_dir, prediction_suffix, overwrite = input_tuple
    
    tile_id = row['id']
    landsat_grid_id = f"coords_{tile_id}_Landsat"
    geometry = row["geometry"]
    
    #country = row["Country_territory__ISO3_"]
    #region = row["gis_name"]

    raster_fps = sorted(glob.glob(f'{landsat_prediction_dir}/{landsat_grid_id}/**/*trend_{prediction_suffix}.tif', recursive=True))
    
    if len(raster_fps) == 0:
        tqdm.tqdm.write(f'No Landsat prediction found for {landsat_grid_id} for path {landsat_prediction_dir}/{landsat_grid_id}')
        return (None, 0)

    results = []
    
    for raster in raster_fps:
        
        with rasterio.open(raster) as r:
            try:
                
                rst = r.read()
                sigtrend = rst[4]
                sigdiff = rst[5]
                sigreldiff = rst[56]
                
                sigdiff = sigdiff * 214
                #sigdiff = sigdiff_m2 / 10000
                
                sigreldiff = sigreldiff * 214
                
                sigtrend = sigtrend * 214
                #sigtrend = sigtrend_m2 / 10000
                
                #calculate the percentage at the hectare level
                
                pos_sig_diff = abs(np.sum(np.where(sigdiff > 0, sigdiff, 0)))/(sigdiff.shape[0]*sigdiff.shape[1])
                neg_sig_diff = abs(np.sum(np.where(sigdiff < 0, sigdiff, 0)))/(sigdiff.shape[0]*sigdiff.shape[1])
                pos_sig_rel_diff = abs(np.sum(np.where(sigreldiff > 0, sigreldiff, 0)))/(sigreldiff.shape[0]*sigreldiff.shape[1])
                neg_sig_rel_diff = abs(np.sum(np.where(sigreldiff < 0, sigreldiff, 0)))/(sigreldiff.shape[0]*sigreldiff.shape[1])
                #nonsigdiff = np.sum(np.where(sigmask == 0, diff, 0))
                pos_sig_trend = abs(np.sum(np.where(sigtrend > 0, sigtrend, 0)))/(sigtrend.shape[0]*sigtrend.shape[1])
                neg_sig_trend = abs(np.sum(np.where(sigtrend < 0, sigtrend, 0)))/(sigtrend.shape[0]*sigtrend.shape[1])
                
                summed_pos_diff_m2 = abs(np.sum(np.where(sigdiff > 0, sigdiff, 0)))
                summed_neg_diff_m2 = abs(np.sum(np.where(sigdiff < 0, sigdiff, 0)))
                
                pos_pixels = np.sum(np.where(sigdiff > 0, 1, 0))
                neg_pixels = np.sum(np.where(sigdiff < 0, 1, 0))
                
                total_pixels = sigdiff.shape[0]*sigdiff.shape[1]
                
                results.append((geometry, tile_id, pos_sig_diff, 
                                neg_sig_diff, pos_sig_trend, neg_sig_trend, pos_sig_rel_diff, neg_sig_rel_diff,
                                summed_pos_diff_m2, summed_neg_diff_m2,
                                pos_pixels, neg_pixels, total_pixels))
                
                count =+ 1
                return (pd.DataFrame(results, columns=["geometry", "tile_id", 
                                                       "pos_sig_diff", "neg_sig_diff", "pos_trend", 
                                                       "neg_trend", 'pos_diff_m2', 'neg_diff_m2',
                                                       'pos_pixels', 'neg_pixels', 'total_pixels']), count)
                
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
    shape = gpd.read_file('/mnt/sdc/tree_density_and_coverage/shapefiles/sahel_downloader/sahel_gee_download_only_semi_arid_final_regions.gpkg')
    #shape = gpd.read_file('/mnt/sdc/tree_density_and_coverage/shapefiles/drylands/maradi_tiles.gpkg')

    # remove null rows
    shape = shape[~shape["id"].isnull()]
    #shape = shape[shape["id"] == "8_15_6"]
    print(len(shape.index))

    landsat_prediction_dir = '/mnt/sdd/ls789gf'
    ps_prediction_dir = "/nfs/Users/Martin/Tree_explorer/tree_cover/Africa"

    prediction_suffix = "silver_sweep_9_ps_no_dilation"

    # calculate individual tree stats
    data = tree_stats(shape, landsat_prediction_dir, prediction_suffix, False, True)
    dfs, total = data
    df = pd.concat(dfs)
    df.to_csv(f"significant_trends_ls789_hct_trend_m2_ps_v4.csv", index=False)
    gdf = gpd.GeoDataFrame(df, geometry="geometry")
    gdf.to_file("significant_trends_ls789_wc_hct_trend_m2_ps_v4.gpkg", driver="GPKG")
    
    
