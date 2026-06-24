# Flipkart-Style Synthetic E-Commerce Dataset (Star Schema)

A 2-year (2024–2025) synthetic dataset modeled on a large Indian e-commerce
platform, built for SQL practice and for the agent project (drop straight into
your tool-calling loop in place of/alongside Chinook).

Files:
- `flipkart_ecommerce.db` — SQLite database, all 5 tables, indexed. **Use this directly with your agent.**
- `dim_date.csv`, `dim_customers.csv`, `dim_products.csv`, `dim_sellers.csv`, `fact_sales.csv` — same data as raw CSVs.

## Schema shape

This is a **star schema**: one fact table (`fact_sales`, grain = one order line
item) surrounded by four dimension tables. No snowflaking (no dimension points
to another dimension) — kept intentionally simple so your agent's generated
JOINs stay shallow while you're still building the loop. If you want true
snowflake later, split `dim_customers` into `dim_customers` + `dim_cities`,
or `dim_products` into `dim_products` + `dim_categories`.

```
dim_date ---------\
dim_customers -----\
dim_products -------> fact_sales (grain: order_item_id)
dim_sellers --------/
```

## Tables

### `dim_date` (731 rows)
| column | notes |
|---|---|
| date_id (PK) | `YYYYMMDD` int, join key |
| date | ISO date string |
| day_name, month, month_name, quarter, year | calendar attributes |
| is_weekend | bool |
| is_festival_sale | bool — true during a named sale event |
| festival_name | e.g. "Big Billion Days", "Diwali Sale", null otherwise |
| demand_multiplier | how much order volume was scaled that day (for your reference, not used in queries) |
| discount_min_pct / discount_max_pct | the discount band sampled from that day |

### `dim_customers` (1,200 rows)
customer_id (PK), customer_name, gender, age, email, city, state, **city_tier**
(1/2/3 — tier 1 = metro), signup_date, **customer_segment**
(Regular / Flipkart Plus / Premium).

### `dim_products` (360 rows)
product_id (PK), product_name, **category** (8 categories), sub_category,
brand, **mrp** (max retail price, pre-discount), weight_kg, launch_date.

### `dim_sellers` (70 rows)
seller_id (PK), seller_name, seller_city, seller_state, is_flipkart_assured,
seller_rating, seller_since.

### `fact_sales` (201,138 rows — grain: one row per order line item)
| column | notes |
|---|---|
| order_id | multiple line items share an order_id (62% single-item orders, rest 2–3 items) |
| order_item_id (PK) | unique per line |
| customer_id, product_id, seller_id, date_id | FKs to dimensions |
| quantity | units of that product in this line |
| unit_mrp | product MRP at time of sale |
| discount_pct | applied discount % (higher during festival_sale dates) |
| unit_selling_price, line_total | post-discount pricing |
| payment_method | UPI / Credit Card / Debit Card / Cash on Delivery / Net Banking / Wallet |
| order_status | Delivered / Returned / Cancelled / RTO (delivery attempted, undelivered) |
| promised_delivery_days, actual_delivery_days | null for Cancelled orders |
| delivery_delay_flag | actual > promised |
| rating | 1–5, null if not delivered or not rated (~30% of delivered orders go unrated) |

## Real-world nuances baked in (verified after generation)

- **Seasonality**: order volume jumps ~4x on Big Billion Days, ~3x on Diwali Sale, with smaller lifts on Republic Day/Holi/Independence Day/End-of-Season sales. Discounts jump from a ~8% baseline to ~44% average during these windows.
- **Logistics realism**: average delivery time scales with city tier — ~2.3 days (tier 1) → ~4.5 (tier 2) → ~7.4 (tier 3) — and festival periods add extra delay noise (real strain on logistics during sale spikes).
- **Category behavior differs**: Fashion has the highest return rate (~16%, size/fit issues), Grocery and Books are lowest (~1–2%), matching real e-commerce patterns.
- **Payment skew**: Cash on Delivery is more common in tier 2/3 cities than tier 1; UPI dominates everywhere, consistent with real Indian e-commerce payment mix.
- **Customer segment effects**: Flipkart Plus / Premium customers get extra effective discounts and 1 day shaved off promised delivery.
- **Ratings are correlated, not random**: skewed positive overall, but pulled down when delivery was delayed — and only ~70% of delivered orders get rated at all.

## Suggested first queries for your agent to try

- "What was total revenue during Big Billion Days 2024 vs. a normal week?"
- "Which category has the highest return rate, and does that change in tier 3 cities?"
- "Are Flipkart Plus customers more profitable per order than Regular customers?"
- "Did average delivery delay get worse during Diwali Sale 2025?"

These all require a JOIN, a filter the agent has to infer (festival_name LIKE / is_festival_sale), and in some cases a self-correction loop if it guesses the wrong column name on the first try — good test cases for the verification step you're building.
