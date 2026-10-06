"""
analysis.py
1. Loads CSVs into SQLite and runs the SQL KPI queries
2. Forecasts spare-part demand (Holt-Winters vs baselines) and reports WAPE
3. Re-simulates inventory with a lead-time-aware policy and estimates savings
4. Saves charts + CSV extracts for Power BI / Tableau
"""
import re, sqlite3, warnings
import numpy as np, pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from statsmodels.tsa.holtwinters import ExponentialSmoothing

warnings.filterwarnings("ignore")
OUT = "outputs"

# ---------------- 1. SQL layer ----------------
con = sqlite3.connect("warranty.db")
for t in ["products", "parts", "sales", "warranty_claims", "inventory_monthly"]:
    pd.read_csv(f"data/{t}.csv").to_sql(t, con, if_exists="replace", index=False)

queries = {}
for block in open("sql/kpis.sql").read().split("-- name:")[1:]:
    name, sql = block.split("\n", 1)
    queries[name.strip()] = sql.strip().rstrip(";")
res = {k: pd.read_sql(q, con) for k, q in queries.items()}
for k, df in res.items():
    df.to_csv(f"{OUT}/kpi_{k}.csv", index=False)
    print(f"\n=== {k} ===\n{df.head(8).to_string(index=False)}")

# ---------------- 2. Demand forecasting ----------------
inv = pd.read_csv("data/inventory_monthly.csv")
parts = pd.read_csv("data/parts.csv")
demand = inv.pivot(index="month", columns="part_id", values="demand").sort_index()
TEST = 6
top_parts = demand.sum().sort_values(ascending=False).head(15).index

def wape(actual, pred):
    return 100 * np.abs(actual - pred).sum() / max(actual.sum(), 1)

rows, fc_export = [], []
for p in top_parts:
    y = demand[p].astype(float)
    train, test = y.iloc[:-TEST], y.iloc[-TEST:]
    naive = np.repeat(train.iloc[-3:].mean(), TEST)                 # baseline 1: trailing mean
    snaive = train.iloc[-12:-12 + TEST].values                      # baseline 2: seasonal naive
    def ets(tr, h):
        try:
            return ExponentialSmoothing(tr + 0.1, trend="add", damped_trend=True).fit().forecast(h).clip(lower=0).values
        except Exception:
            return np.repeat(tr.iloc[-3:].mean(), h)
    def candidates(tr, h):
        return {"trailing_mean": np.repeat(tr.iloc[-3:].mean(), h),
                "seasonal_naive": tr.iloc[-12:-12 + h].values,
                "ets_damped": ets(tr, h)}
    # pick the model on a validation window carved out of the TRAIN set only
    val_tr, val = train.iloc[:-TEST], train.iloc[-TEST:]
    scores = {k: wape(val.values, v) for k, v in candidates(val_tr, TEST).items()}
    chosen = min(scores, key=scores.get)
    cand = candidates(train, TEST)
    hw = cand[chosen]
    rows.append((p, chosen, wape(test.values, cand["trailing_mean"]),
                 wape(test.values, cand["seasonal_naive"]), wape(test.values, cand["ets_damped"]),
                 wape(test.values, hw)))
    for m, a_, f in zip(test.index, test.values, hw):
        fc_export.append((p, m, a_, round(float(f), 2)))

fc = pd.DataFrame(rows, columns=["part_id", "chosen_model", "WAPE_trailing_mean", "WAPE_seasonal_naive", "WAPE_ets_damped", "WAPE_selected"])
print("\n=== Forecast accuracy (WAPE %, lower is better, last 6 months holdout) ===")
print(fc.round(1).to_string(index=False))
print("\nAverage WAPE:", fc.iloc[:, 2:].mean().round(1).to_dict())
fc.to_csv(f"{OUT}/forecast_accuracy.csv", index=False)
pd.DataFrame(fc_export, columns=["part_id", "month", "actual", "forecast"]).to_csv(
    f"{OUT}/powerbi_forecast_vs_actual.csv", index=False)

# ---------------- 3. Inventory policy re-simulation ----------------
lead = parts.set_index("part_id").lead_time_days
unit_cost = parts.set_index("part_id").unit_cost

