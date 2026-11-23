-- First applicable reason wins so accepted plus rejected reconciles to source rows.
SELECT
    tpep_pickup_datetime AS pickup_at,
    tpep_dropoff_datetime AS dropoff_at,
    PULocationID::INTEGER AS pickup_zone_id,
    DOLocationID::INTEGER AS dropoff_zone_id,
    trip_distance AS distance_miles,
    CASE
        WHEN pickup_at IS NULL OR dropoff_at IS NULL THEN 'missing_timestamp'
        WHEN pickup_at < $start::DATE OR pickup_at >= $finish::DATE THEN 'outside_source_month'
        WHEN dropoff_at <= pickup_at OR dropoff_at > pickup_at + INTERVAL 24 HOUR THEN 'invalid_duration'
        WHEN distance_miles IS NULL OR NOT isfinite(distance_miles) OR distance_miles <= 0 THEN 'invalid_distance'
        WHEN pu.zone_id IS NULL OR dz.zone_id IS NULL THEN 'unmapped_zone'
        ELSE 'accepted'
    END AS decision
FROM read_parquet($path) AS t
LEFT JOIN zones AS pu ON t.PULocationID = pu.zone_id
LEFT JOIN zones AS dz ON t.DOLocationID = dz.zone_id
