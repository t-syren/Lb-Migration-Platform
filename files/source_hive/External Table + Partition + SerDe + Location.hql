-- Script 1: External table with full Hive features
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