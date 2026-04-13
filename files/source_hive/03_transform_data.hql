-- DDL: Create a partitioned table for performance
USE retail_db;

CREATE TABLE IF NOT EXISTS transactions (
    txn_id INT,
    cust_id INT,
    amount DOUBLE
)
PARTITIONED BY (txn_date STRING)
STORED AS ORC;

-- DML: Insert data into a specific partition from another source
INSERT OVERWRITE TABLE transactions PARTITION(txn_date='2024-04-09')
SELECT 5001, 101, 150.50;
