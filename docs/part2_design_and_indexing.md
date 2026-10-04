# Part 2 - Database Design, Queries and Indexing

## 1. Schema (created by `sql/schema_sqlite.sql`)

```
dim_customer (PK customer_id)          dim_product (PK product_id)
        ^                                      ^
        | FK customer_id                       | FK product_id
        +-------------- fact_sales (PK transaction_id) --------------+
                        quantity, unit_price, discount, gross/discount/net amounts,
                        transaction_date, region
```

| Required table | Table used | Primary key | Foreign keys |
|---|---|---|---|
| Transactions | `fact_sales` | `transaction_id` | `customer_id` -> `dim_customer`, `product_id` -> `dim_product` |
| Products | `dim_product` | `product_id` | - |
| Customers | `dim_customer` | `customer_id` | - |

Normalisation: product attributes (name, category, price) live once in `dim_product` and customer data once in
`dim_customer`, so nothing is repeated on every transaction row (3NF). `fact_sales` stores
`gross_amount`, `discount_amount` and `net_amount` even though they are derivable. This is a deliberate
denormalisation: they are calculated once at load time, which avoids recomputing them in every query and lets
them be indexed. `total_value` in the brief is `net_amount` (quantity x unit price, minus discount).
CHECK constraints (quantity > 0, discount 0-1, valid region) protect integrity at database level.

## 2. Indexes (`sql/part2/02_indexes.sql`)

| Index | Columns | Helps | Why |
|---|---|---|---|
| ix_fact_region_product_net | region, product_id, quantity, net_amount | Q1 | Covering: the fact table is aggregated straight from the index in group order (no temp sort, no table lookups) |
| ix_fact_product_net | product_id, quantity, net_amount | Q2 | Covering index for grouping by product |
| ix_fact_date_net | transaction_date, net_amount | Q3 | Reads dates in order from a narrow index; also supports date-range filters |
| ix_fact_region_discount | region, discount, gross_amount, discount_amount | Q4 | Covering index for per-region averages |
| ix_fact_net_amount | net_amount | Q5 | Range seek: jumps to net_amount > 1000 instead of scanning every row |

Part 1 already created single-column indexes on date, customer, product and region (used for foreign-key
lookups and filters).

## 3. Performance impact

Measured with `python src/benchmark_indexes.py` on 500,259 rows (best of 3, milliseconds, my machine; replace
with your own output):

| Query | A: no indexes | B: Part 1 indexes | C: + covering indexes | Speed-up A -> C |
|---|---|---|---|---|
| Q1 | 671.1 | 813.8 | 85.1 | 7.9x |
| Q2 | 364.8 | 501.1 | 64.2 | 5.7x |
| Q3 | 303.5 | 325.6 | 237.9 | 1.3x |
| Q4 | 362.5 | 383.3 | 91.9 | 3.9x |
| Q5 | 80.1 | 73.0 | 3.0 | 27.1x |

What the numbers show:
* **Q5** gains most because it is selective: the index lets the database seek straight to the matching range.
* **Q1, Q2, Q4** aggregate every row, so they must read all data. Covering indexes make that cheaper (narrow
  index instead of the wide table, rows already in group order, no temporary B-tree).
* **Q3** improves least: it groups by `substr(transaction_date, 1, 7)`, an expression, so the index cannot be
  used for grouping, only as a narrow scan. A stored `sales_month` column would fix this.
* **Single-column indexes alone (B) did not help** these aggregate queries and were slightly slower: the engine
  still visits the table for `net_amount`. Index design must match the query.
* Q1 and Q2 aggregate the fact table first and join the small product table afterwards. The first version
  joined 500k rows to the product table and got *slower* with indexes.
* On the original ~850 rows all queries take under 1 ms either way; indexes only matter at scale.

Trade-offs: each extra index adds storage and slows INSERT/UPDATE (the ETL maintains every index on each load).
`ix_fact_sales_product` and `ix_fact_sales_region` from Part 1 are now prefixes of the covering indexes and
could be dropped on a write-heavy system. Check plans with `EXPLAIN QUERY PLAN` (SQLite) or the actual execution
plan (SQL Server).
