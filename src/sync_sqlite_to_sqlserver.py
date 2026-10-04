"""Idempotently publish the local SQLite sales store to the SQL Server warehouse.

The source is read as a consistent full snapshot. For this assignment-sized data
set a daily full upsert is simpler to retry and avoids a fragile cross-database
watermark. SQL Server retains the source row hash and ignores unchanged facts.
"""
import argparse
import os
import sqlite3
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SQLITE = ROOT / "db" / "sales.db"


def read_source(sqlite_path):
    with sqlite3.connect(sqlite_path) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("BEGIN")  # Hold one SQLite read snapshot for all three tables.
        products = conn.execute(
            "SELECT product_id, product_name, category, list_price FROM dim_product ORDER BY product_id"
        ).fetchall()
        customers = conn.execute(
            "SELECT customer_id FROM dim_customer ORDER BY customer_id"
        ).fetchall()
        sales = conn.execute(
            """SELECT transaction_id, customer_id, product_id, quantity, unit_price, discount,
                      gross_amount, discount_amount, net_amount, transaction_date, region,
                      row_hash, source_file, load_run_id
               FROM fact_sales ORDER BY transaction_id"""
        ).fetchall()
    return products, customers, sales


def publish(sqlite_path, connection_string):
    try:
        import pyodbc
    except ImportError as exc:
        raise RuntimeError("pyodbc is required. Install requirements.txt and the Microsoft ODBC Driver for SQL Server.") from exc

    products, customers, sales = read_source(sqlite_path)
    limits = ((products, "product_id", 20), (products, "product_name", 200),
              (products, "category", 100), (customers, "customer_id", 20),
              (sales, "transaction_id", 50), (sales, "customer_id", 20),
              (sales, "product_id", 20), (sales, "region", 50))
    for rows, column, maximum in limits:
        if any(len(str(row[column])) > maximum for row in rows):
            raise ValueError(f"Source field {column} exceeds SQL Server limit {maximum}")

    run_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    conn = pyodbc.connect(connection_string, autocommit=False)
    inserted = updated = 0
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT dbo.WarehouseLoadRun (RunID,StartedAt,Status,ProductsRead,CustomersRead,SalesRead) VALUES (?,?,?, ?,?,?)",
            run_id, now, "RUNNING", len(products), len(customers), len(sales))
        conn.commit()
        try:
            cur.execute("""DECLARE @lock_result INT;
                EXEC @lock_result = sys.sp_getapplock @Resource=?, @LockMode='Exclusive',
                     @LockOwner='Transaction', @LockTimeout=0;
                IF @lock_result < 0 THROW 51000, 'Another SQLite sales publish is already running', 1;""",
                "SalesCustomerDB:SQLiteSalesSync")
            for p in products:
                cur.execute("""UPDATE dbo.DimProduct SET ProductName=?,Category=?,ListPrice=?,UpdatedAt=SYSUTCDATETIME()
                               WHERE ProductID=?""", p["product_name"], p["category"], p["list_price"], p["product_id"])
                if cur.rowcount == 0:
                    cur.execute("""INSERT dbo.DimProduct(ProductID,ProductName,Category,ListPrice)
                                   VALUES (?,?,?,?)""", p["product_id"], p["product_name"], p["category"], p["list_price"])

            # The SSIS feed supplies descriptive attributes. Sales-only IDs are seeded
            # with NULL attributes and later enriched by SSIS when customer detail arrives.
            for c in customers:
                cur.execute("""INSERT dbo.DimCustomer(CustomerID)
                               SELECT ? WHERE NOT EXISTS
                               (SELECT 1 FROM dbo.DimCustomer WITH (UPDLOCK,HOLDLOCK) WHERE CustomerID=?)""",
                            c["customer_id"], c["customer_id"])

            for s in sales:
                vals = (s["customer_id"], s["product_id"], s["quantity"], s["unit_price"], s["discount"],
                        s["gross_amount"], s["discount_amount"], s["net_amount"], s["transaction_date"],
                        s["region"], s["row_hash"], s["source_file"], s["load_run_id"], run_id,
                        s["transaction_id"], s["row_hash"])
                cur.execute("""UPDATE dbo.FactSales
                    SET CustomerID=?,ProductID=?,Quantity=?,UnitPrice=?,Discount=?,GrossAmount=?,DiscountAmount=?,
                        NetAmount=?,TransactionDate=?,Region=?,RowHash=?,SourceFile=?,SourceLoadRunID=?,
                        WarehouseRunID=?,UpdatedAt=SYSUTCDATETIME()
                    WHERE TransactionID=? AND RowHash<>?""", *vals)
                if cur.rowcount:
                    updated += 1
                    continue
                cur.execute("""INSERT dbo.FactSales
                    (CustomerID,ProductID,Quantity,UnitPrice,Discount,GrossAmount,DiscountAmount,NetAmount,
                     TransactionDate,Region,RowHash,SourceFile,SourceLoadRunID,WarehouseRunID,TransactionID)
                    SELECT ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?
                    WHERE NOT EXISTS (SELECT 1 FROM dbo.FactSales WITH (UPDLOCK,HOLDLOCK) WHERE TransactionID=?)""",
                    s["customer_id"], s["product_id"], s["quantity"], s["unit_price"], s["discount"],
                    s["gross_amount"], s["discount_amount"], s["net_amount"], s["transaction_date"],
                    s["region"], s["row_hash"], s["source_file"], s["load_run_id"], run_id,
                    s["transaction_id"], s["transaction_id"])
                inserted += cur.rowcount

            cur.execute("""UPDATE dbo.WarehouseLoadRun SET FinishedAt=SYSUTCDATETIME(),Status='SUCCEEDED',
                SalesInserted=?,SalesUpdated=? WHERE RunID=?""", inserted, updated, run_id)
            conn.commit()
        except Exception as exc:
            conn.rollback()
            cur.execute("""UPDATE dbo.WarehouseLoadRun SET FinishedAt=SYSUTCDATETIME(),Status='FAILED',
                ErrorMessage=? WHERE RunID=?""", str(exc)[:2000], run_id)
            conn.commit()
            raise
    finally:
        conn.close()
    return {"run_id": run_id, "products": len(products), "customers": len(customers),
            "sales": len(sales), "inserted": inserted, "updated": updated}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sqlite", type=Path, default=DEFAULT_SQLITE, help="SQLite sales database path")
    parser.add_argument("--connection-string", default=os.getenv("SQLSERVER_CONNECTION_STRING"),
                        help="SQL Server ODBC connection string; defaults to SQLSERVER_CONNECTION_STRING")
    args = parser.parse_args()
    if not args.sqlite.exists():
        parser.error(f"SQLite database does not exist: {args.sqlite}")
    if not args.connection_string:
        parser.error("Set SQLSERVER_CONNECTION_STRING or pass --connection-string")
    try:
        print(publish(args.sqlite, args.connection_string))
    except Exception as exc:
        print(f"Warehouse sync failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
