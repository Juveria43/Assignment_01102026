-- SQL Server queries against the shared SalesCustomerDB warehouse.
-- The required indexes are created by sql/04_warehouse_sqlserver.sql.
USE SalesCustomerDB;
GO

-- Q1: Total sales by region and category
SELECT f.Region, p.Category, COUNT(*) AS transactions, SUM(f.Quantity) AS units_sold,
       ROUND(SUM(f.NetAmount), 2) AS total_sales
FROM dbo.FactSales f
JOIN dbo.DimProduct p ON p.ProductID = f.ProductID
GROUP BY f.Region, p.Category
ORDER BY f.Region, total_sales DESC;

-- Q2: Top 5 products by total revenue
SELECT TOP (5) p.ProductID, p.ProductName, p.Category, SUM(f.Quantity) AS units_sold,
       ROUND(SUM(f.NetAmount), 2) AS total_revenue
FROM dbo.FactSales f
JOIN dbo.DimProduct p ON p.ProductID = f.ProductID
GROUP BY p.ProductID, p.ProductName, p.Category
ORDER BY total_revenue DESC;

-- Q3: Monthly sales trend
WITH monthly AS (
    SELECT CONVERT(CHAR(7), TransactionDate, 120) AS sales_month,
           COUNT(*) AS transactions, ROUND(SUM(NetAmount), 2) AS total_sales
    FROM dbo.FactSales
    GROUP BY CONVERT(CHAR(7), TransactionDate, 120)
)
SELECT sales_month, transactions, total_sales,
       ROUND(100.0 * (total_sales - LAG(total_sales) OVER (ORDER BY sales_month))
             / NULLIF(LAG(total_sales) OVER (ORDER BY sales_month), 0), 1) AS mom_change_pct
FROM monthly
ORDER BY sales_month;

-- Q4: Average discount percentage per region
SELECT Region,
       ROUND(AVG(CAST(Discount AS FLOAT)) * 100, 2) AS avg_discount_pct,
       ROUND(100.0 * SUM(DiscountAmount) / NULLIF(SUM(GrossAmount), 0), 2) AS value_weighted_discount_pct
FROM dbo.FactSales
GROUP BY Region
ORDER BY avg_discount_pct DESC;

-- Q5: Number of transactions with net total over $1,000
SELECT COUNT(*) AS transactions_over_1000
FROM dbo.FactSales
WHERE NetAmount > 1000;
