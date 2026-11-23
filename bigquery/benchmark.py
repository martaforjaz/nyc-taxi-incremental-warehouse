"""Compare two BigQuery table layouts using the same accepted trip records."""
import argparse
from datetime import date, timedelta
import json
from pathlib import Path
import re
from tempfile import TemporaryDirectory
from uuid import uuid4

import duckdb
from google.cloud import bigquery

ROOT = Path(__file__).resolve().parents[1]
SELECT = "SELECT COUNT(*) AS trips, AVG(distance_miles) AS mean_miles FROM trips"
FILTER = " WHERE pickup_at >= @day AND pickup_at < @tomorrow"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--dataset", required=True, help="Existing dataset in the selected location")
    parser.add_argument("--location", default="US")
    parser.add_argument("--day", type=date.fromisoformat, default=date(2025, 1, 15))
    parser.add_argument("--max-bytes-billed", type=int, default=1_000_000_000)
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_]+", args.dataset):
        parser.error("Invalid dataset identifier")
    client = bigquery.Client(project=args.project, location=args.location)
    namespace = f"{args.project}.{args.dataset}"
    prefix = "tlc_demo_" + uuid4().hex[:10]
    tomorrow = args.day + timedelta(days=1)
    tables = []
    evidence = {}
    with TemporaryDirectory() as scratch, duckdb.connect(str(ROOT / "output/warehouse.duckdb"), read_only=True) as db:
        local_count, local_mean = db.execute(SELECT + " WHERE pickup_at >= ? AND pickup_at < ?",
                                           [args.day, tomorrow]).fetchone()
        if not local_count:
            raise ValueError("The selected day has no accepted local trips.")
        path = Path(scratch) / "trips.parquet"
        db.execute("""
            COPY (SELECT pickup_at AT TIME ZONE 'UTC' AS pickup_at, distance_miles FROM trips)
            TO ? (FORMAT PARQUET)
        """, [str(path)])
        try:
            for layout in ("unpartitioned", "partitioned"):
                table = f"{namespace}.{prefix}_{layout}"
                load = bigquery.LoadJobConfig(source_format=bigquery.SourceFormat.PARQUET,
                                               write_disposition=bigquery.WriteDisposition.WRITE_EMPTY)
                if layout == "partitioned":
                    load.time_partitioning = bigquery.TimePartitioning(field="pickup_at")
                # Explicit schema keeps the time column identical in both layouts.
                resource = bigquery.Table(table, schema=[
                    bigquery.SchemaField("pickup_at", "TIMESTAMP"),
                    bigquery.SchemaField("distance_miles", "FLOAT"),
                ])
                resource.time_partitioning = load.time_partitioning
                client.create_table(resource)
                tables.append(table)
                with path.open("rb") as stream:
                    client.load_table_from_file(stream, table, job_config=load).result()
                query = SELECT.replace("FROM trips", f"FROM `{table}`") + FILTER
                params = [bigquery.ScalarQueryParameter("day", "TIMESTAMP", args.day.isoformat() + " 00:00:00+00"),
                          bigquery.ScalarQueryParameter("tomorrow", "TIMESTAMP", tomorrow.isoformat() + " 00:00:00+00")]
                estimate = client.query(query, job_config=bigquery.QueryJobConfig(
                    dry_run=True, use_query_cache=False, query_parameters=params,
                )).total_bytes_processed
                job = client.query(query, job_config=bigquery.QueryJobConfig(
                    use_query_cache=False, maximum_bytes_billed=args.max_bytes_billed, query_parameters=params,
                ))
                row = next(iter(job.result()))
                if row.trips != local_count or abs(row.mean_miles - local_mean) > 1e-8:
                    raise ValueError(f"{layout} disagrees with DuckDB")
                evidence[layout] = {"job_id": job.job_id, "dry_run_bytes": estimate,
                                    "processed_bytes": job.total_bytes_processed, "billed_bytes": job.total_bytes_billed,
                                    "trips": row.trips, "mean_miles": row.mean_miles}
        finally:
            for table in tables:
                client.delete_table(table, not_found_ok=True)
    print(json.dumps({"day": args.day.isoformat(), "duckdb_trips": local_count,
                      "layouts": evidence}, indent=2))


if __name__ == "__main__":
    main()
