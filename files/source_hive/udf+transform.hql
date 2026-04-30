ADD JAR hdfs://libs/myudf.jar;

CREATE TEMPORARY FUNCTION my_udf AS 'com.example.MyUDF';

SELECT my_udf(name)
FROM customers;