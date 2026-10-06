-- name: overall_kpis
SELECT COUNT(*) AS total_claims,
       ROUND(SUM(claim_cost_inr) / 1e6, 2) AS total_cost_inr_mn,
       ROUND(AVG(claim_cost_inr), 0) AS avg_cost_per_claim,
       ROUND(AVG(repair_days), 2) AS mean_time_to_repair_days,
       ROUND(100.0 * AVG(stockout_flag), 2) AS pct_claims_delayed_by_stockout
FROM warranty_claims;

-- name: claim_rate_by_product
SELECT p.product_name, p.category,
       COUNT(c.claim_id) AS claims,
       s.units AS units_sold,
       ROUND(100.0 * COUNT(c.claim_id) / s.units, 2) AS claim_rate_pct,
       ROUND(SUM(c.claim_cost_inr) / 1e6, 2) AS cost_inr_mn
FROM products p
JOIN (SELECT product_id, SUM(units_sold) AS units FROM sales GROUP BY product_id) s USING (product_id)
LEFT JOIN warranty_claims c USING (product_id)
GROUP BY p.product_id
ORDER BY cost_inr_mn DESC;

-- name: supplier_quality
WITH part_rate AS (
    SELECT pt.part_id, pt.supplier_id,
           COUNT(c.claim_id) AS claims,
           SUM(c.claim_cost_inr) AS cost,
           (SELECT SUM(units_sold) FROM sales s WHERE s.product_id = pt.product_id) AS units
    FROM parts pt LEFT JOIN warranty_claims c USING (part_id)
    GROUP BY pt.part_id
)
SELECT supplier_id,
       COUNT(*) AS parts_supplied,
       SUM(claims) AS claims,
       ROUND(SUM(cost) / 1e6, 2) AS cost_inr_mn,
       ROUND(AVG(1000.0 * claims / units), 1) AS claims_per_1000_units_per_part
FROM part_rate
GROUP BY supplier_id
ORDER BY claims_per_1000_units_per_part DESC;

-- name: top_cost_parts_pareto
SELECT pt.part_id, pt.part_name, pr.product_name, pt.supplier_id,
       COUNT(*) AS claims,
       ROUND(SUM(c.claim_cost_inr) / 1e6, 2) AS cost_inr_mn
FROM warranty_claims c
JOIN parts pt USING (part_id)
JOIN products pr ON pr.product_id = pt.product_id
GROUP BY pt.part_id
ORDER BY cost_inr_mn DESC
LIMIT 10;

-- name: claims_by_cause_region
SELECT region, failure_cause, COUNT(*) AS claims,
       ROUND(SUM(claim_cost_inr) / 1e6, 2) AS cost_inr_mn
FROM warranty_claims
GROUP BY region, failure_cause
ORDER BY cost_inr_mn DESC;

-- name: stockout_rate_by_part
SELECT i.part_id, pt.part_name, pt.lead_time_days,
       SUM(i.demand) AS demand_units,
       SUM(i.stockout_units) AS stockout_units,
       ROUND(100.0 * SUM(i.stockout_units) / NULLIF(SUM(i.demand), 0), 1) AS stockout_rate_pct,
       ROUND(1.0 * SUM(i.demand) / NULLIF(AVG(i.closing_stock), 0) / 3, 2) AS inventory_turns_per_year
FROM inventory_monthly i JOIN parts pt USING (part_id)
GROUP BY i.part_id
HAVING demand_units > 0
ORDER BY stockout_rate_pct DESC
LIMIT 15;

-- name: monthly_trend
SELECT substr(claim_date, 1, 7) AS month, COUNT(*) AS claims,
       ROUND(SUM(claim_cost_inr) / 1e6, 3) AS cost_inr_mn
FROM warranty_claims GROUP BY month ORDER BY month;

-- name: repair_time_stockout_impact
SELECT stockout_flag, COUNT(*) AS claims, ROUND(AVG(repair_days), 2) AS avg_repair_days
FROM warranty_claims GROUP BY stockout_flag;
