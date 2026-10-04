-- Part 2 schema = the 3 core tables created by sql/schema_sqlite.sql (Part 1):
--   Transactions -> fact_sales,  Products -> dim_product,  Customers -> dim_customer
-- This script adds a convenience view that joins them. total_value = net amount after discount.
DROP VIEW IF EXISTS vw_sales_detail;
CREATE VIEW vw_sales_detail AS
SELECT  f.transaction_id,
        f.transaction_date,
        f.region,
        c.customer_id,
        p.product_id,
        p.product_name,
        p.category,
        f.quantity,
        f.unit_price,
        f.discount,
        f.gross_amount,
        f.net_amount AS total_value
FROM fact_sales f
JOIN dim_product  p ON p.product_id  = f.product_id
JOIN dim_customer c ON c.customer_id = f.customer_id;
