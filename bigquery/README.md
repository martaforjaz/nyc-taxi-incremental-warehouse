# BigQuery partition pruning benchmark

The runner compares a date-filtered query on identical unpartitioned and daily-partitioned tables. It checks the trip count and mean distance against DuckDB and prints job IDs, dry-run estimates, bytes processed and bytes billed.

After building the local warehouse, install the BigQuery client and use Application Default Credentials with access to an existing BigQuery dataset. The benchmark creates two uniquely named tables in that dataset and deletes those tables on completion. Query billing is capped per query. Storage and loading use the selected project.

```bash
python -m pip install -r bigquery/requirements.txt
python bigquery/benchmark.py --project YOUR_PROJECT --dataset YOUR_DATASET \
  --location US --day 2025-01-15 --max-bytes-billed 1000000000
```

The upload encodes source wall-clock timestamps as UTC solely to preserve the published date buckets. Both table layouts use the same encoded values and the same half-open time filter. This benchmark does not reconstruct trip time zones.

## Measured result

On 23 November 2026, both layouts returned 121,901 trips and a mean distance of 6.4761 miles, matching DuckDB for 15 January 2025. Caching was disabled.

- **Unpartitioned:** 109,698,736 bytes processed and 110,100,480 bytes billed.
- **Daily partitions:** 1,950,416 bytes processed and 10,485,760 bytes billed.
- **Reduction in bytes processed:** 98.22%. Processed bytes and billed bytes are separate job metrics.

The [run evidence](../evidence/bigquery-benchmark.json) records both query job IDs and the dry-run estimates.

For BigQuery Sandbox, add `--sandbox`. The original data spans 59 calendar days. Sandbox mode shifts both copies by the same whole number of days so the full window fits inside the 60-day partition retention period. In the reference run, the offset was 633 days and 15 January 2025 mapped to 10 October 2026. DuckDB checks the unshifted source day. The same trips fall into the same daily groups in both BigQuery layouts.

[Google Cloud documentation on partition pruning](https://docs.cloud.google.com/bigquery/docs/querying-partitioned-tables)
