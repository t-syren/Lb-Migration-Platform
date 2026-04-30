FROM sales_ext
INSERT OVERWRITE TABLE high_value_sales
SELECT * WHERE amount > 1000
INSERT OVERWRITE TABLE low_value_sales
SELECT * WHERE amount <= 1000;