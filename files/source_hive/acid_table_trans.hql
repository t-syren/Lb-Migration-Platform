CREATE TABLE acid_table (
    id INT,
    name STRING
)
CLUSTERED BY (id) INTO 4 BUCKETS
STORED AS ORC
TBLPROPERTIES ('transactional'='true');