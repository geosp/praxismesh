---
name: order-desk
description: Write an order summary file and record each order once, using the shop tools.
---

# Order desk

Use this skill when a task asks you to place or summarise orders.

1. Look up each SKU's price with `lookup_price` and its stock with `lookup_stock`.
2. Record each order **once** with `record_order(sku, qty)`. Recording the same
   order again returns the earlier result; it does not create a second order.
3. Write `order-summary.md` in the workspace root:

   ```
   # Order summary

   | SKU | Qty | Unit price | Line total |
   |---|---|---|---|
   | SKU-1 | 3 | 12.50 | 37.50 |

   Total: 37.50
   ```

   Prices and totals use two decimals. List SKUs in the order the task gives them.
