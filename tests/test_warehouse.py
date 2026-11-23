from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import duckdb

from warehouse import initialize, ingest


class WarehouseTest(unittest.TestCase):
    def test_two_months_replay_and_quality(self):
        with TemporaryDirectory() as temp, duckdb.connect() as db:
            folder = Path(temp)
            zones = folder / "zones.csv"
            zones.write_text("LocationID,Borough,Zone\n1,Manhattan,Example\n", encoding="utf-8")
            initialize(db, zones)
            for month in ["2025-01", "2025-02"]:
                db.execute("""
                    CREATE OR REPLACE TEMP TABLE fixture AS
                    SELECT TIMESTAMP '""" + month + """-02 01:00:00' AS tpep_pickup_datetime,
                           tpep_pickup_datetime + INTERVAL 1 HOUR AS tpep_dropoff_datetime,
                           1 AS PULocationID, 1 AS DOLocationID, distance AS trip_distance
                    FROM (VALUES (1.0), (0.0)) AS d(distance)
                """)
                path = folder / f"{month}.parquet"
                db.execute("COPY fixture TO ? (FORMAT PARQUET)", [str(path)])
                self.assertTrue(ingest(db, month, path))
                self.assertFalse(ingest(db, month, path))
            self.assertEqual(db.execute("SELECT COUNT(*) FROM trips").fetchone(), (2,))
            self.assertEqual(
                db.execute("SELECT decision, sum(trip_count) FROM decisions GROUP BY 1 ORDER BY 1").fetchall(),
                [("accepted", 2), ("invalid_distance", 2)],
            )
            with path.open("ab") as stream:
                stream.write(b"changed")
            with self.assertRaisesRegex(ValueError, "source bytes changed"):
                ingest(db, month, path)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM trips").fetchone(), (2,))
