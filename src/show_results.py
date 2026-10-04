import sqlite3
from pathlib import Path

db = Path(__file__).resolve().parents[1] / "db" / "sales.db"
c = sqlite3.connect(db)

def show(title, sql):
    print(f"\n=== {title} ===")
    cur = c.execute(sql)
    print(" | ".join(d[0] for d in cur.description))
    for row in cur.fetchall():
        print(" | ".join(str(v) for v in row))

show("Row counts", """
    SELECT 'fact_sales', COUNT(*) FROM fact_sales
    UNION ALL SELECT 'dim_product', COUNT(*) FROM dim_product
    UNION ALL SELECT 'dim_customer', COUNT(*) FROM dim_customer
    UNION ALL SELECT 'rejected_records', COUNT(*) FROM rejected_records""")
show("Run history", """
    SELECT run_id, source_file, status, rows_extracted, rows_rejected,
           rows_inserted, rows_updated, rows_skipped
    FROM etl_run_log ORDER BY started_at""")
show("Watermark", "SELECT * FROM etl_watermark")
show("Rejection reasons", """
    SELECT reject_reason, COUNT(*) AS n FROM rejected_records
    GROUP BY reject_reason ORDER BY n DESC LIMIT 10""")
show("Revenue by region", """
    SELECT region, ROUND(SUM(net_amount), 2) AS net_revenue
    FROM fact_sales GROUP BY region ORDER BY net_revenue DESC""")
c.close()