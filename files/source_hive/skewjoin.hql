SELECT /*+ SKEWJOIN(a) */
    a.id, b.value
FROM table_a a
JOIN table_b b
ON a.id = b.id;