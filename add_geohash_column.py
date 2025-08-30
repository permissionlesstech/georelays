#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
from pathlib import Path


def geohash_encode(latitude: float, longitude: float, precision: int = 7) -> str:
    """Encode latitude/longitude to a base32 geohash string."""
    base32_alphabet = "0123456789bcdefghjkmnpqrstuvwxyz"

    lat = max(min(latitude, 90.0), -90.0)
    lon = max(min(longitude, 180.0), -180.0)
    if lat == 90.0:
        lat = 89.999999999
    if lon == 180.0:
        lon = -180.0

    lat_range: list[float] = [-90.0, 90.0]
    lon_range: list[float] = [-180.0, 180.0]
    bits: list[int] = []
    is_lon = True

    while len(bits) < precision * 5:
        if is_lon:
            midpoint = (lon_range[0] + lon_range[1]) / 2.0
            if lon >= midpoint:
                bits.append(1)
                lon_range[0] = midpoint
            else:
                bits.append(0)
                lon_range[1] = midpoint
        else:
            midpoint = (lat_range[0] + lat_range[1]) / 2.0
            if lat >= midpoint:
                bits.append(1)
                lat_range[0] = midpoint
            else:
                bits.append(0)
                lat_range[1] = midpoint
        is_lon = not is_lon

    geohash_chars: list[str] = []
    for i in range(0, len(bits), 5):
        chunk = bits[i : i + 5]
        value = (
            (chunk[0] << 4)
            | (chunk[1] << 3)
            | (chunk[2] << 2)
            | (chunk[3] << 1)
            | chunk[4]
        )
        geohash_chars.append(base32_alphabet[value])
    return "".join(geohash_chars)


def add_geohash_column(
    input_csv_path: Path, output_csv_path: Path, precision: int
) -> int:
    """Read a CSV with columns Relay URL,Latitude,Longitude and write a CSV with Geohash column appended. Returns number of rows processed."""
    with input_csv_path.open("r", encoding="utf-8", newline="") as rf:
        reader = csv.DictReader(rf)
        fieldnames: list[str] = list(reader.fieldnames or [])

        if "Latitude" not in fieldnames or "Longitude" not in fieldnames:
            raise ValueError("Input CSV must contain Latitude and Longitude columns")

        if "Geohash" not in fieldnames:
            fieldnames.append("Geohash")

        rows: list[dict[str, str]] = []
        for row in reader:
            try:
                lat = (
                    float(row["Latitude"])
                    if row.get("Latitude") not in (None, "")
                    else None
                )
                lon = (
                    float(row["Longitude"])
                    if row.get("Longitude") not in (None, "")
                    else None
                )
            except ValueError:
                lat = None
                lon = None

            row["Geohash"] = (
                geohash_encode(lat, lon, precision)
                if lat is not None and lon is not None
                else ""
            )
            rows.append(row)

    with output_csv_path.open("w", encoding="utf-8", newline="") as wf:
        writer = csv.DictWriter(wf, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    return len(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Append a Geohash column to a relays CSV."
    )
    parser.add_argument(
        "--input",
        required=True,
        help="Path to input CSV containing Relay URL,Latitude,Longitude",
    )
    parser.add_argument(
        "--output",
        help="Path to output CSV (default: <input> with _geohash suffix)",
    )
    parser.add_argument(
        "--precision",
        type=int,
        default=7,
        help="Geohash precision (default: 7)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_path = Path(args.input).expanduser().resolve()
    default_output = input_path.with_name(
        f"{input_path.stem}_geohash{input_path.suffix}"
    )
    output_path = (
        Path(args.output).expanduser().resolve() if args.output else default_output
    )
    processed = add_geohash_column(input_path, output_path, args.precision)
    print(f"Wrote {processed} rows to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
