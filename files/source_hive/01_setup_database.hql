-- DDL: Database and Table Setup
CREATE DATABASE IF NOT EXISTS retail_db
COMMENT 'Database for retail business data';

USE retail_db;

CREATE TABLE IF NOT EXISTS customers (
    cust_id INT,
    first_name STRING,
    last_name STRING,
    age INT,
    city STRING
)
ROW FORMAT DELIMITED
FIELDS TERMINATED BY ','
STORED AS TEXTFILE;
