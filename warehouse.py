"""Ingest monthly NYC TLC exports and write reproducible aggregate evidence."""
import argparse
import csv
from datetime import date
from hashlib import file_digest
from pathlib import Path
from urllib.request import urlopen
import shutil

import duckdb

ROOT = Path(__file__).resolve().parent
BASE = "https://d37ci6vzurychx.cloudfront.net"
DEFAULT_MONTHS = ("2025-01", "2025-02")
CLASSIFY = (ROOT / "sql/classify.sql").read_text(encoding="utf-8")


def digest(path):
    with path.open("rb") as stream:
        return file_digest(stream, "sha256").hexdigest()


def fetch(folder, name, url):
    path = folder / name
    if not path.exists():
        temporary = path.with_suffix(".partial")
        with urlopen(url, timeout=90) as response, temporary.open("wb") as target:
            shutil.copyfileobj(response, target)
        temporary.replace(path)
    return path


def initialize(db, zones):
    db.execute("""
        CREATE TABLE IF NOT EXISTS batches (
            month VARCHAR PRIMARY KEY, sha256 VARCHAR, source_rows BIGINT, accepted BIGINT
        );
        CREATE TABLE IF NOT EXISTS decisions (
            month VARCHAR, decision VARCHAR, trip_count BIGINT, PRIMARY KEY (month, decision)
        );
        CREATE TABLE IF NOT EXISTS trips (
            month VARCHAR, pickup_at TIMESTAMP, dropoff_at TIMESTAMP,
            pickup_zone_id INTEGER, dropoff_zone_id INTEGER, distance_miles DOUBLE
        );
        CREATE TABLE IF NOT EXISTS inputs (name VARCHAR PRIMARY KEY, sha256 VARCHAR);
    """)
    checksum = digest(zones)
    prior = db.execute("SELECT sha256 FROM inputs WHERE name='zones'").fetchone()
    if prior:
        if prior[0] != checksum:
            raise ValueError("Zone lookup changed. Use a fresh database.")
        return
    db.begin()
    try:
        db.execute("""
            CREATE TABLE zones (zone_id INTEGER PRIMARY KEY, borough VARCHAR, zone VARCHAR);
            INSERT INTO zones SELECT LocationID, Borough, Zone FROM read_csv_auto(?)
        """, [str(zones)])
        db.execute("INSERT INTO inputs VALUES ('zones', ?)", [checksum])
        db.commit()
    except Exception:
        db.rollback()
        raise


def ingest(db, month, path):
    start = date.fromisoformat(month + "-01")
    finish = date(start.year + (start.month == 12), start.month % 12 + 1, 1)
    checksum = digest(path)
    previous = db.execute("SELECT sha256 FROM batches WHERE month = ?", [month]).fetchone()
    if previous:
        if previous[0] != checksum:
            raise ValueError(f"{month}: source bytes changed. Use a fresh database.")
        return False
    db.begin()
    try:
        db.execute("CREATE OR REPLACE TEMP TABLE staged AS " + CLASSIFY,
                   {"start": start, "finish": finish, "path": str(path)})
        total, accepted = db.execute(
            "SELECT count(*), count(*) FILTER (WHERE decision='accepted') FROM staged"
        ).fetchone()
        db.execute("INSERT INTO decisions SELECT ?, decision, count(*) FROM staged GROUP BY decision",
                   [month])
        db.execute("""
            INSERT INTO trips
            SELECT ?, pickup_at, dropoff_at, pickup_zone_id, dropoff_zone_id, distance_miles
            FROM staged WHERE decision = 'accepted'
        """, [month])
        db.execute("INSERT INTO batches VALUES (?, ?, ?, ?)", [month, checksum, total, accepted])
        db.execute("DROP TABLE staged")
        db.commit()
    except Exception:
        db.rollback()
        raise
    return True


def export(db, out):
    out.mkdir(parents=True, exist_ok=True)
    queries = {
        "batches": "SELECT * FROM batches ORDER BY month",
        "quality": "SELECT * FROM decisions ORDER BY month, decision",
        "boroughs": """
            SELECT month, z.borough, count(*) AS trips
            FROM trips JOIN zones z ON pickup_zone_id = z.zone_id
            GROUP BY month, z.borough ORDER BY month, trips DESC, z.borough
        """,
        "inputs": "SELECT * FROM inputs ORDER BY name",
    }
    for name, query in queries.items():
        result = db.execute(query)
        with (out / f"{name}.csv").open("w", newline="", encoding="utf-8") as stream:
            writer = csv.writer(stream, lineterminator="\n")
            writer.writerow(column[0] for column in result.description)
            writer.writerows(result.fetchall())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("months", nargs="*", default=DEFAULT_MONTHS)
    args = parser.parse_args()
    for month in args.months:
        if date.fromisoformat(month + "-01").strftime("%Y-%m") != month:
            parser.error("Months must use YYYY-MM")
    inputs, outputs = ROOT / "input", ROOT / "output"
    inputs.mkdir(exist_ok=True)
    outputs.mkdir(exist_ok=True)
    zones = fetch(inputs, "taxi_zone_lookup.csv", BASE + "/misc/taxi_zone_lookup.csv")
    with duckdb.connect(str(outputs / "warehouse.duckdb")) as db:
        initialize(db, zones)
        for month in args.months:
            name = f"yellow_tripdata_{month}.parquet"
            path = fetch(inputs, name, f"{BASE}/trip-data/{name}")
            status = "loaded" if ingest(db, month, path) else "unchanged"
            print(f"{month}: {status}")
        export(db, outputs)


if __name__ == "__main__":
    main()