def simulate(policy):
    tot_so = tot_dem = 0
    stock_sum = 0
    for p in demand.columns:
        d = demand[p].values
        lag = max(1, int(np.ceil(lead[p] / 30)))
        stock, pipe = int(d[:3].mean() * 2) + 2, {}
        for i in range(len(d)):
            stock += pipe.pop(i, 0)
            sold = min(stock, d[i]); tot_so += d[i] - sold; tot_dem += d[i]
            stock -= sold; stock_sum += stock * unit_cost[p]
            h = d[max(0, i - 2):i + 1]
            if policy == "current":
                target = int(np.ceil(h.mean() * 1.2))
            else:   # lead-time-aware: cover lead time + safety stock (z=1.65)
                h6 = d[max(0, i - 5):i + 1]
                target = int(np.ceil(h.mean() * (lag + 1) + 1.65 * h6.std() * np.sqrt(lag + 1)))
            order = max(0, target - stock - sum(pipe.values()))
            if order:
                pipe[i + lag] = pipe.get(i + lag, 0) + order
    return tot_so, tot_dem, stock_sum / len(demand)   # avg total inventory value (INR)

so_a, dem, inv_a = simulate("current")
so_b, _, inv_b = simulate("proposed")
claims = pd.read_csv("data/warranty_claims.csv")
delay = claims.groupby("stockout_flag").repair_days.mean()
extra_days = delay.get(1, 0) - delay.get(0, 0)

# ---- Assumptions (state these in your deck) ----
COST_PER_DELAYED_CLAIM_DAY = 250      # INR: technician revisit + customer goodwill cost
HOLDING_RATE = 0.20                   # annual holding cost as % of inventory value
years = len(demand) / 12
saving_delay = (so_a - so_b) * extra_days * COST_PER_DELAYED_CLAIM_DAY / years
extra_holding = (inv_b - inv_a) * HOLDING_RATE
print("\n=== Inventory policy simulation ===")
print(f"Stock-out rate:  current {100*so_a/dem:.1f}%  ->  proposed {100*so_b/dem:.1f}%")
print(f"Avg inventory value: current INR {inv_a:,.0f}  ->  proposed INR {inv_b:,.0f}")
print(f"Extra repair days when a stock-out occurs: {extra_days:.1f}")
print(f"Annual delay-cost avoided : INR {saving_delay:,.0f}")
print(f"Annual extra holding cost : INR {extra_holding:,.0f}")
print(f"NET annual benefit        : INR {saving_delay - extra_holding:,.0f}  (assumption-based)")

# Supplier quality scenario (worst two suppliers derived from data, not hard-coded)
sq = res["supplier_quality"]
bench = sq.claims_per_1000_units_per_part.median()
worst = sq.head(2)
gap_cost = sum(r.cost_inr_mn * 1e6 * max(0, 1 - bench / r.claims_per_1000_units_per_part) for r in worst.itertuples())
print(f"\nWorst suppliers by failure rate: {list(worst.supplier_id)} (benchmark = median supplier)")
print(f"Closing 50% of the gap to benchmark = INR {gap_cost*0.5/years/1e6:.2f} mn / year")
# ---------------- 4. Charts ----------------
plt.rcParams.update({"figure.dpi": 130, "axes.spines.top": False, "axes.spines.right": False})
m = res["monthly_trend"]
fig, ax = plt.subplots(figsize=(8, 3.5)); ax.plot(m.month, m.cost_inr_mn, color="#6d28d9")
ax.set_xticks(m.month[::4]); ax.set_title("Monthly warranty cost (INR mn)"); plt.tight_layout()
plt.savefig(f"{OUT}/chart_monthly_cost.png"); plt.close()

s = res["supplier_quality"].sort_values("claims_per_1000_units_per_part")
fig, ax = plt.subplots(figsize=(6, 3.5)); ax.barh(s.supplier_id, s.claims_per_1000_units_per_part, color="#6d28d9")
ax.set_title("Failure rate by supplier (claims per 1,000 units, per part)"); plt.tight_layout()
plt.savefig(f"{OUT}/chart_supplier_cost.png"); plt.close()

pa = res["claim_rate_by_product"]
fig, ax = plt.subplots(figsize=(7, 4)); ax.barh(pa.product_name[::-1], pa.claim_rate_pct[::-1], color="#6d28d9")
ax.set_title("Claim rate by product (% of units sold)"); plt.tight_layout()
plt.savefig(f"{OUT}/chart_claim_rate.png"); plt.close()

best = top_parts[0]; f = pd.DataFrame(fc_export, columns=["p", "m", "a", "f"]); f = f[f.p == best]
fig, ax = plt.subplots(figsize=(7, 3.5))
ax.plot(demand.index[-24:], demand[best].iloc[-24:], label="Actual", color="#111")
ax.plot(f.m, f.f, "--", label="Forecast", color="#6d28d9")
ax.set_xticks(demand.index[-24::4]); ax.legend(); ax.set_title(f"Demand forecast vs actual: {best}")
plt.tight_layout(); plt.savefig(f"{OUT}/chart_forecast.png"); plt.close()
print("\nCharts and CSV extracts saved to outputs/")
