PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS dim_customer (
    customer_id      TEXT PRIMARY KEY,
    first_seen_date  TEXT NOT NULL,
    created_at       TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS dim_product (
    product_id    TEXT PRIMARY KEY,
    product_name  TEXT NOT NULL,
    category      TEXT NOT NULL,
    list_price    REAL NOT NULL CHECK (list_price > 0),
    updated_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS fact_sales (
    transaction_id    TEXT PRIMARY KEY,
    customer_id       TEXT NOT NULL REFERENCES dim_customer(customer_id),
    product_id        TEXT NOT NULL REFERENCES dim_product(product_id),
    quantity          INTEGER NOT NULL CHECK (quantity > 0),
    unit_price        REAL    NOT NULL CHECK (unit_price > 0),
    discount          REAL    NOT NULL DEFAULT 0 CHECK (discount BETWEEN 0 AND 1),
    gross_amount      REAL    NOT NULL,
    discount_amount   REAL    NOT NULL,
    net_amount        REAL    NOT NULL,
    transaction_date  TEXT    NOT NULL,
    region            TEXT    NOT NULL CHECK (region IN ('North','South','East','West')),
    row_hash          TEXT    NOT NULL,
    source_file       TEXT,
    load_run_id       TEXT,
    loaded_at         TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at        TEXT
);

CREATE INDEX IF NOT EXISTS ix_fact_sales_date     ON fact_sales(transaction_date);
CREATE INDEX IF NOT EXISTS ix_fact_sales_customer ON fact_sales(customer_id);
CREATE INDEX IF NOT EXISTS ix_fact_sales_product  ON fact_sales(product_id);
CREATE INDEX IF NOT EXISTS ix_fact_sales_region   ON fact_sales(region);

CREATE TABLE IF NOT EXISTS rejected_records (
    reject_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    load_run_id     TEXT NOT NULL,
    transaction_id  TEXT,
    reject_reason   TEXT NOT NULL,
    raw_payload     TEXT NOT NULL,
    rejected_at     TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS etl_watermark (
    pipeline_name          TEXT PRIMARY KEY,
    last_transaction_date  TEXT,
    last_run_at            TEXT
);

CREATE TABLE IF NOT EXISTS etl_run_log (
    run_id           TEXT PRIMARY KEY,
    source_file      TEXT,
    started_at       TEXT NOT NULL,
    finished_at      TEXT,
    status           TEXT NOT NULL,
    rows_extracted   INTEGER,
    rows_rejected    INTEGER,
    rows_inserted    INTEGER,
    rows_updated     INTEGER,
    rows_skipped     INTEGER,
    error_message    TEXT
);