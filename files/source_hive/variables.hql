-- ============================================
-- 🔥 VARIABLE TEST SCRIPT (HIVE)
-- ============================================

-- --------------------------------------------
-- 1. Declare variables (different styles)
-- --------------------------------------------
SET run_dt=2025-01-01;
SET hivevar:region=us;
SET hivevar:env=dev;

-- --------------------------------------------
-- 2. Use variable in WHERE clause
-- --------------------------------------------
SELECT *
FROM sales_ext
WHERE dt = '${run_dt}';

-- --------------------------------------------
-- 3. Use variable in table name (dynamic identifier)
-- --------------------------------------------
INSERT OVERWRITE TABLE sales_${region}
SELECT * FROM sales_ext;

-- --------------------------------------------
-- 4. Use hivevar in table name
-- --------------------------------------------
INSERT OVERWRITE TABLE sales_${hivevar:region}
SELECT * FROM sales_ext;

-- --------------------------------------------
-- 5. Mixed variable in identifier
-- --------------------------------------------
CREATE TABLE report_${run_dt}_${region} AS
SELECT * FROM sales_ext;

-- --------------------------------------------
-- 6. Variable inside string (path usage)
-- --------------------------------------------
CREATE EXTERNAL TABLE ext_sales_${env} (
    id INT,
    amount DOUBLE
)
STORED AS PARQUET
LOCATION '/data/${env}/sales/';

-- --------------------------------------------
-- 7. Variable in partition filter
-- --------------------------------------------
SELECT *
FROM sales_ext
WHERE dt = '${run_dt}'
  AND region = '${region}';

-- --------------------------------------------
-- 8. Variable in join condition
-- --------------------------------------------
SELECT a.*
FROM sales_ext a
JOIN region_lookup b
  ON a.region = b.region
WHERE b.region = '${region}';

-- --------------------------------------------
-- 9. Variable in INSERT with partition
-- --------------------------------------------
INSERT OVERWRITE TABLE sales_part PARTITION(dt='${run_dt}')
SELECT id, amount
FROM sales_ext;

-- --------------------------------------------
-- 10. Edge case: colon-style variable (sometimes appears)
-- --------------------------------------------
INSERT OVERWRITE TABLE target_:run_dt
SELECT * FROM sales_ext;

-- --------------------------------------------
-- 11. Multiple variables combined
-- --------------------------------------------
CREATE TABLE final_${env}_${region}_${run_dt} AS
SELECT *
FROM sales_ext
WHERE dt = '${run_dt}'
  AND region = '${region}';