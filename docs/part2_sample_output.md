# Part 2 - Query results (sample output)

Source: `sales.db` (852 transactions)

## Q1: Total sales by region and category

```sql
-- Aggregate the big fact table first (region, product), then join the small product table.
SELECT s.region,
       p.category,
       SUM(s.transactions)            AS transactions,
       SUM(s.units)                   AS units_sold,
       ROUND(SUM(s.sales), 2)         AS total_sales
FROM (SELECT region, product_id, COUNT(*) AS transactions,
             SUM(quantity) AS units, SUM(net_amount) AS sales
      FROM fact_sales
      GROUP BY region, product_id) s
JOIN dim_product p ON p.product_id = s.product_id
GROUP BY s.region, p.category
ORDER BY s.region, total_sales DESC;
```

| region | category | transactions | units_sold | total_sales |
|---|---|---|---|---|
| East | Electronics | 90 | 390 | 186289.96 |
| East | Furniture | 55 | 243 | 34622.41 |
| East | Accessories | 74 | 354 | 15827.43 |
| North | Electronics | 92 | 438 | 171871.98 |
| North | Furniture | 63 | 260 | 36413.01 |
| North | Accessories | 42 | 204 | 9568.21 |
| South | Electronics | 84 | 365 | 165048.41 |
| South | Furniture | 71 | 311 | 45286.47 |
| South | Accessories | 65 | 313 | 14832.31 |
| West | Electronics | 87 | 412 | 159954.23 |
| West | Furniture | 61 | 318 | 46482.51 |
| West | Accessories | 68 | 315 | 13617.41 |

Query plan:
```
CO-ROUTINE s
SCAN fact_sales USING COVERING INDEX ix_fact_region_product_net
SCAN s
SEARCH p USING INDEX sqlite_autoindex_dim_product_1 (product_id=?)
USE TEMP B-TREE FOR GROUP BY
USE TEMP B-TREE FOR ORDER BY
```

## Q2: Top 5 products by total revenue

```sql
SELECT p.product_id,
       p.product_name,
       p.category,
       s.units_sold,
       ROUND(s.revenue, 2)            AS total_revenue
FROM (SELECT product_id, SUM(quantity) AS units_sold, SUM(net_amount) AS revenue
      FROM fact_sales
      GROUP BY product_id) s
JOIN dim_product p ON p.product_id = s.product_id
ORDER BY total_revenue DESC
LIMIT 5;
```

| product_id | product_name | category | units_sold | total_revenue |
|---|---|---|---|---|
| P01 | Laptop | Electronics | 381 | 346646.46 |
| P09 | Tablet | Electronics | 451 | 185122.7 |
| P03 | Monitor | Electronics | 386 | 106412.39 |
| P05 | Desk | Furniture | 423 | 73643.85 |
| P06 | Office Chair | Furniture | 364 | 51613.6 |

Query plan:
```
CO-ROUTINE s
SCAN fact_sales USING COVERING INDEX ix_fact_product_net
SCAN s
SEARCH p USING INDEX sqlite_autoindex_dim_product_1 (product_id=?)
USE TEMP B-TREE FOR ORDER BY
```

## Q3: Monthly sales trend (with month-over-month change)

```sql
WITH monthly AS (
    SELECT substr(transaction_date, 1, 7) AS sales_month,
           COUNT(*)                       AS transactions,
           ROUND(SUM(net_amount), 2)      AS total_sales
    FROM fact_sales
    GROUP BY substr(transaction_date, 1, 7)
)
SELECT sales_month,
       transactions,
       total_sales,
       ROUND(100.0 * (total_sales - LAG(total_sales) OVER (ORDER BY sales_month))
             / LAG(total_sales) OVER (ORDER BY sales_month), 1) AS mom_change_pct
FROM monthly
ORDER BY sales_month;
```

| sales_month | transactions | total_sales | mom_change_pct |
|---|---|---|---|
| 2023-01 | 68 | 78316.81 | None |
| 2023-02 | 47 | 39277.73 | -49.8 |
| 2023-03 | 61 | 84271.86 | 114.6 |
| 2023-04 | 56 | 55092.17 | -34.6 |
| 2023-05 | 60 | 75529.71 | 37.1 |
| 2023-06 | 52 | 31795.79 | -57.9 |
| 2023-07 | 62 | 53252.3 | 67.5 |
| 2023-08 | 61 | 55156.47 | 3.6 |
| 2023-09 | 62 | 68544.99 | 24.3 |
| 2023-10 | 62 | 63327.78 | -7.6 |
| 2023-11 | 56 | 47702.71 | -24.7 |
| 2023-12 | 63 | 62752.67 | 31.5 |
| 2024-01 | 79 | 106680.9 | 70.0 |
| 2024-02 | 63 | 78112.45 | -26.8 |

Query plan:
```
CO-ROUTINE (subquery-3)
CO-ROUTINE monthly
SCAN fact_sales USING COVERING INDEX ix_fact_date_net
USE TEMP B-TREE FOR GROUP BY
SCAN monthly
USE TEMP B-TREE FOR ORDER BY
SCAN (subquery-3)
```

## Q4: Average discount percentage per region

```sql
SELECT region,
       ROUND(AVG(discount) * 100, 2)                          AS avg_discount_pct,
       ROUND(100.0 * SUM(discount_amount) / SUM(gross_amount), 2) AS value_weighted_discount_pct
FROM fact_sales
GROUP BY region
ORDER BY avg_discount_pct DESC;
```

| region | avg_discount_pct | value_weighted_discount_pct |
|---|---|---|
| North | 9.14 | 9.44 |
| East | 8.7 | 9.96 |
| West | 7.85 | 7.39 |
| South | 7.55 | 7.11 |

Query plan:
```
SCAN fact_sales USING COVERING INDEX ix_fact_region_discount
USE TEMP B-TREE FOR ORDER BY
```

## Q5: Number of transactions with total_value > 1000

```sql
SELECT COUNT(*) AS transactions_over_1000
FROM fact_sales
WHERE net_amount > 1000;
```

| transactions_over_1000 |
|---|
| 242 |

Query plan:
```
SEARCH fact_sales USING COVERING INDEX ix_fact_net_amount (net_amount>?)
```

## Q5b: Same count broken down by region

```sql
SELECT region, COUNT(*) AS transactions_over_1000
FROM fact_sales
WHERE net_amount > 1000
GROUP BY region
ORDER BY transactions_over_1000 DESC;
```

| region | transactions_over_1000 |
|---|---|
| East | 64 |
| South | 60 |
| North | 59 |
| West | 59 |

Query plan:
```
SCAN fact_sales USING COVERING INDEX ix_fact_region_product_net
USE TEMP B-TREE FOR ORDER BY
```
