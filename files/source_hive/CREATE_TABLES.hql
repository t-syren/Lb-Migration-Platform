-- ============================================
-- 🔥 P3 + P4 COMBINED TEST SCRIPT
-- ============================================

-- --------------------------------------------
-- 1. NORMAL CREATE TABLE (should add USING DELTA)
-- --------------------------------------------
CREATE TABLE normal_table (
    id INT,
    name STRING
);

-- --------------------------------------------
-- 2. CREATE TABLE WITH PARTITION (USING before PARTITIONED BY)
-- --------------------------------------------
CREATE TABLE partitioned_table (
    id INT,
    dt STRING
)
PARTITIONED BY (dt);

-- --------------------------------------------
-- 3. CTAS (should NOT add USING DELTA)
-- --------------------------------------------
CREATE TABLE ctas_table AS
SELECT * FROM normal_table;

-- --------------------------------------------
-- 4. CTAS with subquery (regex trap)
-- --------------------------------------------
CREATE TABLE ctas_subquery AS
SELECT * FROM (
    SELECT id FROM normal_table
) t;

-- --------------------------------------------
-- 5. Already USING DELTA (should NOT duplicate)
-- --------------------------------------------
CREATE TABLE already_delta (
    id INT
)
USING DELTA;

-- --------------------------------------------
-- 6. EXTERNAL TABLE WITH HDFS LOCATION (should REMOVE location)
-- --------------------------------------------
CREATE EXTERNAL TABLE ext_hdfs (
    id INT,
    name STRING
)
ROW FORMAT DELIMITED
FIELDS TERMINATED BY ','
STORED AS TEXTFILE
LOCATION 'hdfs://warehouse/ext_hdfs/';

-- --------------------------------------------
-- 7. EXTERNAL TABLE WITH DBFS LOCATION (should KEEP location)
-- --------------------------------------------
CREATE EXTERNAL TABLE ext_dbfs (
    id INT
)
STORED AS PARQUET
LOCATION '/mnt/data/ext_dbfs/';

-- --------------------------------------------
-- 8. EXTERNAL TABLE WITH S3 LOCATION (should KEEP location)
-- --------------------------------------------
CREATE EXTERNAL TABLE ext_s3 (
    id INT
)
STORED AS PARQUET
LOCATION 's3://bucket/path/';

-- --------------------------------------------
-- 9. CREATE TABLE WITH LOCATION (valid delta case)
-- --------------------------------------------
CREATE TABLE delta_with_location (
    id INT
)
LOCATION '/mnt/delta/table_path';

-- --------------------------------------------
-- 10. NESTED QUERY (regex trap for USING DELTA)
-- --------------------------------------------
CREATE TABLE tricky_nested (
    id INT
)
AS
SELECT * FROM (
    SELECT id FROM normal_table
) sub;

-- --------------------------------------------
-- 11. MULTI-LINE COMPLEX CREATE TABLE
-- --------------------------------------------
CREATE TABLE complex_table (
    id INT,
    name STRING,
    created_ts TIMESTAMP
)
COMMENT 'complex table'
PARTITIONED BY (created_ts);

-- --------------------------------------------
-- 12. RANDOM SELECT (should remain untouched)
-- --------------------------------------------
SELECT * FROM normal_table;