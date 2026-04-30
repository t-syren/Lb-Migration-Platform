-- =========================================
-- HIVE FULL FEATURE TEST SCRIPT
-- =========================================

-- ---------- SESSION CONFIG ----------
SET hive.execution.engine=tez;
SET hive.exec.dynamic.partition=true;
SET hive.exec.dynamic.partition.mode=nonstrict;
SET hive.auto.convert.join=true;

-- ---------- VARIABLES ----------
SET hivevar:run_dt=2025-01-01;

-- ---------- DATABASE ----------
CREATE DATABASE IF NOT EXISTS retail_db
COMMENT 'Retail data warehouse';

USE retail_db;

-- ---------- EXTERNAL TABLE ----------
CREATE EXTERNAL TABLE IF NOT EXISTS sales_ext (
    order_id STRING,
    customer_id STRING,
    amount DOUBLE,
    order_date STRING
)
PARTITIONED BY (dt STRING)
ROW FORMAT DELIMITED
FIELDS TERMINATED BY ','
STORED AS TEXTFILE
LOCATION 'hdfs://warehouse/sales_ext/'
TBLPROPERTIES ('skip.header.line.count'='1');

MSCK REPAIR TABLE sales_ext;

-- ---------- COMPLEX TYPES ----------
CREATE TABLE complex_data (
    id INT,
    attributes MAP<STRING, STRING>,
    metrics STRUCT<clicks:INT, impressions:INT>
)
STORED AS ORC;

-- ---------- BUCKETING ----------
CREATE TABLE bucketed_table (
    user_id STRING,
    event_time TIMESTAMP
)
CLUSTERED BY (user_id) INTO 8 BUCKETS
SORTED BY (event_time)
STORED AS ORC;

-- ---------- ACID TABLE ----------
CREATE TABLE acid_table (
    id INT,
    name STRING
)
CLUSTERED BY (id) INTO 4 BUCKETS
STORED AS ORC
TBLPROPERTIES ('transactional'='true');

-- ---------- UDF ----------
ADD JAR hdfs://libs/myudf.jar;

CREATE TEMPORARY FUNCTION my_udf AS 'com.example.MyUDF';

-- ---------- CTE + WINDOW ----------
WITH ranked_orders AS (
    SELECT 
        customer_id,
        amount,
        ROW_NUMBER() OVER (PARTITION BY customer_id ORDER BY amount DESC) AS rn
    FROM sales_ext
)
SELECT * FROM ranked_orders WHERE rn = 1;

-- ---------- LATERAL VIEW ----------
SELECT 
    customer_id,
    item
FROM orders
LATERAL VIEW EXPLODE(SPLIT(items, ',')) t AS item;

-- ---------- JOIN + HINT ----------
SELECT /*+ MAPJOIN(c) */
    o.order_id,
    c.customer_name
FROM orders o
JOIN customers c
ON o.customer_id = c.customer_id;

-- ---------- MULTI INSERT ----------
FROM sales_ext
INSERT OVERWRITE TABLE high_value_sales
SELECT * WHERE amount > 1000
INSERT OVERWRITE TABLE low_value_sales
SELECT * WHERE amount <= 1000;

-- ---------- DYNAMIC PARTITION ----------
INSERT OVERWRITE TABLE sales_part PARTITION (dt)
SELECT 
    order_id,
    customer_id,
    amount,
    order_date,
    order_date AS dt
FROM sales_ext;

-- ---------- VARIABLE USAGE ----------
INSERT OVERWRITE TABLE target_${hivevar:run_dt}
SELECT * FROM sales_ext;

-- ---------- ANALYZE ----------
ANALYZE TABLE sales_ext COMPUTE STATISTICS FOR COLUMNS;

-- ---------- CLEANUP ----------
-- Comment-only statement to test filtering
