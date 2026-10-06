# After-Market Service Analytics: Warranty Cost & Spare-Parts Optimisation

**Stack:** Python · SQL (SQLite) · statsmodels · Power BI / Tableau · Claude API (text-to-SQL)

A consulting-style analytics project that answers three questions an after-market service business cares about:

1. **Where is the warranty money going?** (products, parts, regions, failure causes)
2. **Which suppliers drive failures?** (volume-normalised, so big suppliers aren't unfairly blamed)
3. **How should spare-parts inventory be run to cut repair delays**, and what is that worth?

> **Data disclosure:** the dataset is **simulated** (`generate_data.py`, fixed seed 42). Real warranty data is
> proprietary. It is built with realistic structure (seasonality, a 24-month warranty window, a few deliberately weak
> suppliers, lead-time-driven stock-outs) so the analysis workflow is realistic, but **the findings below describe the
> simulation, not a real company.** See [Using real data](#using-real-data).

---

## Business problem

A consumer-durables manufacturer (ACs, refrigerators, washers, kitchen appliances, water purifiers) sells through five
regions with a 24-month warranty. Management sees rising warranty cost and slow repairs, but does not know whether the
cause is product quality, supplier quality, or spare-parts availability.

## Dataset (simulated)

| Table | Rows | Description |
|---|---|---|
| `products` | 12 | Product, category, price, base failure rate |
| `parts` | 48 | Part, product, supplier, unit cost, lead time (days) |
| `sales` | 2,160 | Monthly units sold by product and region, 2022-01 to 2024-12 |
| `warranty_claims` | 17,086 | Claim date, part, region, failure cause, cost (INR), repair days, stock-out flag |
| `inventory_monthly` | 1,728 | Monthly demand, opening/closing stock, stock-out units per part |

## Project structure

```
warranty_project/
├── generate_data.py        # builds the simulated dataset -> data/
├── sql/kpis.sql            # 8 named KPI queries (read by analysis.py)
├── analysis.py             # SQL KPIs, demand forecasting, inventory simulation, charts
├── genai_assistant.py      # natural-language Q&A over the database (Claude API)
├── data/                   # CSV tables
├── outputs/                # charts + CSV extracts for Power BI / Tableau
├── requirements.txt
└── README.md
```

## How to run

```bash
pip install -r requirements.txt
python generate_data.py        # creates data/*.csv   (optional, CSVs are included)
python analysis.py             # prints KPIs, writes outputs/
python genai_assistant.py      # optional; needs ANTHROPIC_API_KEY
```

Requires Python 3.10+. On Mac/Linux use `python3` / `pip3`.
For the assistant: `export ANTHROPIC_API_KEY=your_key` (Windows: `set ANTHROPIC_API_KEY=your_key`).

## Method

1. **SQL layer.** CSVs are loaded into SQLite and 8 KPI queries compute claim rate, cost per claim, mean time to repair,
   supplier failure rate, a part-level Pareto, stock-out rate and the repair-time impact of stock-outs.
2. **Demand forecasting.** For the 15 highest-demand parts, three methods (trailing mean, seasonal naive, damped-trend
   exponential smoothing) are compared on a 6-month holdout using WAPE. The model is selected per part on a validation
   window carved from the training data only, so there is no test-set leakage.
3. **Inventory policy simulation.** The current policy (order up to 1.2 x trailing 3-month demand, ignoring lead time) is
   compared against a lead-time-aware policy (cover lead-time demand + safety stock at z = 1.65).
4. **Business case.** Stock-out reduction is converted to rupees using explicit, editable assumptions, and the extra
   holding cost is netted off.
5. **GenAI assistant.** An LLM converts a plain-English question to SQL; a guardrail only allows a single read-only
   `SELECT`/`WITH` statement; the result is summarised back in plain language.

## Key findings (simulated data, seed 42)

| Metric | Result |
|---|---|
| Total claims / cost | 17,086 claims, **INR 28.1 mn** over 3 years (avg INR 1,645 per claim) |
| Mean time to repair | 6.4 days overall |
| Claims delayed by missing parts | **28.3%** |
| Repair time with vs without stock-out | **15.0 vs 3.1 days** (about 12 extra days) |
| Largest cost block | AC products (1.5T and 2T Split), with a clear Apr-Aug peak |
| Weakest suppliers | **S05: 25.6** and **S02: 18.2** claims per 1,000 units per part, vs a median of about 12.9 (about 2.0x and 1.4x) |
| Stock-out rate, current policy | 17.8% |
| Stock-out rate, lead-time-aware policy | **0.7%** |
| Net annual benefit of the new policy | **about INR 2.8 mn** (delay cost avoided less extra holding cost) |
| Supplier quality programme | Closing 50% of the gap to the median supplier is worth about INR 0.5 mn/year |

![Monthly warranty cost](outputs/chart_monthly_cost.png)
![Failure rate by supplier](outputs/chart_supplier_cost.png)
![Claim rate by product](outputs/chart_claim_rate.png)
![Forecast vs actual](outputs/chart_forecast.png)

### An honest note on forecasting
Per-part spare-parts demand is low-count and noisy. Average WAPE on the holdout:

| Method | WAPE |
|---|---|
| Trailing mean | 24.4% |
| Seasonal naive | 24.9% |
| Damped-trend ETS | 28.9% |
| Per-part selected model | 27.8% |

A simple baseline beat the more sophisticated model. The takeaway is that **the biggest lever is the replenishment
policy (lead-time awareness and safety stock), not a fancier forecast.** Reporting this openly is deliberate.

## Recommendations (what I'd present to the client)

1. **Fix replenishment first:** move from a flat 1.2x rule to lead-time-aware reorder points with safety stock.
   Start with the long-lead-time (45-60 day) parts, which have the highest stock-out rates.
2. **Launch a supplier quality programme** targeting S05 and S02, using joint root-cause analysis and incoming inspection.
3. **Pre-position AC spares before April**, since cooling claims peak in Apr-Aug.
4. **Track three KPIs monthly:** stock-out rate, % of claims delayed by parts, and claims per 1,000 units by supplier.

## Assumptions and limitations

- All data is simulated, so absolute numbers are illustrative; the *method* is what transfers.
- Savings use two assumptions: **INR 250 per delayed claim-day** and **20% annual holding cost**. Both are editable at the top of the
  business-case section in `analysis.py`.
- The inventory simulation uses monthly buckets and a simplified lead time (rounded up to whole months).
- The 12-day delay figure is observed in simulated data, where stock-outs mechanically add repair time.
- No causal claims about suppliers: in real data you would control for product mix and usage conditions.

## Using real data

Real public datasets that can replace or complement the simulation (verify current links and licences before use):

- **Backblaze Hard Drive Stats:** real daily drive failures; treat a failed drive as a claim and a drive model as a part.
- **NASA C-MAPSS turbofan degradation:** run-to-failure sensor data for the predictive-maintenance / IoT angle.
- **Olist Brazilian E-commerce (Kaggle):** real transactional data for demand forecasting and inventory.

Keep the same table and column names and `sql/kpis.sql` and `analysis.py` will largely work unchanged.

## Power BI / Tableau dashboard

Load `data/*.csv` and relate `warranty_claims` and `inventory_monthly` to `parts` (on `part_id`) and `products` (on `product_id`).
Suggested pages: **Overview** (KPI cards, monthly trend), **Suppliers & parts** (supplier failure rate, top-10 parts, region slicer),
**Inventory & forecast** (stock-outs by part, forecast vs actual from `outputs/powerbi_forecast_vs_actual.csv`).

*(Add dashboard screenshots here.)*

## Possible extensions

- Predict which claims will be stock-out-delayed (classification) and route parts proactively.
- Add warranty-cost accrual forecasting by product cohort.
- Feed IoT sensor data for predictive replacement; connect to SAP service data in production.
- Deploy the assistant as a Streamlit app.
