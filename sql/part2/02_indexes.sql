-- Part 2 indexes (in addition to the 4 single-column indexes from Part 1:
--   ix_fact_sales_date, ix_fact_sales_customer, ix_fact_sales_product, ix_fact_sales_region).
-- The new ones are COVERING indexes: they contain every column a query needs,
-- so SQLite can answer from the index alone without visiting the table rows.

-- Q1  sales by region + category (join on product, sum net_amount)
CREATE INDEX IF NOT EXISTS ix_fact_region_product_net ON fact_sales(region, product_id, quantity, net_amount);

-- Q2  top products by revenue (group by product)
CREATE INDEX IF NOT EXISTS ix_fact_product_net ON fact_sales(product_id, quantity, net_amount);

-- Q3  monthly trend (scan in date order, read net_amount from the index)
CREATE INDEX IF NOT EXISTS ix_fact_date_net ON fact_sales(transaction_date, net_amount);

-- Q4  average discount per region
CREATE INDEX IF NOT EXISTS ix_fact_region_discount ON fact_sales(region, discount, gross_amount, discount_amount);

-- Q5  transactions with total_value > 1000 (range seek on net_amount)
CREATE INDEX IF NOT EXISTS ix_fact_net_amount ON fact_sales(net_amount);
