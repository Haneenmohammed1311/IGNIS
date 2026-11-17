"""Audit a folder of teammate release files and print a short text report you can paste.

Usage:  uv run python tools/audit_release.py <folder> [<folder> ...]
It only READS files. It prints, and also saves, harmonization_audit.txt.
"""
import sys, re, glob, os
import pyarrow.parquet as pq, pandas as pd

KEYS = re.compile(r"harmon|equiv|calib|uncert|ratio|scale|scaling|factor|prob|_lo$|_hi$|lower|upper|ci_|interval|adjust|normal|baseline|median|percentile|anomal", re.I)
out = []
def p(*a):
    s = " ".join(str(x) for x in a); print(s); out.append(s)

for root in sys.argv[1:]:
    files = sorted(glob.glob(os.path.join(root, "**", "*.parquet"), recursive=True))
    p(f"\n##### {root}: {len(files)} parquet files")
    for f in files:
        pf = pq.ParquetFile(f); names = pf.schema_arrow.names
        hits = [n for n in names if KEYS.search(n)]
        p(f"- {os.path.relpath(f, root)} | rows={pf.metadata.num_rows:,} | cols={len(names)} | suspicious-name columns={hits}")
        p("    columns:", names)
        for c in ("year", "country_code", "country", "source_dataset"):
            if c in names:
                vals = pf.read(columns=[c]).to_pandas()[c].dropna().unique()
                p(f"    {c}: {sorted(map(str, vals))[:12]}")
    # test: does the monthly total equal the sum of sensors?
    tot = [f for f in files if f.endswith("monthly_activity.parquet")]
    bys = [f for f in files if f.endswith("monthly_activity_by_sensor.parquet")]
    for t, b in zip(tot, bys):
        a = pd.read_parquet(t); s = pd.read_parquet(b)
        m = s.groupby("month_utc").type0_detections.sum().rename("sum_of_sensors")
        j = a.set_index("month_utc")[["type0_detections"]].join(m)
        p(f"  total == raw sum of sensors in every month? {bool((j.type0_detections == j.sum_of_sensors).all())}  ({os.path.relpath(t, root)})")
open("harmonization_audit.txt", "w").write("\n".join(out))
print("\nsaved harmonization_audit.txt")