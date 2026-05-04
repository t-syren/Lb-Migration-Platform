-- =========================================================
-- 1. DATABASE & SESSION CONFIG (OPTIMIZATION BASICS)
-- =========================================================

CREATE DATABASE IF NOT EXISTS retail_db;
USE retail_db;

-- Execution Engine
SET hive.execution.engine=tez;

-- Enable Cost Based Optimizer
SET hive.cbo.enable=true;

-- Enable Vectorization
SET hive.vectorized.execution.enabled=true;

-- Enable Parallel Execution
SET hive.exec.parallel=true;

-- Dynamic Partitioning
SET hive.exec.dynamic.partition=true;
SET hive.exec.dynamic.partition.mode=nonstrict;

-- Map Join Optimization
SET hive.auto.convert.join=true;

-- Skew Join Handling
SET hive.optimize.skewjoin=true;


-- =========================================================
-- 2. RAW TABLE (TEXT FORMAT - BAD PRACTICE INTENTIONALLY)
-- =========================================================

CREATE TABLE IF NOT EXISTS raw_sales (
    order_id STRING,
    customer_id STRING,
    product_id STRING,
    amount DOUBLE,
    quantity INT,
    order_date STRING,
    region STRING
)
ROW FORMAT DELIMITED
FIELDS TERMINATED BY ','
STORED AS TEXTFILE;


-- =========================================================
-- 3. OPTIMIZED TABLE (ORC + PARTITION + BUCKET)
-- =========================================================

CREATE TABLE IF NOT EXISTS sales_orc (
    order_id STRING,
    customer_id STRING,
    product_id STRING,
    amount DOUBLE,
    quantity INT
)
PARTITIONED BY (order_date STRING)
CLUSTERED BY (customer_id) INTO 4 BUCKETS
STORED AS ORC
TBLPROPERTIES ("orc.compress"="SNAPPY");


-- Load data (example)
INSERT OVERWRITE TABLE sales_orc PARTITION(order_date)
SELECT 
    order_id,
    customer_id,
    product_id,
    amount,
    quantity,
    order_date
FROM raw_sales;


-- =========================================================
-- 4. DIMENSION TABLES
-- =========================================================

CREATE TABLE customers (
    customer_id STRING,
    name STRING,
    city STRING
) STORED AS ORC;

CREATE TABLE products (
    product_id STRING,
    product_name STRING,
    category STRING
) STORED AS ORC;


-- =========================================================
-- 5. CTE + JOINS + TRANSFORMATIONS
-- =========================================================

WITH base_data AS (
    SELECT 
        s.order_id,
        s.customer_id,
        s.product_id,
        s.amount,
        s.quantity,
        s.order_date,
        c.name,
        c.city,
        p.product_name,
        p.category
    FROM sales_orc s
    LEFT JOIN customers c 
        ON s.customer_id = c.customer_id
    INNER JOIN products p 
        ON s.product_id = p.product_id
),

-- Aggregation CTE
agg_data AS (
    SELECT 
        category,
        city,
        SUM(amount) AS total_sales,
        COUNT(*) AS total_orders,
        AVG(amount) AS avg_sales
    FROM base_data
    GROUP BY category, city
)

SELECT * FROM agg_data;


-- =========================================================
-- 6. ALL IMPORTANT HIVE FUNCTIONS
-- =========================================================

SELECT 
    order_id,

    -- STRING FUNCTIONS
    UPPER(customer_id) AS upper_id,
    LOWER(customer_id) AS lower_id,
    SUBSTR(customer_id,1,3) AS sub_id,
    LENGTH(customer_id) AS len_id,
    CONCAT(customer_id, '_', product_id) AS concat_col,

    -- NUMERIC FUNCTIONS
    ROUND(amount,2) AS rounded_amt,
    CEIL(amount) AS ceil_amt,
    FLOOR(amount) AS floor_amt,

    -- DATE FUNCTIONS
    FROM_UNIXTIME(UNIX_TIMESTAMP(order_date,'yyyy-MM-dd')) AS formatted_date,
    DATEDIFF(current_date, order_date) AS days_diff,

    -- CONDITIONAL
    CASE 
        WHEN amount > 1000 THEN 'HIGH'
        WHEN amount > 500 THEN 'MEDIUM'
        ELSE 'LOW'
    END AS sales_category,

    -- NULL HANDLING
    NVL(customer_id,'UNKNOWN') AS cust_id,

    -- TYPE CAST
    CAST(amount AS INT) AS amount_int

