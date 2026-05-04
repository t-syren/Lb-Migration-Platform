SELECT customer_id, item
FROM orders
LATERAL VIEW EXPLODE(split(items, ',')) t AS item;