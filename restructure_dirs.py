import os
import shutil
from tqdm import tqdm 

in_dir = "/mnt/sdd/senegal_landsat"
out_dir = "/mnt/sdd/senegal_landsat_predictions"
os.makedirs(out_dir, exist_ok=True)

for year in tqdm(os.listdir(in_dir), position=0, desc="Processing years", disable=False):
    
    year_dir = os.path.join(in_dir, year)
    for file in tqdm(os.listdir(year_dir), position=1, desc=f"Processing files for year {year}", leave=False):
        if file.endswith("silver_sweep_9.tif"):
            file_path = os.path.join(year_dir, file)
            grid_id = f"{file.split('_')[0]}_{file.split('_')[1]}_{file.split('_')[2]}_{file.split('_')[3]}"
            new_grid_dir = os.path.join(out_dir, grid_id)
            os.makedirs(new_grid_dir, exist_ok=True)
            grid_year_dir = os.path.join(new_grid_dir, year)
        os.makedirs(grid_year_dir, exist_ok=True)
            new_file_path = os.path.join(grid_year_dir, f"{grid_id}_{year}_silver_sweep_9.tif")
            shutil.copy(file_path, new_file_path)