FROM sales_orc;


-- =========================================================
-- 7. WINDOW FUNCTIONS
-- =========================================================

SELECT 
    customer_id,
    order_date,
    amount,

    ROW_NUMBER() OVER (PARTITION BY customer_id ORDER BY amount DESC) AS rn,
    RANK() OVER (PARTITION BY customer_id ORDER BY amount DESC) AS rnk,
    DENSE_RANK() OVER (PARTITION BY customer_id ORDER BY amount DESC) AS dense_rnk,

    SUM(amount) OVER (PARTITION BY customer_id) AS total_spent,

    LAG(amount,1) OVER (PARTITION BY customer_id ORDER BY order_date) AS prev_amt,
    LEAD(amount,1) OVER (PARTITION BY customer_id ORDER BY order_date) AS next_amt

FROM sales_orc;


-- =========================================================
-- 8. DIFFERENT JOIN TYPES
-- =========================================================

-- INNER JOIN
SELECT * FROM sales_orc s
JOIN customers c ON s.customer_id = c.customer_id;

-- LEFT JOIN
SELECT * FROM sales_orc s
LEFT JOIN customers c ON s.customer_id = c.customer_id;

-- RIGHT JOIN
SELECT * FROM sales_orc s
RIGHT JOIN customers c ON s.customer_id = c.customer_id;

-- FULL OUTER JOIN
SELECT * FROM sales_orc s
FULL OUTER JOIN customers c ON s.customer_id = c.customer_id;

-- LEFT SEMI JOIN (EXISTS)
SELECT * FROM sales_orc s
WHERE customer_id IN (SELECT customer_id FROM customers);

-- LEFT ANTI JOIN (NOT EXISTS)
SELECT * FROM sales_orc s
WHERE customer_id NOT IN (SELECT customer_id FROM customers);


-- =========================================================
-- 9. PERFORMANCE OPTIMIZATION QUERIES
-- =========================================================

-- Partition Pruning
SELECT * FROM sales_orc WHERE order_date='2025-01-01';

-- Bucketing Optimization (requires same bucket count)
SET hive.optimize.bucketmapjoin=true;

-- Analyze Table (Statistics for CBO)
ANALYZE TABLE sales_orc COMPUTE STATISTICS;

-- Column Stats
ANALYZE TABLE sales_orc COMPUTE STATISTICS FOR COLUMNS;

-- Explain Plan
EXPLAIN SELECT * FROM sales_orc WHERE amount > 500;


-- =========================================================
-- 10. ADVANCED (SKEW + MAPJOIN HINT)
-- =========================================================

SELECT /*+ MAPJOIN(c) */ 
    s.*, c.name
FROM sales_orc s
JOIN customers c 
ON s.customer_id = c.customer_id;

-- =========================================================
-- 11.UDF + COMPLEX FUNC + DYNAMIC SQL + VARAIBLES
-- =========================================================



ADD JAR hdfs:///udf/custom_udf.jar;

CREATE TEMPORARY FUNCTION my_udf AS 'com.test.MyUDF';

SELECT 
    id,
    my_udf(map_col['key'], array_col[0]) AS result
FROM complex_table;



SET hivevar:run_dt=2025-01-01;

INSERT OVERWRITE TABLE target_${hivevar:run_dt}
SELECT *
FROM source
WHERE dt = '${hivevar:run_dt}';

-- =========================================================
-- 11. FILE FORMAT CONVERSION (TEXT -> ORC/PARQUET)
-- =========================================================

CREATE TABLE sales_parquet STORED AS PARQUET AS
SELECT * FROM sales_orc;


-- =========================================================
-- 12. CLEANUP
-- =========================================================

-- DROP TABLE raw_sales;
-- DROP TABLE sales_orc;