# Landsat Tree Cover Change Analysis — Sahel

Code for detecting and quantifying changes in tree cover across the Sahel region using Landsat satellite imagery at 15 m resolution. This repository accompanies:

> **Farmer Managed Natural Regeneration Promotes Expansion of Trees on Croplands in the Sahel** — *Nature Sustainability* (under review)

Preprocessing code (GEE download pipeline) is in a companion repository:
https://github.com/renel33/gee_landsat_preprocessing_and_download

---

## System requirements

**Operating system:** Linux (tested on Ubuntu 20.04 and 22.04); macOS 12+ should work.

**Python:** 3.8 – 3.11 (tested on 3.10.12)

**No non-standard hardware is required to run the demo.** The full analysis (Step 1–2 below) requires ≥32 GB RAM and ~2 TB disk for the full Sahel dataset; a 32-core CPU reduces runtime from weeks to ~6 hours.

**Python package dependencies** (exact versions tested in parentheses):

| Package | Tested version | Purpose |
|---|---|---|
| `numpy` | 1.24.3 | Array operations |
| `scipy` | 1.10.1 | Trend statistics |
| `pandas` | 2.0.3 | Tabular data |
| `geopandas` | 0.13.2 | Vector / geospatial data |
| `rasterio` | 1.3.8 | Raster I/O |
| `matplotlib` | 3.7.2 | Figures |
| `seaborn` | 0.12.2 | Figures |
| `tqdm` | 4.65.0 | Progress bars |

---

## Installation

```bash
git clone https://github.com/renel33/landsat_tree_analysis.git
cd landsat_tree_analysis
pip install -r requirements.txt
```

**Typical install time on a normal desktop computer: ~5 minutes.**

Using conda (recommended):
```bash
conda create -n fmnr python=3.10
conda activate fmnr
pip install -r requirements.txt
```

---

## Demo

A self-contained demo runs entirely on the two CSV files committed in this repository, requiring no external data or large downloads.

**Instructions:**

```bash
jupyter notebook demo.ipynb
```

Run all cells in order (Kernel → Restart & Run All).

**Expected output:** A bar chart (`demo_output_relative_gain.png`) showing the relative gain in tree cover on croplands vs. shrublands for each Sahel country, consistent with the paper's main finding. Summary statistics are printed in the final cell.

**Expected run time: < 2 minutes on a normal desktop computer (any CPU).**

The demo uses `significant_trends_ls789_wc_hct.csv` (2,284 tiles across the Sahel) and `significant_trends_ls789_wc_hct_trend.csv`, which are included in this repository.

---

## Repository structure

```
landsat_tree_analysis/
├── demo.ipynb                         # Self-contained demo (START HERE)
├── significant_trends_ls789_wc_hct.csv        # Demo data: per-tile tree cover statistics
├── significant_trends_ls789_wc_hct_trend.csv  # Demo data: per-tile trend statistics
├── src/
│   ├── significance.py            # Step 1: per-tile trend significance computation
│   ├── significance_relative_diff.py  # Step 1b: cropland variant
│   ├── significance_shrubland.py  # Step 1c: shrubland variant
│   ├── analyse_predictions_v3.py  # Step 2: aggregate by country/region (paper version)
│   ├── trend_validation.py        # Validation against VHR Planet imagery
│   ├── relative_diff_v3.ipynb     # Figure generation notebook (paper figures)
│   ├── minimum_detectable_tree.py # Detection-limit analysis
│   └── downsample.py              # Raster downsampling utilities
├── notebooks/
│   └── change_validation.ipynb    # Change detection validation
├── validation/                    # Shapefiles for accuracy assessment
├── shapefiles/                    # Study-area boundary files
├── maurice_model/                 # Pre-trained U-Net weights (.h5)
├── requirements.txt
├── LICENSE
└── README.md
```

---

## Instructions for use on your own data

The main analysis scripts use path variables configured at the top of the
`if __name__ == "__main__":` block. To run on your data, open the script
and edit those variables before running.

### Step 1 — Compute per-tile trend significance

Edit `src/significance.py`, updating these variables:

```python
# Line ~120 in src/significance.py
shape = gpd.read_file('/path/to/your/grid.gpkg')       # analysis grid shapefile
landsat_prediction_dir = '/path/to/landsat_predictions' # dir of Landsat tree cover rasters
prediction_suffix = 'your_model_suffix'                 # filename suffix identifying predictions
```

Then run:
```bash
python src/significance.py
```

Processes all tiles in parallel. **Expected run time: ~4 hours for the full Sahel (~4,000 tiles) on a 32-core server.** Output: a CSV of per-tile statistics.

### Step 2 — Aggregate by country and region

Edit `src/analyse_predictions_v3.py` (same path variables as Step 1), then:

```bash
python src/analyse_predictions_v3.py
```

**Expected run time: ~2 hours on a 32-core server.** Output: CSV and GeoPackage of country-level statistics.

### Step 3 — Reproduce paper figures

Open `src/relative_diff_v3.ipynb` in Jupyter. Update the CSV paths in the first code cell to point to the CSVs produced in Step 2, then run all cells.

**Expected run time: < 5 minutes on any laptop.**

### Step 4 — Validate against VHR data (optional)

Edit the path variables in `src/trend_validation.py` to point to your Planet/VHR tiles, then:
```bash
python src/trend_validation.py
```

---

## Data

The full Landsat-derived tree cover prediction tiles (~2 TB) are archived at:

> **Zenodo DOI**: [to be added upon publication]

---

## License

MIT — see [LICENSE](LICENSE).

## Citation

```
[BibTeX to be added upon publication]
```

## Contact

Rene Arum Lee — rene.arum.lee@gmail.com
