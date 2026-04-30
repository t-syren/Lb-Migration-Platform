-- ============================================
-- 🔥 LLM VALIDATION SCRIPT
-- ============================================

-- 1. MULTI INSERT (sqlglot fails → LLM candidate)
FROM sales_ext
INSERT OVERWRITE TABLE high_value_sales
SELECT * WHERE amount > 1000
INSERT OVERWRITE TABLE low_value_sales
SELECT * WHERE amount <= 1000;

-- 2. DYNAMIC VARIABLE IN TABLE NAME (parse error)
INSERT OVERWRITE TABLE target_:run_dt
SELECT * FROM sales_ext;

-- 3. EXTERNAL TABLE WITH LOCATION (needs smart conversion)
CREATE EXTERNAL TABLE ext_llm_test (
    id INT,
    name STRING
)
STORED AS PARQUET
LOCATION '/mnt/data/ext_llm_test/';

-- 4. COMPLEX HIVE FUNCTION (often not handled well)
SELECT
    customer_id,
    from_unixtime(unix_timestamp(order_date, 'yyyy-MM-dd'), 'yyyyMMdd') AS formatted_dt
FROM sales_ext;

-- 5. NESTED + WINDOW + EDGE CASE
SELECT *
FROM (
    SELECT *,
           row_number() OVER (PARTITION BY customer_id ORDER BY amount DESC) AS rn
    FROM sales_ext
) t
WHERE rn = 1;

-- 6. BROKEN SYNTAX (forces LLM fallback)
SELECT customer_id amount FROM sales_ext;