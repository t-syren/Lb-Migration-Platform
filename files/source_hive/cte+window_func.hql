WITH base AS (
    SELECT customer_id, amount, order_date
    FROM sales_ext
),
ranked AS (
    SELECT *,
           ROW_NUMBER() OVER (PARTITION BY customer_id ORDER BY order_date DESC) as rn
    FROM base
)
SELECT customer_id, amount
FROM ranked
WHERE rn = 1;