# ASI: Zenodo Dataset and Artifact Bundle (Conference Record)

## Overview
This curated package contains the dataset and reproducibility artifacts for the conference paper:

**ASI: A Closed-Loop Robustness Proxy for Spatial Flight-Stability Mapping Using PX4 Flight Logs**

This record contains the dataset and artifact bundle supporting the ASI project, which studies spatial closed-loop robustness using PX4 flight logs. The release includes curated raw logs, processed feature tables, experiment manifests, controller parameter files, selected reproducibility scripts, and figure assets corresponding to the analyses reported in the conference paper.

## What is included
- `data/raw_logs/` : curated PX4 ULog files for E1–E5 environments
- `data/processed_tables/` : environment summaries and processed tables
- `data/feature_tables/` : feature-level CSV tables used in ASI analysis
- `data/manifests/` : experiment manifests and ULog contract files
- `data/params/` : controller parameter files used in intervention experiments
- `data/stats/` : statistical summary outputs
- `data/normalization/` : normalization constants used in ASI computation
- `figures/paper_main/` : main figures used in the conference paper
- `figures/supplementary/` : supplementary figure assets
- `code/preprocessing/` : dataset assembly and extraction scripts
- `code/analysis/` : ASI computation and statistics scripts
- `code/plotting/` : figure-generation scripts

## What was intentionally excluded
The following materials were reviewed but excluded from this Zenodo package to keep the record publication-grade and focused on the conference paper:
- macOS metadata (`__MACOSX`, `.DS_Store`)
- Python virtual environments (`.venv`, `asi_env`, `asi_viz_venv`)
- temporary files (`tempCodeRunnerFile.py`, duplicated `test.py` files)
- outdated or obviously redundant exploratory assets

## Environments
The curated raw-log dataset includes:
- E1_openfield
- E2_nearwall
- E3_corridor
- E4_nearground
- E5_rooftop_edge

## Notes
- ASI is interpreted as a hover-probe-based robustness proxy for a specific UAV/controller configuration.
- This package is intended to support reproducibility of the conference paper results.
- The paper PDF is intentionally not included in this Zenodo dataset package.

## Authors
- Jayawant Bodagala
- Balaji Bodagala
