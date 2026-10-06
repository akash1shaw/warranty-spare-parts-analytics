# After-Market Service Analytics: Warranty Cost & Spare-Parts Optimisation

Consulting-style analytics project: where does warranty money go, which suppliers drive it,
and how should spare-parts inventory be run to cut repair delays?

> **Data disclosure:** the bundled dataset is **simulated** (`generate_data.py`, seed 42):
> 17k claims, 12 products, 48 parts, 8 suppliers, 36 months. Say "simulated dataset" on your resume.
> See "Using real data" to swap in public data.

## Run
```
pip install -r requirements.txt
python generate_data.py      # creates data/*.csv
python analysis.py           # SQL KPIs, forecasting, inventory simulation, charts -> outputs/
python genai_assistant.py    # optional NL assistant (needs ANTHROPIC_API_KEY)
```
Power BI / Tableau: load `data/*.csv` (star schema: claims + inventory as facts, products/parts/sales as dims)
or the `outputs/powerbi_*.csv` and `outputs/kpi_*.csv` extracts.

## Findings (simulated data; re-run to see your exact numbers)
1. **Cost:** ~INR 28 mn warranty cost over 3 years; AC products are the largest cost block and peak Apr-Aug.
2. **Suppliers:** S05 and S02 have ~2x the median failure rate per 1,000 units, so they are priority targets
   for a supplier quality programme (50% gap closure ≈ INR 0.5 mn/year).
3. **Stock-outs:** ~28% of claims are delayed by missing parts; a delayed claim takes ~12 extra days to close.
4. **Inventory policy:** the current rule (1.2 x trailing 3-month demand) ignores lead time. A lead-time-aware
   reorder policy cuts simulated stock-outs from ~18% to <1% at the cost of higher inventory.
   Net benefit is **assumption-based** (INR 250 per delayed-claim-day, 20% holding cost). Change them in `analysis.py`.
5. **Forecasting (honest result):** per-part demand is low-count and noisy. A simple trailing mean (WAPE ~24%)
   beat damped-trend ETS (~29%) on a 6-month holdout. The value is in the policy, not a fancier model.
   Do NOT claim an ML model "improved accuracy" unless your own run shows it.

## Using real data (recommended to add to this project)
Real warranty claims are proprietary. Real public alternatives for the same skills:
- **Backblaze Hard Drive Stats** (backblaze.com/cloud-storage/resources/hard-drive-test-data): real daily failure
  data for hundreds of thousands of drives. Treat each failed drive as a "claim" and each model as a "part".
- **NASA C-MAPSS turbofan degradation** (NASA Prognostics Data Repository / Kaggle): run-to-failure sensor data, good for IoT/predictive maintenance.
- **UCI "Online Retail" / Olist Brazilian E-commerce (Kaggle):** real transactional demand data for the forecasting and inventory part.
Keep the same table names and column names and the SQL and analysis scripts will mostly work unchanged.
Check each dataset's licence and verify the current download link yourself.

## Resume bullets (fill with YOUR run's numbers)
- Built an after-market service analytics pipeline (SQL, Python, Power BI) on a simulated 17k-claim warranty dataset.
- Identified 2 suppliers with ~2x median failure rates; quantified an annual savings case from a quality programme.
- Simulated a lead-time-aware spare-parts policy, cutting stock-outs from ~18% to <1% (assumption-based net benefit INR ~2.8 mn/yr).
- Benchmarked 3 forecasting methods on a holdout set; found simple baselines competitive and reported it transparently.
- Built a GenAI text-to-SQL assistant with read-only query guardrails for natural-language insight queries.
