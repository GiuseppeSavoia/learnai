"""Scarica il database puzzle di Lichess (CC0) e ne importa un sottoinsieme bilanciato in data/puzzles.db.

Uso:  .venv/bin/python scripts/import_puzzles.py [--per-bucket 6000] [--per-theme 300] [--keep-download]

Selezione: Popularity >= 80 e NbPlays >= 200; campionamento casuale uniforme (reservoir sampling)
per fasce di rating da 100 punti tra 400 e 2800, più una riserva per ogni tema così che anche i
temi rari siano rappresentati.
"""

from __future__ import annotations

import argparse
import csv
import io
import random
import sqlite3
import sys
import time
from pathlib import Path

import httpx
import zstandard

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import config, puzzle_store  # noqa: E402

URL = "https://database.lichess.org/lichess_db_puzzle.csv.zst"
MIN_POPULARITY = 80
MIN_PLAYS = 200
RATING_MIN = 400
RATING_MAX = 2800
BUCKET_SIZE = 100

Row = tuple[str, str, str, int, int, int, int, str, str]


def download(dest: Path) -> None:
    tmp = dest.with_suffix(dest.suffix + ".part")
    print(f"Scarico {URL} ...", flush=True)
    with httpx.stream("GET", URL, follow_redirects=True, timeout=60) as resp:
        resp.raise_for_status()
        total = int(resp.headers.get("content-length", 0))
        done = 0
        with tmp.open("wb") as fh:
            for chunk in resp.iter_bytes(1 << 20):
                fh.write(chunk)
                done += len(chunk)
                if total:
                    print(f"\r  {done / 1e6:.0f}/{total / 1e6:.0f} MB", end="", flush=True)
    print()
    tmp.rename(dest)


class Reservoir:
    def __init__(self, capacity: int, rng: random.Random) -> None:
        self.capacity = capacity
        self.items: list[Row] = []
        self.seen = 0
        self.rng = rng

    def offer(self, row: Row) -> None:
        self.seen += 1
        if len(self.items) < self.capacity:
            self.items.append(row)
        else:
            j = self.rng.randrange(self.seen)
            if j < self.capacity:
                self.items[j] = row


def select(source: Path, per_bucket: int, per_theme: int, seed: int) -> list[Row]:
    rng = random.Random(seed)
    buckets: dict[int, Reservoir] = {}
    by_theme: dict[str, Reservoir] = {}
    total = 0
    with source.open("rb") as fh:
        reader = zstandard.ZstdDecompressor().stream_reader(fh)
        text = io.TextIOWrapper(reader, encoding="utf-8", newline="")
        rows = csv.reader(text)
        header = next(rows)
        idx = {name: i for i, name in enumerate(header)}
        for rec in rows:
            total += 1
            if total % 500_000 == 0:
                print(f"  lette {total:,} righe", flush=True)
            rating = int(rec[idx["Rating"]])
            popularity = int(rec[idx["Popularity"]])
            plays = int(rec[idx["NbPlays"]])
            if popularity < MIN_POPULARITY or plays < MIN_PLAYS or not RATING_MIN <= rating < RATING_MAX:
                continue
            row: Row = (
                rec[idx["PuzzleId"]],
                rec[idx["FEN"]],
                rec[idx["Moves"]],
                rating,
                int(rec[idx["RatingDeviation"]]),
                popularity,
                plays,
                rec[idx["Themes"]],
                rec[idx["OpeningTags"]],
            )
            bucket = rating // BUCKET_SIZE
            buckets.setdefault(bucket, Reservoir(per_bucket, rng)).offer(row)
            for theme in row[7].split():
                by_theme.setdefault(theme, Reservoir(per_theme, rng)).offer(row)
    print(f"Righe totali lette: {total:,}")
    chosen: dict[str, Row] = {}
    for res in list(buckets.values()) + list(by_theme.values()):
        for row in res.items:
            chosen[row[0]] = row
    return list(chosen.values())


def write_db(rows: list[Row], dest: Path) -> None:
    tmp = dest.with_suffix(".tmp.db")
    tmp.unlink(missing_ok=True)
    conn = sqlite3.connect(tmp)
    try:
        conn.executescript(puzzle_store.SCHEMA)
        conn.executemany("INSERT INTO puzzles VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)
        conn.executemany(
            "INSERT INTO puzzle_themes(theme, rating, puzzle_id) VALUES (?, ?, ?)",
            ((theme, r[3], r[0]) for r in rows for theme in r[7].split()),
        )
        conn.executescript(puzzle_store.INDEXES)
        conn.commit()
        conn.execute("VACUUM")
    finally:
        conn.close()
    tmp.replace(dest)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--per-bucket", type=int, default=6000, help="puzzle per fascia di 100 punti")
    parser.add_argument("--per-theme", type=int, default=300, help="minimo garantito per tema (se disponibile)")
    parser.add_argument("--seed", type=int, default=2000)
    parser.add_argument("--keep-download", action="store_true", help="non cancellare il file .zst")
    args = parser.parse_args()

    config.ensure_data_dir()
    source = config.DATA_DIR / "lichess_db_puzzle.csv.zst"
    start = time.monotonic()
    if not source.is_file():
        download(source)
    else:
        print(f"Uso il file già scaricato: {source}")
    rows = select(source, args.per_bucket, args.per_theme, args.seed)
    print(f"Puzzle selezionati: {len(rows):,}")
    write_db(rows, config.PUZZLE_DB_PATH)
    print(f"Scritto {config.PUZZLE_DB_PATH} in {time.monotonic() - start:.0f}s")
    if not args.keep_download:
        source.unlink()
        print("File .zst eliminato.")


if __name__ == "__main__":
    main()
