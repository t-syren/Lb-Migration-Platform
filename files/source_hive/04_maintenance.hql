-- DDL: Altering schema
USE retail_db;

ALTER TABLE customers ADD COLUMNS (email STRING);

-- DML: Using Overwrite to "update" data (standard Hive approach)
-- This creates a full refresh of the table with generated emails
INSERT OVERWRITE TABLE customers
SELECT cust_id, first_name, last_name, age, city, 
       CONCAT(LOWER(first_name), '.', LOWER(last_name), '@email.com') 
FROM customers;

-- DDL: Truncate table to remove all data but keep structure
-- TRUNCATE TABLE transactions;
