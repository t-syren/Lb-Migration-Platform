CREATE TABLE bucketed_table (
    user_id STRING,
    event_time TIMESTAMP
)
CLUSTERED BY (user_id) INTO 8 BUCKETS
SORTED BY (event_time)
STORED AS ORC;