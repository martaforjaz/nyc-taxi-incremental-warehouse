"""Generate publication-ready SVGs from the committed aggregate evidence."""
import csv
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent
NAVY, PLUM, MUTED = "#102b59", "#915883", "#506078"


def read(name):
    with (ROOT / "evidence" / f"{name}.csv").open(encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))


def text(x, y, value, size=20, color=NAVY, weight=400, anchor="start"):
    return (f'<text x="{x}" y="{y}" fill="{color}" font-size="{size}" '
            f'font-weight="{weight}" text-anchor="{anchor}">{escape(str(value))}</text>')


def box(x, y, width, height, color, radius=0):
    return f'<rect x="{x}" y="{y}" width="{width}" height="{height}" rx="{radius}" fill="{color}"/>'


def save(name, title, height, items):
    folder = ROOT / "figures"
    folder.mkdir(exist_ok=True)
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="1120" height="{height}" '
           f'viewBox="0 0 1120 {height}" font-family="Arial,sans-serif" role="img">'
           f'<title>{escape(title)}</title>' + box(0, 0, 1120, height, "#fff")
           + "".join(items) + "</svg>\n")
    with (folder / f"{name}.svg").open("w", encoding="utf-8", newline="\n") as file:
        file.write(svg)


def overview(batch):
    total = sum(int(row["source_rows"]) for row in batch)
    accepted = sum(int(row["accepted"]) for row in batch)
    title = "Two monthly files become a replay-safe trip warehouse"
    items = [text(560, 52, title, 34, weight=700, anchor="middle")]
    stages = [
        ("I. Source acquisition", "NYC TLC yellow taxis", f"{len(batch)} monthly Parquet files", "Official zone lookup"),
        ("II. Quality checks", f"{total:,} source rows", "Dates, duration, distance", f"{total-accepted:,} rows rejected"),
        ("III. Incremental load", "DuckDB daily-ready facts", f"{accepted:,} accepted trips", "Month + SHA-256 ledger"),
        ("IV. Evidence", "Borough aggregates", "Replay checks and CSVs", "BigQuery benchmark script"),
    ]
    for i, (heading, first, second, third) in enumerate(stages):
        x = 30 + 269 * i
        items += [box(x, 89, 253, 50, NAVY, 24),
                  text(x+126, 121, heading, 19, "#fff", 700, "middle"),
                  text(x+126, 181, first, 18, NAVY, 700, "middle"),
                  text(x+126, 225, second, 17, MUTED, 400, "middle"),
                  text(x+126, 269, third, 17, PLUM, 700, "middle")]
        if i < 3:
            items.append(text(x+261, 205, "→", 17, NAVY, 700, "middle"))
    items += [box(30, 305, 1060, 3, NAVY)]
    save("overview", title, 331, items)


def bars(name, title, subtitle, labels, values, months, footer, formatted):
    items = [text(34, 50, title, 30, weight=700), text(34, 80, subtitle, 18, MUTED)]
    for i, month in enumerate(months):
        x = 820 + i * 123
        items += [box(x, 100, 15, 15, (NAVY, PLUM)[i]), text(x+22, 113, month, 15, MUTED)]
    maximum = max(max(pair) for pair in values)
    for i, (label, pair) in enumerate(zip(labels, values)):
        y = 146 + i * 58
        items.append(text(34, y+19, label, 18, weight=700))
        for j, value in enumerate(pair):
            color = (NAVY, PLUM)[j]
            width = 640 * value / maximum
            items += [box(284, y+21*j, width, 15, color, 2),
                      text(295+width, y+12+21*j, formatted(value), 15, color, 700)]
    bottom = 152 + 58 * len(labels)
    items += [box(34, bottom, 1052, 2, "#dee3ec"), text(34, bottom+28, footer, 16, MUTED)]
    save(name, title, bottom+49, items)


def main():
    batch = read("batches")
    months = [row["month"] for row in batch]
    if len(months) != 2:
        raise ValueError("The reference figures compare two monthly batches.")
    overview(batch)
    quality = {(r["month"], r["decision"]): int(r["trip_count"]) for r in read("quality")}
    reasons = [("invalid_distance", "Invalid distance"), ("invalid_duration", "Invalid duration"),
               ("outside_source_month", "Outside source month")]
    bars("quality", "Invalid distance was the leading rejection reason",
         "Rejected records per 10,000 source rows", [label for _, label in reasons],
         [[10000 * quality.get((r["month"], key), 0)/int(r["source_rows"]) for r in batch] for key, _ in reasons],
         months, "Each row is counted once, under the first failed check.", lambda v: f"{v:,.2f}")
    boroughs = {(r["month"], r["borough"]): int(r["trips"]) for r in read("boroughs")}
    labels = ["Manhattan", "Queens", "Brooklyn", "Bronx", "Staten Island"]
    bars("boroughs", "Manhattan accounted for most accepted pickups",
         "Accepted trips by pickup borough", labels,
         [[boroughs.get((month, label), 0) for month in months] for label in labels],
         months, "Unknown, N/A and EWR classifications are included in the full CSV.", lambda v: f"{v:,}")


if __name__ == "__main__":
    main()
