# Landsat Tree Cover Change Analysis — Sahel

Code for detecting and quantifying changes in tree cover across the Sahel region using Landsat satellite imagery at 15 m resolution. This repository supports the analysis in:

> **[Paper title]** — [Authors], *Nature Sustainability*, [Year]. DOI: [paper DOI]

A companion repository for GEE-based image preprocessing is available at: https://github.com/renel33/gee_landsat_preprocessing_and_download

---

## Overview

The analysis pipeline:
1. Applies a pre-trained U-Net model to Landsat 7/8/9 imagery to produce 15 m tree cover predictions.
2. Computes per-pixel temporal trends (slope + significance) across the 2000–2020 period.
3. Aggregates results by country, region, and land-cover class (cropland vs. shrubland).
4. Validates trends against Very High Resolution (VHR) Planet imagery.
5. Generates all main-text and supplementary figures.

---

## Repository structure

```
landsat_tree_analysis/
├── src/
│   ├── significance.py            # Per-tile trend significance computation
│   ├── analyse_predictions.py     # Tree cover statistics by country/region
│   ├── analyse_predictions_v3.py  # Extended analysis (main version used in paper)
│   ├── trend_validation.py        # Trend validation against VHR Planet data
│   ├── relative_diff_v3.ipynb     # Main analysis notebook (produces paper figures)
│   ├── minimum_detectable_tree.py # Detection-limit analysis
│   └── downsample.py              # Raster downsampling utilities
├── notebooks/
│   ├── change_validation.ipynb    # Change detection validation
│   └── buildvrt.ipynb             # Building GDAL VRT mosaics
├── validation/                    # Shapefiles for accuracy assessment
├── shapefiles/                    # Study-area boundary files
├── maurice_model/                 # Pre-trained U-Net weights (.h5)
├── requirements.txt
├── LICENSE
└── README.md
```

---

## System requirements

- **OS**: Linux (tested on Ubuntu 20.04 and 22.04); macOS should work
- **Python**: 3.8 – 3.11
- **RAM**: ≥32 GB recommended for processing full Sahel tiles
- **Disk**: Model outputs from the full analysis are ~2 TB; the scripts can be run on subsets

Python package dependencies are listed in `requirements.txt`. Key packages:

| Package | Version tested | Purpose |
|---|---|---|
| `numpy` | 1.24 | Array operations |
| `rasterio` | 1.3 | Raster I/O |
| `geopandas` | 0.13 | Vector data handling |
| `scipy` | 1.10 | Statistics |
| `pandas` | 2.0 | Tabular data |
| `matplotlib` / `seaborn` | 3.7 / 0.12 | Figures |

---

## Installation

```bash
git clone https://github.com/<your-username>/landsat_tree_analysis.git
cd landsat_tree_analysis
pip install -r requirements.txt
```

Typical install time on a standard laptop: ~5 minutes (conda environment recommended).

Using conda:
```bash
conda create -n fmnr python=3.10
conda activate fmnr
pip install -r requirements.txt
```

---

## Data

The analysis requires Landsat-derived tree cover prediction tiles produced by the preprocessing pipeline. These are not included in the repository due to size (~2 TB), but are archived at:

> **Zenodo DOI**: [to be added upon publication]

The pre-trained model weights are included under `maurice_model/` (U-Net trained on 25 cm resolution Planet imagery over Niger, 2019; see Methods in the paper for details).

---

## Usage

### 1. Compute trend significance per tile

```bash
python src/significance.py \
  --prediction_dir /path/to/landsat_predictions \
  --grid_shp shapefiles/grid.gpkg \
  --output_dir /path/to/output
```

Processes all tiles in parallel using `ProcessPoolExecutor`. Expected run time: ~4 hours for the full Sahel grid (~4,000 tiles) on a 32-core machine.

### 2. Aggregate statistics by country

```bash
python src/analyse_predictions_v3.py \
  --prediction_dir /path/to/output \
  --grid_shp shapefiles/grid.gpkg
```

Outputs a CSV of tree cover change statistics per tile, with country/region attribution. Expected run time: ~2 hours on a 32-core machine.

### 3. Reproduce paper figures

Open and run `src/relative_diff_v3.ipynb` in Jupyter, pointing `crop_df` and `shrub_df` to the CSVs produced in step 2.

Expected run time: < 5 minutes on any modern laptop.

### 4. Trend validation

```bash
python src/trend_validation.py \
  --landsat_dir /path/to/landsat_predictions \
  --vhr_dir /path/to/planet_tiles \
  --grid_shp shapefiles/grid.gpkg
```

---

## Demo

A small test subset (5 tiles from Niger) is available in the Zenodo archive under `demo_data/`. To run:

```bash
python src/significance.py \
  --prediction_dir demo_data/predictions \
  --grid_shp shapefiles/grid.gpkg \
  --output_dir demo_data/output

python src/analyse_predictions_v3.py \
  --prediction_dir demo_data/output \
  --grid_shp shapefiles/grid.gpkg
```

Expected output: a CSV similar to `demo_data/expected_output/demo_results.csv`.
Expected run time: < 10 minutes on a standard laptop (4 cores).

---

## License

MIT — see [LICENSE](LICENSE).

## Citation

If you use this code, please cite:

```
[BibTeX to be added upon publication]
```

## Contact

Rene Arum Lee — rene.arum.lee@gmail.com
