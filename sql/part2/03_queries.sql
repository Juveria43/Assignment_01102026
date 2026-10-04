-- =====================================================================
-- Part 2 analytical queries (SQLite). "total_value" = net_amount
-- (quantity x unit_price, minus discount).
-- =====================================================================

-- @Q1: Total sales by region and category
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

-- @Q2: Top 5 products by total revenue
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

-- @Q3: Monthly sales trend (with month-over-month change)
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

-- @Q4: Average discount percentage per region
SELECT region,
       ROUND(AVG(discount) * 100, 2)                          AS avg_discount_pct,
       ROUND(100.0 * SUM(discount_amount) / SUM(gross_amount), 2) AS value_weighted_discount_pct
FROM fact_sales
GROUP BY region
ORDER BY avg_discount_pct DESC;

-- @Q5: Number of transactions with total_value > 1000
SELECT COUNT(*) AS transactions_over_1000
FROM fact_sales
WHERE net_amount > 1000;

-- @Q5b: Same count broken down by region
SELECT region, COUNT(*) AS transactions_over_1000
FROM fact_sales
WHERE net_amount > 1000
GROUP BY region
ORDER BY transactions_over_1000 DESC;
