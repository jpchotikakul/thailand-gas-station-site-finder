# Thailand Gas Station Site Finder

A **site-selection and investment-screening** tool for land in Thailand that may suit a high-traffic petrol or service station. It is not a complete national property search, and it is not investment, legal or engineering advice.

**Live site:** https://piyaster11.github.io/thailand-gas-station-site-finder/

**Repository:** https://github.com/piyaster11/thailand-gas-station-site-finder

Open the [About / methodology](https://piyaster11.github.io/thailand-gas-station-site-finder/about.html) page on the site for the full scoring rules, badge meanings and source audit. A short version is below.

## What the site does

- Collects **public land-for-sale listings** from Thai property sites that allow crawling
- Converts land area (rai / ngan / square wah / sqm) and calculates price per rai only when both price and area are known
- Places each listing on an interactive map of Thailand (Leaflet), with a satellite layer
- Enriches mapped sites with **OpenStreetMap**: nearest major road, lane tags, competing `amenity=fuel` stations within 1 / 3 / 5 / 10 km, and nearby industrial, retail, EV, school, hospital and tourism features
- Scores every site **0–100** with configurable weights (defaults: traffic 30, road access 20, land size 15, competition 15, demand generators 10, price/value 10)
- Lets you filter, shortlist, compare up to four sites, and export a CSV
- Marks every field **Verified**, **Calculated**, **Estimated** or **Data not available** — it does not invent traffic counts, zoning, dimensions or prices

## Repository layout

```
pipeline/               Python data pipeline (standard library only)
  collect.py            Polite collectors for DotProperty and FazWaz
  enrich.py             Nominatim (when precise enough) + Overpass / OSM
  score.py              Suitability model and advantage / risk text
  run.py                Orchestrator — writes docs/data/listings.json
docs/                   GitHub Pages site (no build step)
  index.html            Map, filters, scores, compare
  about.html            Methodology and provenance
  data/listings.json    Published dataset (meta + listings)
.github/workflows/update-data.yml   Weekly + manual refresh
```

## How to run the pipeline

Python 3.11 or newer. No third-party packages.

```bash
python -m pipeline.run --max-pages 3 --delay 1.25
```

- `--max-pages` caps how many search pages are fetched per province (and the national list)
- `--delay` is the minimum pause between HTTP requests (plus a little jitter)
- `--skip-collect` reuses `pipeline/cache/raw_listings.json` and only re-enriches and rescores
- `--skip-geocode` skips Nominatim

The pipeline identifies itself as `ThailandGasStationSiteFinder/1.0`, follows robots.txt for the paths it uses, retries 429/5xx, and **stops** if a site returns a captcha or access block. It does not log in, and it does not call FazWaz `/api/` or `/graphql` (those paths are disallowed).

Cache files under `pipeline/cache/` (raw harvests, Overpass extracts, Nominatim answers) are gitignored. The published file is `docs/data/listings.json`.

To preview the site locally:

```bash
python -m http.server 8080 --directory docs
```

Then open http://127.0.0.1:8080/

## Data sources

| Source | Role in this project |
| --- | --- |
| [DotProperty](https://www.dotproperty.co.th/en/land-for-sale) | Primary. Public land pages include schema.org ItemList records with coordinates, price, photos and address. |
| [FazWaz](https://www.fazwaz.com/land-for-sale/thailand) | Supplementary cards (price, area, address, photo). Public HTML has no GPS; a pin is added only when subdistrict + district + province can be geocoded, and that pin is labelled Estimated. |
| OpenStreetMap (Overpass, or a [Geofabrik](https://www.geofabrik.de/) Thailand shapefile extract if Overpass is unreachable) | Roads, fuel stations, demand generators. © OSM contributors, ODbL. |
| Nominatim | Locality geocoding, used only when the listing names a subdistrict, district and province. |
| [DPT city-plan viewer](https://onedpt.dpt.go.th/) | Linked for zoning. Zoning is never guessed. |

Tried and **not** collected in the first harvest (blocks or disallowed paths — no captcha bypass): DDproperty (Cloudflare challenge), Hipflat (HTTP 401), Baania (Cloudflare IP block), Livinginsider sitemap (CloudFront 403), Kaidee / home.co.th search and API paths (disallowed in robots.txt).

The published file always states how many listings were actually collected and from which sources. It is a screening sample, not every plot for sale in Thailand. DotProperty and FazWaz share inventory; records are deduplicated.

## This harvest (10 Nov 2026, Asia/Bangkok)

- **5,429** land-for-sale listings from **DotProperty**, covering **all 77 provinces**
- Every listing in this file has published coordinates (4,193 seller-placed listing pins, labelled “Listing pin (seller-placed, approximate)” — not Verified; 1,236 flagged as area centroids because several listings share the exact point). **520** pins are flagged “Pin may be inaccurate” because they sit on or next to an OSM road or junction (506 on a carriageway buffer, 292 at a junction; some are both).
- **545** score 70 or above with the default weights
- FazWaz was tried in the same run but returned **HTTP 403**, so it is not in this file. The collector is still in `pipeline/collect.py` for a later refresh.
- Nearby roads and fuel stations come from a Geofabrik OSM extract (Overpass was unreachable from the machine that built this file)

## Scoring, traffic and zoning

- **Traffic potential** is an Estimated 0–100 *proxy* from OSM road class, lanes (when tagged), distance to a major road, nearby major roads, and nearby activity. Official Department of Highways traffic counts were not matched to individual sites and are shown as Data not available — they are not invented.
- **Competition** uses OSM `amenity=fuel` counts at 1 / 3 / 5 / 10 km (Estimated; OSM coverage varies).
- **Missing factors:** location-dependent factors without coordinates are scored 35 (penalty). Missing price or area is scored 50 (neutral). Data completeness is the share of weight that came from computed factors, not these imputations.
- **Marker colours:** green 70+, yellow 45–69, red below 45.
- **Listing pins** are seller-placed and approximate, never Verified. Pins that sit on or next to an OSM road / junction are flagged “Pin may be inaccurate”; derived road, competitor and traffic figures then carry a reduced-confidence note. Use the “Hide listings with suspect pins” filter to exclude them.
- Weights can be changed in the UI; factor scores stay as computed by the pipeline and are only re-averaged in the browser.

## GitHub Pages

The site is served from the `docs/` folder on the `main` branch. The workflow `.github/workflows/update-data.yml` can refresh `docs/data/listings.json` every Monday at 09:00 Asia/Bangkok, or on demand. Please keep delays polite on scheduled runs.

## Disclaimer

Verify the title deed (chanote), access, zoning and on-the-ground conditions with a surveyor and the local authorities before making a decision. Listing text and photos remain the property of their publishers; this independent tool links back to the original listing.
