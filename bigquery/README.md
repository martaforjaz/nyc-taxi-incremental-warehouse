# BigQuery partition pruning benchmark

The runner compares a date-filtered query on identical unpartitioned and daily-partitioned tables. It checks the trip count and mean distance against DuckDB and prints job IDs, dry-run estimates, bytes processed and bytes billed.

After building the local warehouse, install the BigQuery client and use Application Default Credentials with access to an existing BigQuery dataset. The benchmark creates two uniquely named tables in that dataset and deletes those tables on completion. Query billing is capped per query. Storage and loading use the selected project.

```bash
python -m pip install -r bigquery/requirements.txt
python bigquery/benchmark.py --project YOUR_PROJECT --dataset YOUR_DATASET \
  --location US --day 2025-01-15 --max-bytes-billed 1000000000
```

The upload encodes source wall-clock timestamps as UTC solely to preserve the published date buckets. Both table layouts use the same encoded values and the same half-open time filter. This benchmark does not reconstruct trip time zones.

**Execution status:** the DuckDB run is verified. BigQuery requires an authenticated Google Cloud project and has not been run for this repository. There are no cloud byte counts or savings claims yet.

[Google Cloud documentation on partition pruning](https://docs.cloud.google.com/bigquery/docs/querying-partitioned-tables)
