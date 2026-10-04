"""Runs the Part 2 scripts against db/sales.db and writes docs/part2_sample_output.md"""
import re
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "db" / "sales.db"
SQL = ROOT / "sql" / "part2"
OUT = ROOT / "docs" / "part2_sample_output.md"


def load_queries():
    text = (SQL / "03_queries.sql").read_text(encoding="utf-8")
    queries = []
    for chunk in re.split(r"^-- @", text, flags=re.M)[1:]:
        title, _, body = chunk.partition("\n")
        queries.append((title.strip(), body.strip().rstrip(";")))
    return queries


def to_markdown(cur):
    cols = [d[0] for d in cur.description]
    rows = cur.fetchall()
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    lines += ["| " + " | ".join(str(v) for v in r) + " |" for r in rows]
    return "\n".join(lines)


def main():
    conn = sqlite3.connect(DB)
    conn.executescript((SQL / "01_views.sql").read_text(encoding="utf-8"))
    conn.executescript((SQL / "02_indexes.sql").read_text(encoding="utf-8"))
    conn.commit()

    md = ["# Part 2 - Query results (sample output)\n",
          f"Source: `{DB.name}` ({conn.execute('SELECT COUNT(*) FROM fact_sales').fetchone()[0]} transactions)\n"]
    for title, sql in load_queries():
        cur = conn.execute(sql)
        table = to_markdown(cur)
        plan = conn.execute("EXPLAIN QUERY PLAN " + sql).fetchall()
        plan_txt = "\n".join(r[3] for r in plan)
        print(f"\n=== {title} ===\n{table}")
        md += [f"## {title}\n", "```sql", sql + ";", "```\n", table, "",
               "Query plan:", "```", plan_txt, "```\n"]
    OUT.write_text("\n".join(md), encoding="utf-8")
    print(f"\nWrote {OUT}")
    conn.close()


if __name__ == "__main__":
    main()
