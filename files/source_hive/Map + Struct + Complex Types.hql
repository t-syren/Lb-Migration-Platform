CREATE TABLE complex_data (
    id INT,
    attributes MAP<STRING, STRING>,
    metrics STRUCT<clicks:INT, impressions:INT>
)
STORED AS ORC;