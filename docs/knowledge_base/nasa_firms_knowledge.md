# NASA FIRMS & Earthdata Technical Knowledge Base (2026 Standards)

## 1. Transition from Suomi NPP to NOAA-20 and NOAA-21
* **Cessation Date:** Delivery of new operational science data, active fire alerts, burned area products, and imagery from the **Suomi National Polar-orbiting Partnership (Suomi NPP)** satellite ceased on **November 2, 2026** (13:00 UTC for FIRMS active fire streams; 15:40 UTC for LANCE streams). Historical Suomi NPP data prior to November 2, 2026 remains archived and accessible.
* **Replacement Satellites:** Operational workflows have transitioned to the Joint Polar Satellite System (JPSS) series: **NOAA-20 (JPSS-1)** and **NOAA-21 (JPSS-2)**. Both carry identical Visible Infrared Imaging Radiometer Suite (VIIRS) instruments providing **375-meter** (and 750m) spatial resolution, flying in the same orbital plane roughly 50 minutes apart to ensure uninterrupted daytime and nighttime monitoring.
* **File Naming & API Migration Conventions:**
  * **VIIRS Active Fire / Land / Reflectance:** Prefix changes from `VNP` (e.g., `VNP14IMG` / `VNP14IMGTDL`) to `VJ1` for NOAA-20 (e.g., `VJ114IMG`) and `VJ2` for NOAA-21 (e.g., `VJ214IMG`).
  * **FIRMS API / Script Sensor Parameters:** Change `VIIRS_SNPP_NRT` (or `VIIRS_SNPP_SP`) to `VIIRS_NOAA20_NRT` or `VIIRS_NOAA21_NRT`.
  * **VIIRS Atmosphere (Aerosol):** Changes from `AERDB_L2_VIIRS_SNPP` to `AERDB_L2_VIIRS_NOAA20` and `AERDB_L2_VIIRS_NOAA21`.
  * **OMPS Ozone / SO2:** Changes from `NPP_NMTO3-L2` to `J1_NMTO3-L2` and `J2_NMTO3-L2`.
* **Other Satellite Sensors in FIRMS:**
  * **MODIS (Terra & Aqua):** Provides 1 km spatial resolution for long-term historical trend analysis. Terra provides a morning overpass (~3 hours before Aqua), while Aqua has an afternoon overpass similar to VIIRS.
  * **Geostationary Satellites (GOES-East/West, Himawari, Meteosat):** Provide high temporal frequency (every 10–15 minutes) to track rapid fire growth, but at coarser spatial resolution (2 km for GOES ABI and Himawari AHI; 3 km for MSG SEVIRI; 1 km sub-nadir for Meteosat Third Generation). Pixel size grows coarser toward the edge of the Earth disk.

## 2. NOAA-21 OMPS Aerosol Index & Pyrocumulonimbus (PyroCb) Layers
* **Purpose:** Introduced into NASA FIRMS (with archive data back to April 28, 2025) to track atmospheric smoke plumes, dust storms, and volcanic ash daily.
* **Spatial Resolution Upgrade:**
  * **NOAA-21 OMPS (Newest):** 12 km x 10 km (~6 x 6 miles)
  * **NOAA-20 OMPS:** 17 km x 12 km (~10.5 x 7.5 miles)
  * **Suomi NPP OMPS (Legacy):** 50 km x 50 km (~31 x 31 miles)
* **Layer Selection Guide:**
  * **Regular Aerosol Index (Range 0.0 to 5.0):** Best for everyday air quality and visibility monitoring near the surface.
  * **Pyrocumulonimbus (PyroCb) Aerosol Index (Range 0.0 to 50.0):** Designed for extreme wildfire smoke or volcanic eruptions. Values **greater than 10** indicate aerosols injected high into the upper troposphere (16,000–40,000 ft) or lower stratosphere (>40,000 ft).

## 3. Satellite Swath Outlines & Observation Coverage
* **Definition:** A "swath" is the horizontal width of Earth's surface imaged by a sensor perpendicular to its orbital track during a single overpass. Swath outlines are derived from Level-2 metadata bounding coordinates (5-minute granules for MODIS; 6-minute granules for VIIRS) and should not be used for exact edge-of-swath area measurements.
* **MODIS vs. VIIRS Coverage Characteristics:**
  * **MODIS Swath Width:** **2,300 km**. Because of this narrower width, a single MODIS sensor cannot image the entire globe in one day—leaving coverage gaps of approximately **350 km** between consecutive orbits near the equator (between 30°N and 30°S).
  * **VIIRS Swath Width:** **3,040 km**. Consecutive VIIRS orbits overlap by approximately **350 km** at the equator, enabling a single VIIRS sensor to image the entire Earth daily. Areas near swath edges can be observed twice within 100 minutes, and high-latitude regions can be imaged 6 to 8 times per day per sensor.
* **Scientific Implication for Analytics:** Raw detection counts differ between sensors partly due to swath width, spatial resolution (375m vs 1km), and orbital overpass frequency—not solely because of differences in actual fire incidence.

## 4. Dynamic Multispectral Imagery with TiTiler-CMR & HLS
* **Overview:** Released in 2025 and integrated into NASA Worldview and FIRMS in 2026, **TiTiler-CMR** is an open-source service that dynamically renders on-demand map tiles directly from NASA's Common Metadata Repository (CMR) without pre-processing (supporting COG, NetCDF, HDF-5, and GRIB).
* **Harmonized Landsat and Sentinel-2 (HLS):** Provides **30-meter** spatial resolution imagery. Through TiTiler-CMR in FIRMS, users can customize RGB spectral band combinations and indices:
  * **Color-Infrared (Near-Infrared + Visible):** Healthy vegetation reflects near-infrared light and appears vibrant red, water appears dark blue/black, and urban areas appear white/gray.
  * **Wildfire Applications:** Allows responders and researchers to penetrate smoke plumes, pinpoint active fire fronts, assess post-fire burn severity, and cross-validate coarser thermal hotspot detections (such as 375m VIIRS or 1km MODIS detections) against actual burned land scars.