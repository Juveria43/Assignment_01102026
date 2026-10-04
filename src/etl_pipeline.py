import argparse, hashlib, json, logging, sqlite3, sys, traceback
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "db" / "sales.db"
SCHEMA_SQL = ROOT / "sql" / "schema_sqlite.sql"
LOG_DIR = ROOT / "logs"
PIPELINE_NAME = "sales_json_to_sqlite"  # Local SQLite landing/processing pipeline
VALID_REGIONS = {"North", "South", "East", "West"}

# "03-05-2023" is interpreted as MONTH-DAY-YEAR (5 Mar 2023)
DATE_FORMATS = ["%Y/%m/%d %H:%M:%S", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%d %H:%M:%S", "%m-%d-%Y", "%Y-%m-%d"]

EXPECTED_COLUMNS = ["transaction_id", "customer_id", "product_id", "product_name",
                    "product_category", "product_price", "quantity", "discount", "date", "region"]

log = logging.getLogger("sales_etl")


def setup_logging(run_id):
    LOG_DIR.mkdir(exist_ok=True)
    fmt = logging.Formatter(f"%(asctime)s | %(levelname)-7s | {run_id} | %(message)s")
    log.setLevel(logging.DEBUG)
    log.handlers.clear()
    fh = RotatingFileHandler(LOG_DIR / "etl_pipeline.log", maxBytes=2_000_000,
                             backupCount=3, encoding="utf-8")
    fh.setFormatter(fmt)
    fh.setLevel(logging.DEBUG)
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(fmt)
    ch.setLevel(logging.INFO)
    log.addHandler(fh)
    log.addHandler(ch)


# ---------------------------- EXTRACT ----------------------------
def extract(path):
    log.info("EXTRACT  reading %s", path)
    with open(path, encoding="utf-8") as f:
        records = json.load(f)
    if not isinstance(records, list):
        raise ValueError("Expected the JSON file to contain a list of records")
    df = pd.json_normalize(records, sep="_")
    df = df.reindex(columns=EXPECTED_COLUMNS)
    df["raw_payload"] = [json.dumps(r, default=str) for r in records]
    log.info("EXTRACT  %d records read, %d columns after flattening", len(df), len(df.columns))
    return df


# ------------------------ TRANSFORM + VALIDATE ------------------------
def clean_text(s):
    s = s.astype("string").str.strip()
    return s.mask(s == "")


def parse_date(value):
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return pd.NaT
    text = str(value).strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return pd.NaT


def row_hash(row):
    parts = [row.customer_id, row.product_id, row.product_name, row.product_category,
             str(int(row.quantity)), f"{row.unit_price:.2f}", f"{row.discount:.4f}",
             row.transaction_date, row.region]
    payload = json.dumps(parts, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def transform(df):
    df = df.reset_index(drop=True).copy()
    n = len(df)

    for col in ["transaction_id", "customer_id", "product_id",
                "product_name", "product_category", "region"]:
        df[col] = clean_text(df[col])
    df["customer_id"] = df["customer_id"].str.upper()
    df["product_id"] = df["product_id"].str.upper()
    df["region"] = df["region"].str.title()

    price = pd.to_numeric(df["product_price"], errors="coerce")
    qty = pd.to_numeric(df["quantity"], errors="coerce")
    disc_present = df["discount"].notna()
    disc = pd.to_numeric(df["discount"], errors="coerce")
    df["transaction_ts"] = pd.to_datetime(df["date"].map(parse_date), errors="coerce")

    log.info("TRANSFORM %d missing discounts defaulted to 0", int((~disc_present).sum()))

    checks = {
        "missing transaction_id":          df["transaction_id"].isna(),
        "missing customer_id":             df["customer_id"].isna(),
        "missing product_id":              df["product_id"].isna(),
        "missing product_name":            df["product_name"].isna(),
        "missing product_category":        df["product_category"].isna(),
        "invalid price (null or <= 0)":    price.isna() | (price <= 0),
        "invalid quantity (null or <= 0)": qty.isna() | (qty <= 0),
        "non-integer quantity":            qty.notna() & (qty % 1 != 0),
        "invalid discount (not 0-1)":      (disc_present & disc.isna()) | (disc < 0) | (disc > 1),
        "unparseable date":                df["transaction_ts"].isna(),
        "invalid region":                  ~df["region"].isin(VALID_REGIONS),
    }
    reasons = [[] for _ in range(n)]
    for message, mask in checks.items():
        for i in np.flatnonzero(mask.fillna(False).to_numpy(dtype=bool)):
            reasons[i].append(message)

    valid_so_far = np.array([len(r) == 0 for r in reasons])
    dup = df[valid_so_far].duplicated(subset="transaction_id", keep="first")
    for i in dup[dup].index:
        reasons[i].append("duplicate transaction_id within file")

    df["reject_reason"] = ["; ".join(r) for r in reasons]
    bad = df["reject_reason"] != ""

    rejected = df.loc[bad, ["transaction_id", "reject_reason", "raw_payload"]].copy()

    good = df.loc[~bad].copy()
    good["unit_price"] = price[~bad].astype(float).round(2)
    good["quantity"] = qty[~bad].astype(int)
    good["discount"] = disc[~bad].fillna(0.0).astype(float)
    good["gross_amount"] = (good["quantity"] * good["unit_price"]).round(2)
    good["discount_amount"] = (good["gross_amount"] * good["discount"]).round(2)
    good["net_amount"] = (good["gross_amount"] - good["discount_amount"]).round(2)
    good["transaction_date"] = good["transaction_ts"].dt.strftime("%Y-%m-%d %H:%M:%S")
    good["row_hash"] = good.apply(row_hash, axis=1)
    good = good.sort_values("transaction_date").reset_index(drop=True)

    log.info("TRANSFORM %d rows valid, %d rows rejected", len(good), len(rejected))
    if len(rejected):
        summary = rejected["reject_reason"].str.split("; ").explode().value_counts().to_dict()
        for reason, cnt in summary.items():
            log.warning("REJECT   %4d x %s", cnt, reason)
        for _, r in rejected.iterrows():
            log.debug("REJECTED %s | %s | %s", r.transaction_id, r.reject_reason, r.raw_payload)
    return good, rejected


# ----------------------------- LOAD -----------------------------
def chunked(seq, size=500):
    for i in range(0, len(seq), size):
        yield seq[i:i + size]


def fetch_existing_hashes(conn, ids):
    existing = {}
    for chunk in chunked(list(ids)):
        marks = ",".join("?" * len(chunk))
        sql = f"SELECT transaction_id, row_hash FROM fact_sales WHERE transaction_id IN ({marks})"
        existing.update(conn.execute(sql, chunk).fetchall())
    return existing


def get_watermark(conn):
    row = conn.execute("SELECT last_transaction_date FROM etl_watermark WHERE pipeline_name=?",
                       (PIPELINE_NAME,)).fetchone()
    return row[0] if row else None


def load(conn, good, rejected, run_id, source_file):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    watermark = get_watermark(conn)
    log.info("LOAD     current watermark = %s", watermark)

    existing = fetch_existing_hashes(conn, good["transaction_id"].tolist())
    is_new = ~good["transaction_id"].isin(existing.keys())
    is_changed = good.apply(
        lambda r: r.transaction_id in existing and existing[r.transaction_id] != r.row_hash, axis=1)
    new_rows, changed_rows = good[is_new], good[is_changed]
    skipped = len(good) - len(new_rows) - len(changed_rows)

    if watermark:
        late = int((new_rows["transaction_date"] <= watermark).sum())
        if late:
            log.warning("LOAD     %d late-arriving NEW rows (dated <= watermark) - inserting anyway", late)
    log.info("LOAD     new=%d  changed=%d  unchanged(skipped)=%d", len(new_rows), len(changed_rows), skipped)

    to_write = pd.concat([new_rows, changed_rows])

    products = to_write.sort_values("transaction_date").drop_duplicates("product_id", keep="last")
    conn.executemany(
        """INSERT INTO dim_product (product_id, product_name, category, list_price, updated_at)
           VALUES (?,?,?,?,?)
           ON CONFLICT(product_id) DO UPDATE SET
               product_name=excluded.product_name, category=excluded.category,
               list_price=excluded.list_price, updated_at=excluded.updated_at""",
        [(r.product_id, r.product_name, r.product_category, r.unit_price, now)
         for r in products.itertuples()])

    customers = to_write.groupby("customer_id")["transaction_date"].min()
    conn.executemany(
        """INSERT INTO dim_customer (customer_id, first_seen_date) VALUES (?,?)
           ON CONFLICT(customer_id) DO UPDATE SET
               first_seen_date = MIN(first_seen_date, excluded.first_seen_date)""",
        list(customers.items()))

    conn.executemany(
        """INSERT INTO fact_sales
           (transaction_id, customer_id, product_id, quantity, unit_price, discount,
            gross_amount, discount_amount, net_amount, transaction_date, region,
            row_hash, source_file, load_run_id, loaded_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        [(r.transaction_id, r.customer_id, r.product_id, r.quantity, r.unit_price, r.discount,
          r.gross_amount, r.discount_amount, r.net_amount, r.transaction_date, r.region,
          r.row_hash, source_file, run_id, now) for r in new_rows.itertuples()])

    conn.executemany(
        """UPDATE fact_sales SET customer_id=?, product_id=?, quantity=?, unit_price=?, discount=?,
               gross_amount=?, discount_amount=?, net_amount=?, transaction_date=?, region=?,
               row_hash=?, source_file=?, load_run_id=?, updated_at=?
           WHERE transaction_id=?""",
        [(r.customer_id, r.product_id, r.quantity, r.unit_price, r.discount,
          r.gross_amount, r.discount_amount, r.net_amount, r.transaction_date, r.region,
          r.row_hash, source_file, run_id, now, r.transaction_id) for r in changed_rows.itertuples()])

    conn.executemany(
        "INSERT INTO rejected_records (load_run_id, transaction_id, reject_reason, raw_payload) VALUES (?,?,?,?)",
        [(run_id, None if pd.isna(r.transaction_id) else r.transaction_id,
          r.reject_reason, r.raw_payload) for r in rejected.itertuples()])

    new_mark = good["transaction_date"].max() if len(good) else watermark
    if watermark and new_mark:
        new_mark = max(new_mark, watermark)
    conn.execute(
        """INSERT INTO etl_watermark (pipeline_name, last_transaction_date, last_run_at)
           VALUES (?,?,?)
           ON CONFLICT(pipeline_name) DO UPDATE SET
               last_transaction_date=excluded.last_transaction_date,
               last_run_at=excluded.last_run_at""",
        (PIPELINE_NAME, new_mark, now))
    log.info("LOAD     watermark advanced to %s", new_mark)
    return {"inserted": len(new_rows), "updated": len(changed_rows), "skipped": skipped}


# --------------------------- ORCHESTRATION ---------------------------
def init_db(db_path, reset):
    db_path.parent.mkdir(exist_ok=True)
    if reset and db_path.exists():
        db_path.unlink()
        log.info("INIT     --reset: deleted existing database")
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA_SQL.read_text(encoding="utf-8"))
    return conn


def run(input_path, db_path, reset):
    now = datetime.now()
    run_id = now.strftime("%Y%m%d_%H%M%S") + f"{now.microsecond // 1000:03d}"
    setup_logging(run_id)
    log.info("=" * 70)
    log.info("START    input=%s db=%s", input_path, db_path)
    started = now.strftime("%Y-%m-%d %H:%M:%S")

    conn = init_db(db_path, reset)
    conn.execute("INSERT INTO etl_run_log (run_id, source_file, started_at, status) VALUES (?,?,?, 'RUNNING')",
                 (run_id, input_path.name, started))
    conn.commit()

    try:
        raw = extract(input_path)
        good, rejected = transform(raw)
        if len(rejected):
            csv_path = LOG_DIR / f"rejected_{run_id}.csv"
            rejected.to_csv(csv_path, index=False)
            log.info("REJECT   details written to %s", csv_path)

        stats = load(conn, good, rejected, run_id, input_path.name)
        conn.execute(
            """UPDATE etl_run_log SET finished_at=?, status='SUCCESS', rows_extracted=?, rows_rejected=?,
                   rows_inserted=?, rows_updated=?, rows_skipped=? WHERE run_id=?""",
            (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), len(raw), len(rejected),
             stats["inserted"], stats["updated"], stats["skipped"], run_id))
        conn.commit()
        log.info("DONE     extracted=%d rejected=%d inserted=%d updated=%d skipped=%d",
                 len(raw), len(rejected), stats["inserted"], stats["updated"], stats["skipped"])
    except Exception as exc:
        conn.rollback()
        log.error("FAILED   %s\n%s", exc, traceback.format_exc())
        conn.execute("UPDATE etl_run_log SET finished_at=?, status='FAILED', error_message=? WHERE run_id=?",
                     (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), str(exc)[:500], run_id))
        conn.commit()
        raise SystemExit(1)
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="Sales JSON -> relational DB ETL")
    parser.add_argument("--input", type=Path, default=ROOT / "data" / "sales_data.json")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--reset", action="store_true", help="delete the database before loading")
    args = parser.parse_args()
    run(args.input, args.db, args.reset)


if __name__ == "__main__":
    main()