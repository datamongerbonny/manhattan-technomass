# Manhattan Technomass

A replication of the **Technomass** method (Inostroza 2014) for Manhattan, New York: how much built material (buildings plus sealed ground, in m³ per hectare) sits on the land, how it falls off with distance from the Midtown CBD, and when it was built.

One Python script does everything: downloads the data, samples the island, calculates Technomass and draws the figures.

## Quick start

You need Python 3.9 or newer.

```bash
pip install -r requirements.txt
python manhattan_technomass.py
```

The first run downloads about 45 MB of data and takes a few minutes. Results are written to `technomass_output/`.

## Data

Downloaded automatically on the first run; nothing to fetch by hand.

| File | Source |
|---|---|
| `nyc_buildings_manhattan.geojson` | [NYC Open Data, Building Footprints](https://data.cityofnewyork.us/d/5zhs-2jue) (dataset `5zhs-2jue`), filtered to Manhattan. Roof heights and construction years. |
| `boroughs.geojson` | NYC borough boundaries ([dwillis/nyc-maps](https://github.com/dwillis/nyc-maps)) |

NYC updates the building data regularly. Delete `nyc_buildings_manhattan.geojson` to force a fresh download of the latest version.

If the NYC Open Data download fails (for example on patchy wifi), the script retries five times, then falls back to a GitHub copy of the footprints and prints a large **WARNING**. That copy has no construction years, so Figs. 8–9 come out empty. Re-run when you have a better connection.

## Method in brief

- **Technomass** T = (building volume + 0.5 m × sealed non-building land) ÷ sample area, in m³/ha. Building volume is footprint area × roof height.
- **CBD:** Midtown, near Grand Central and Bryant Park.
- **Samples:**
  - 150 random, non-overlapping 7-ha circles across the main island (parks with under 5% building cover are skipped)
  - 32 circles every 450 m along a transect following the street grid (29° east of north)
  - square samples of 64 ha and 9 ha at five sites from Midtown to Inwood
- **Accumulation rate:** building volume grouped by construction period, per hectare per year.
- The random seed is fixed (42), so everyone gets the same sample locations.

## Outputs

`technomass_output/` in this repo holds a reference run made on 8 October 2026, so you can check your results against it.

| File | What it shows |
|---|---|
| `manhattan_technomass_samples.png` | Sample map (analogue of Fig. 3) |
| `fig4_square_samples.png` | Square sample sites with close-ups |
| `fig5_circular_all.png` | Technomass vs distance to CBD, circular samples |
| `fig6_transect.png` | Technomass along the transect |
| `fig7_squares.png` | Technomass vs distance, square samples |
| `fig8_rate_squares.png` | Accumulation rate by construction period, squares |
| `fig9_rate_circular.png` | Accumulation rate by construction period, circles |
| `manhattan_technomass_distance.png` | Figs. 5 and 6 side by side |
| `table2_manhattan.csv` | Summary table (analogue of Table 2) |
| `manhattan_technomass_samples.csv` | Every sample with its coordinates and components |
| `run_log.txt` | Console output of the reference run |

### Reference results (8 Oct 2026)

| Samples | Average (m³/ha) | Min | Max |
|---|---|---|---|
| Squared small (9 ha) | 192,720 | 57,683 | 599,327 |
| Squared big (64 ha) | 183,498 | 68,175 | 528,702 |
| Circular (all, n=150) | 162,661 | 22,570 | 684,691 |
| Circular transect (n=32) | 217,648 | 36,151 | 621,691 |
| **Total average** | **189,132** | 46,145 | 608,603 |

**Will my numbers match?** They should, to within a fraction of a percent. Small differences mean NYC has updated some building records since the reference run. Large differences (several percent), or empty Figs. 8–9, mean the fallback data was used; look for the WARNING in your console.

## Known limitations

- **Missing heights.** 75 buildings have no roof height and are assigned 4 m.
- **Undated buildings.** About 3% of building volume has no construction year. It counts toward Technomass but not toward the accumulation rates.
- **Pre-1860 buildings.** About 2,200 buildings dated before 1860 fall outside the period bins in Figs. 8–9, so they are left out of the rate charts. Add a period such as `(1600, 1859)` to `PERIODS` in the script to include them.
- **Projection.** Coordinates use a simple local metric projection centred on Manhattan. That is accurate enough at this scale, but it is not a survey-grade CRS.

## Reference

Inostroza, L. (2014). Measuring urban ecosystem functions through 'Technomass' — A novel indicator to assess urban metabolism. *Ecological Indicators*, 42, 10–19.
