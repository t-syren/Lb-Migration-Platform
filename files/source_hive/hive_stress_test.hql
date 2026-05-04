-- ============================================
-- 🔥 MASTER HIVE STRESS TEST SCRIPT
-- Covers: DDL, DML, UDF, VARIABLES, COMPLEX SQL
-- ============================================

-- ============================================
-- 0. VARIABLES
-- ============================================
SET run_dt=2025-01-01;
SET hivevar:region=us;
SET hive.exec.dynamic.partition=true;

SELECT * FROM sales WHERE dt='${run_dt}';

-- ============================================
-- 1. DATABASE + USE
-- ============================================
CREATE DATABASE IF NOT EXISTS retail_db COMMENT 'Retail DB';
USE retail_db;

-- ============================================
-- 2. BASIC TABLE
-- ============================================
CREATE TABLE normal_table (
    id INT,
    name STRING
);

-- ============================================
-- 3. PARTITIONED TABLE
-- ============================================
CREATE TABLE partitioned_table (
    id INT,
    dt STRING
)
PARTITIONED BY (dt);

-- ============================================
-- 4. BUCKETED TABLE (unsupported)
-- ============================================
CREATE TABLE bucketed_table (
    id INT,
    name STRING
)
CLUSTERED BY (id) INTO 4 BUCKETS;

-- ============================================
-- 5. SORTED TABLE (unsupported)
-- ============================================
CREATE TABLE sorted_table (
    id INT,
    ts TIMESTAMP
)
SORTED BY (ts);

-- ============================================
-- 6. EXTERNAL TABLE (HDFS)
-- ============================================
CREATE EXTERNAL TABLE ext_hdfs (
    id INT,
    name STRING
)
ROW FORMAT DELIMITED
FIELDS TERMINATED BY ','
STORED AS TEXTFILE
LOCATION 'hdfs://warehouse/ext_hdfs/';

-- ============================================
-- 7. EXTERNAL TABLE (DBFS)
-- ============================================
CREATE EXTERNAL TABLE ext_dbfs (
    id INT
)
STORED AS PARQUET
LOCATION '/mnt/data/ext_dbfs/';

-- ============================================
-- 8. CTAS
-- ============================================
CREATE TABLE ctas_table AS
SELECT * FROM normal_table;

-- ============================================
-- 9. CTAS WITH SUBQUERY
-- ============================================
CREATE TABLE ctas_nested AS
SELECT * FROM (
    SELECT id FROM normal_table
) t;

-- ============================================
-- 10. LOCATION TABLE
-- ============================================
CREATE TABLE delta_with_location (
    id INT
)
LOCATION '/mnt/delta/table_path';

-- ============================================
-- 11. COMPLEX CREATE
-- ============================================
CREATE TABLE complex_table (
    id INT,
    name STRING,
    created_ts TIMESTAMP
)
COMMENT 'complex'
PARTITIONED BY (created_ts)
TBLPROPERTIES ('key'='value');

-- ============================================
-- 12. INSERT
-- ============================================
INSERT INTO normal_table VALUES (1, 'A');

-- ============================================
-- 13. INSERT OVERWRITE PARTITION
-- ============================================
INSERT OVERWRITE TABLE partitioned_table PARTITION(dt)
SELECT id, '2025-01-01' FROM normal_table;

-- ============================================
-- 14. MULTI INSERT (LLM trigger)
-- ============================================
FROM normal_table
INSERT OVERWRITE TABLE high_value
SELECT * WHERE id > 10
INSERT OVERWRITE TABLE low_value
SELECT * WHERE id <= 10;

-- ============================================
-- 15. JOIN
-- ============================================
SELECT a.id, b.name
FROM normal_table a
JOIN complex_table b
ON a.id = b.id;

-- ============================================
-- 16. WINDOW FUNCTION
-- ============================================
SELECT *,
ROW_NUMBER() OVER (PARTITION BY id ORDER BY name) AS rn
FROM normal_table;

-- ============================================
-- 17. LATERAL VIEW
-- ============================================
SELECT id, item
FROM orders
LATERAL VIEW EXPLODE(SPLIT(items, ',')) t AS item;

-- ============================================
-- 18. ANALYZE
-- ============================================
ANALYZE TABLE normal_table COMPUTE STATISTICS FOR COLUMNS;

-- ============================================
-- 19. MSCK REPAIR
-- ============================================
MSCK REPAIR TABLE partitioned_table;

-- ============================================
-- 20. LOAD DATA (unsupported)
-- ============================================
LOAD DATA INPATH '/data/file.csv'
INTO TABLE normal_table;

-- ============================================
-- 21. UDF (BLOCKER)
-- ============================================
ADD JAR hdfs:///libs/my_udf.jar;

CREATE TEMPORARY FUNCTION my_udf AS 'com.example.MyUdf';

SELECT my_udf(name) FROM normal_table;

-- ============================================
-- 22. VARIABLES IN TABLE NAME
-- ============================================
INSERT OVERWRITE TABLE sales_${region}
SELECT * FROM normal_table;

-- ============================================
-- 23. COLON VARIABLES
-- ============================================
INSERT OVERWRITE TABLE target_:run_dt
SELECT * FROM normal_table;

-- ============================================
-- 24. COMPLEX QUERY
-- ============================================
WITH ranked AS (
    SELECT *,
           ROW_NUMBER() OVER (PARTITION BY id ORDER BY created_ts DESC) AS rn
    FROM complex_table
)
SELECT * FROM ranked WHERE rn = 1;

-- ============================================
-- 25. EXPLAIN (should be removed)
-- ============================================
EXPLAIN SELECT * FROM normal_table;

-- ============================================
-- 26. EDGE CASE (broken SQL)
-- ============================================
INSERT OVERWRITE TABLE broken_:var
SELECT * FROM;

-- ============================================
-- 27. FINAL SELECT
-- ============================================
SELECT * FROM normal_table;