-- DML: Populating the customers table
USE retail_db;

-- Inserting specific records
INSERT INTO TABLE customers VALUES 
(101, 'John', 'Doe', 30, 'New York'),
(102, 'Jane', 'Smith', 25, 'Chicago'),
(103, 'Mike', 'Brown', 45, 'Houston');

-- Loading data from an HDFS path (common in Hive)
-- LOAD DATA INPATH '/user/raw_data/extra_cust.csv' INTO TABLE customers;
