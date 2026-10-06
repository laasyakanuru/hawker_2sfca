# Subzone K-means clustering outputs

Two clustering specifications are kept side by side. They differ only in the
preprocessing of the clustering sample; both use the same three features
(`hdb_share`, `hdb_small_flat_share`, `pct_elderly`), StandardScaler, and
K-means with `n_init=25`, `random_state=42`.

Accessibility outcomes (SPAR, access_per_1000, pct_pop_no_access, stall deficit)
are **held out** of clustering and only joined afterwards for profiling. The
shared pipeline inputs they draw on (`fact_subzone_population.csv`,
`agg_access_subzone.csv`, `dim_subzone.csv`, ...) live in `data/processed/` and
are **not** part of this folder.

---

## `final_pop500/`  —  PRIMARY specification

Used in the final report / presentation.

- Population filter: `resident_pop >= 500`
- `pop_hdb == 0` → `hdb_small_flat_share` is **undefined (NaN) → row dropped**
  (keeps the clustering sample consistent with the regression preprocessing)
- Final sample: **n = 158** subzones
- **K = 3**, silhouette ≈ 0.366
- Cluster sizes: 57 / 71 / 30
- Underserved profile: **C1 = Larger-flat / lower-elderly HDB areas**
  (population-weighted SPAR ≈ 0.38 at the 1 km catchment; national average = 1.0)

Reproduce with:
```
python src/rerun_pop500.py                 # the 6 CSVs here
python src/make_underserved_map_pop500.py  # outputs/clustering/final_pop500/
```

## `legacy_pop1000/`  —  earlier / sensitivity specification

Retained for reproducibility and robustness context. Not the headline result.

- Population filter: `resident_pop >= 1000`
- `pop_hdb == 0` → `hdb_small_flat_share` **treated as 0** (row kept)
- Sample: **n = 212** subzones
- **K = 3**, silhouette ≈ 0.447
- Cluster sizes: 80 / 69 / 63

Reproduce with (run in order):
```
python src/build_clustering_features.py
python src/run_kmeans.py
python src/cluster_accessibility.py
python src/catchment_sensitivity.py
python src/feature_diagnostics.py     # 7-feature redundancy diagnostic
python src/cluster0_sanity_check.py   # robustness check of the low-access cluster
python src/make_figures.py            # outputs/clustering/legacy_pop1000/
```

---

## Substantive conclusion (both specifications)

The underserved neighbourhood type is the **larger-flat / lower-elderly HDB**
profile (newer / outer HDB estates), not the small-flat / older HDB profile.
This holds under both preprocessing rules and is stable across the 500 m,
1,000 m and 1,500 m catchments. Results are associations in the baseline 2SFCA
model; no causal claims are made.

## File naming

Filenames carry **no** `_main` / `_pop500` suffix — the folder name
(`final_pop500` vs `legacy_pop1000`) is the specification label. Matching
figures are under `outputs/clustering/<spec>/`.
