"""Build bounded chat evidence from release overview and daily summaries."""

COUNTRY_NAMES = {"AU": "Australia", "BR": "Brazil", "ID": "Indonesia", "ZA": "South Africa"}


def gather_analytical_facts(route: dict, current_filters=None) -> dict:
    """Query summaries sequentially; never expose detailed rows to the model."""
    from fastapi import HTTPException

    from . import main

    countries = route.get("countries") or ([current_filters.country] if current_filters else [])
    years = route.get("years") or ([current_filters.year] if current_filters else [])
    countries = [code for code in dict.fromkeys(countries) if code in COUNTRY_NAMES][:4]
    years = sorted({year for year in years if year in range(2020, 2026)})[:6]
    sensor = None if route.get("compare_sensors") else (
        route.get("sensor") or (current_filters.sensor if current_filters else None)
    )
    facts: dict[str, dict] = {}
    scope_notes = []

    if current_filters and (current_filters.region or current_filters.polygon):
        scope_notes.append("The active regional/custom map filter was not applied; provided metrics are country-wide.")
    if current_filters and (current_filters.start or current_filters.end):
        scope_notes.append("The active date range was not applied; provided metrics are full-year summaries.")

    if not route.get("needs_analytics", True):
        return {"facts": facts, "scope_notes": scope_notes}

    for country in countries:
        if len(years) > 1:
            try:
                comparison = main.compare(main.Compare(country=country, year=years[0], years=years, sensor=sensor))
                for item in comparison:
                    year = item["year"]
                    if year not in years:
                        continue
                    facts[f"{country}.{year}.comparison"] = {
                        "status": "available" if item["available"] else "unavailable",
                        "country": COUNTRY_NAMES[country], "country_code": country,
                        "year": year, "sensor": sensor or "all sensors",
                        "total_detections": item["total"],
                        "note": "Total is derived from the cached daily summary.",
                    }
            except HTTPException as error:
                if error.status_code == 503:
                    raise
                scope_notes.append(f"Year comparison for {country} was unavailable.")

        for year in years:
            release = main.releases.get((country, year))
            fact_id = f"{country}.{year}.overview" + (f".{sensor}" if sensor else "")
            if not release or release.get("status") != "ready":
                facts[fact_id] = {
                    "status": "unavailable", "country": COUNTRY_NAMES[country],
                    "country_code": country, "year": year, "sensor": sensor or "all sensors",
                    "message": "No validated local release is currently available.",
                }
                continue
            try:
                filters = main.Filters(country=country, year=year)
                result = main.analytical("overview", filters)
                metrics = result["metrics"]
                accounting = ("detections", "linked", "unresolved", "outside_scope")
                if any(metrics.get(key) is None for key in accounting):
                    raise ValueError("Release tracking totals are incomplete.")
                total, linked, unresolved, outside = (int(metrics[key]) for key in accounting)
                if min(total, linked, unresolved, outside) < 0 or linked + unresolved + outside != total:
                    raise ValueError("Release tracking totals do not reconcile.")
                if sensor:
                    sensor_count = metrics.get({
                        "MODIS": "modis",
                        "VIIRS SNPP": "snpp",
                        "VIIRS JPSS-1": "jpss1",
                    }[sensor], 0) or 0
                    if sensor_count:
                        sensor_filters = main.Filters(country=country, year=year, sensor=sensor)
                        metrics = main.analytical("overview", sensor_filters)["metrics"]
                    else:
                        metrics = {"detections": 0, "mean_frp": None, "frp_n": 0}
                facts[fact_id] = {
                    "status": "available", "country": COUNTRY_NAMES[country],
                    "country_code": country, "year": year, "sensor": sensor or "all sensors",
                    "metrics": metrics,
                    "note": "Metrics come from the release's pre-aggregated overview summary.",
                }
            except HTTPException as error:
                if error.status_code == 503:
                    raise
                facts[fact_id] = {
                    "status": "unavailable", "country": COUNTRY_NAMES[country],
                    "country_code": country, "year": year, "sensor": sensor or "all sensors",
                    "message": "No validated local release is currently available.",
                }

    return {"facts": facts, "scope_notes": scope_notes}
