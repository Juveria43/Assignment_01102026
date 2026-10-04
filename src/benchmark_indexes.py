"""
Shows the performance impact of indexes on a scaled-up copy of the data.
Builds db/benchmark.db (default 500,000 rows) and times the 5 queries with:
  (A) no secondary indexes   (B) Part 1 indexes   (C) Part 1 + Part 2 covering indexes
Usage: python src/benchmark_indexes.py [--rows 500000]
"""
import argparse
import re
import sqlite3
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC_DB = ROOT / "db" / "sales.db"
BENCH_DB = ROOT / "db" / "benchmark.db"
SCHEMA = (ROOT / "sql" / "schema_sqlite.sql").read_text(encoding="utf-8")
P2_INDEXES = (ROOT / "sql" / "part2" / "02_indexes.sql").read_text(encoding="utf-8")
P1_INDEX_NAMES = ["ix_fact_sales_date", "ix_fact_sales_customer", "ix_fact_sales_product", "ix_fact_sales_region"]
P2_INDEX_NAMES = ["ix_fact_region_product_net", "ix_fact_product_net", "ix_fact_date_net",
                  "ix_fact_region_discount", "ix_fact_net_amount"]


def queries():
    text = (ROOT / "sql" / "part2" / "03_queries.sql").read_text(encoding="utf-8")
    out = []
    for chunk in re.split(r"^-- @", text, flags=re.M)[1:]:
        title, _, body = chunk.partition("\n")
        if not title.startswith("Q5b"):
            out.append((title.split(":")[0], body.strip().rstrip(";")))
    return out


def best_time(conn, sql, repeats=3):
    best = float("inf")
    for _ in range(repeats):
        t = time.perf_counter()
        conn.execute(sql).fetchall()
        best = min(best, time.perf_counter() - t)
    return best * 1000


def build(rows):
    if BENCH_DB.exists():
        BENCH_DB.unlink()
    src = sqlite3.connect(SRC_DB)
    dst = sqlite3.connect(BENCH_DB)
    dst.executescript(SCHEMA)
    for t in ("dim_customer", "dim_product"):
        data = src.execute(f"SELECT * FROM {t}").fetchall()
        dst.executemany(f"INSERT INTO {t} VALUES ({','.join('?' * len(data[0]))})", data)
    base = src.execute("SELECT * FROM fact_sales").fetchall()
    copies = rows // len(base) + 1
    n = 0
    for k in range(copies):
        batch = [(f"{r[0]}-{k}",) + r[1:] for r in base]
        dst.executemany(f"INSERT INTO fact_sales VALUES ({','.join('?' * len(base[0]))})", batch)
        n += len(batch)
        if n >= rows:
            break
    dst.commit()
    src.close()
    return dst, n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", type=int, default=500_000)
    rows = ap.parse_args().rows
    conn, n = build(rows)
    print(f"Benchmark table built: {n:,} rows\n")

    stages = {}
    for name in P1_INDEX_NAMES:
        conn.execute(f"DROP INDEX IF EXISTS {name}")
    conn.commit(); conn.execute("ANALYZE")
    stages["A: no indexes"] = {q: best_time(conn, s) for q, s in queries()}

    conn.executescript(SCHEMA); conn.execute("ANALYZE")
    stages["B: Part 1 indexes"] = {q: best_time(conn, s) for q, s in queries()}

    conn.executescript(P2_INDEXES); conn.execute("ANALYZE")
    stages["C: + covering indexes"] = {q: best_time(conn, s) for q, s in queries()}

    names = [q for q, _ in queries()]
    print("Best of 3 runs, milliseconds\n")
    print("| Query | " + " | ".join(stages) + " | Speed-up A->C |")
    print("|---|" + "---|" * (len(stages) + 1))
    for q in names:
        vals = [stages[s][q] for s in stages]
        print(f"| {q} | " + " | ".join(f"{v:,.1f}" for v in vals) + f" | {vals[0] / vals[-1]:.1f}x |")
    conn.close()


if __name__ == "__main__":
    main()
