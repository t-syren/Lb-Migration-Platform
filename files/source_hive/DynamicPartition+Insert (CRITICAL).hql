SET hive.exec.dynamic.partition=true;
SET hive.exec.dynamic.partition.mode=nonstrict;

INSERT OVERWRITE TABLE sales_part PARTITION (dt)
SELECT order_id, customer_id, amount, order_date, order_date as dt
FROM sales_ext;