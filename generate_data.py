"""
generate_data.py
Generates a SIMULATED after-market service dataset (warranty claims, sales,
parts master, monthly spare-parts inventory) for Jan 2022 - Dec 2024.

NOTE: This data is synthetic. State this clearly on your resume / README.
To use real data instead, see README.md ("Using real data").
"""
import numpy as np
import pandas as pd

rng = np.random.default_rng(42)
MONTHS = pd.period_range("2022-01", "2024-12", freq="M")
REGIONS = ["North", "South", "East", "West", "Central"]
CAUSES = ["Manufacturing defect", "Wear and tear", "Electrical fault",
          "Software/firmware", "Transport damage", "Improper use"]

# ---------- Products ----------
products = pd.DataFrame({
    "product_id": [f"P{i:02d}" for i in range(1, 13)],
    "product_name": ["AC 1.5T Split", "AC 2T Split", "Fridge 260L", "Fridge 350L",
                     "Washer 7kg", "Washer 9kg", "Microwave 25L", "Microwave 30L",
                     "Water Purifier RO", "Water Purifier UV", "Dishwasher 12pl", "Chimney 90cm"],
    "category": ["Cooling"] * 2 + ["Refrigeration"] * 2 + ["Laundry"] * 2 +
                ["Kitchen"] * 2 + ["Water"] * 2 + ["Kitchen"] * 2,
    "unit_price": [38000, 52000, 27000, 38000, 24000, 33000, 9500, 14000,
                   16000, 14000, 42000, 18000],
    "base_failure_rate": [0.0035, 0.0030, 0.0025, 0.0028, 0.0040, 0.0036,
                          0.0022, 0.0020, 0.0045, 0.0042, 0.0050, 0.0030],
})

# ---------- Suppliers & Parts ----------
suppliers = [f"S{i:02d}" for i in range(1, 9)]
supplier_quality = {s: 1.0 for s in suppliers}
supplier_quality["S05"] = 2.2   # deliberately poor supplier -> insight for analysis
supplier_quality["S02"] = 1.5

part_names = ["Compressor", "PCB Controller", "Motor", "Thermostat", "Fan Assembly",
              "Pump", "Heating Element", "Door Seal", "Sensor", "Display Panel"]
rows = []
pid = 1
for p in products.product_id:
    for k in rng.choice(len(part_names), size=4, replace=False):
        rows.append({
            "part_id": f"PT{pid:03d}",
            "part_name": part_names[k],
            "product_id": p,
            "supplier_id": rng.choice(suppliers),
            "unit_cost": int(np.round(rng.lognormal(7.0, 0.7), -1)),   # ~INR 1,100 median
            "lead_time_days": int(rng.choice([7, 14, 21, 30, 45, 60])),
            "failure_weight": float(rng.uniform(0.5, 2.0)),
        })
        pid += 1
parts = pd.DataFrame(rows)
parts["failure_weight"] *= parts.supplier_id.map(supplier_quality)
parts["failure_weight"] /= parts.groupby("product_id").failure_weight.transform("sum")

# ---------- Monthly sales (units) ----------
sales = []
for p in products.itertuples():
    base = {"Cooling": 900, "Refrigeration": 700, "Laundry": 500, "Kitchen": 450, "Water": 600}[p.category]
    base *= rng.uniform(0.6, 1.4)
    for r in REGIONS:
        rf = rng.uniform(0.6, 1.4)
        for i, m in enumerate(MONTHS):
            season = 1 + (0.45 * np.sin((m.month - 3) / 12 * 2 * np.pi) if p.category == "Cooling" else 0.1 * np.sin(m.month / 12 * 2 * np.pi))
            growth = 1 + 0.01 * i
            units = rng.poisson(max(base * rf * season * growth / 5, 1))
            sales.append((str(m), p.product_id, r, units))
sales = pd.DataFrame(sales, columns=["month", "product_id", "region", "units_sold"])

# ---------- Warranty claims ----------
sales["idx"] = sales.month.map({str(m): i for i, m in enumerate(MONTHS)})
claims = []
cid = 1
part_by_prod = {p: g for p, g in parts.groupby("product_id")}
fail_rate = products.set_index("product_id").base_failure_rate.to_dict()
cat_by_prod = products.set_index("product_id").category.to_dict()
for (p, r), g in sales.groupby(["product_id", "region"]):
    g = g.sort_values("idx").reset_index(drop=True)
    for i, row in g.iterrows():
        installed = g.units_sold.iloc[max(0, i - 23):i + 1].sum()      # 24-month warranty
        m = pd.Period(row.month)
        hot = 1.35 if (cat_by_prod[p] == "Cooling" and m.month in (4, 5, 6, 7)) else 1.0
        n = rng.poisson(installed * fail_rate[p] * hot)
        if n == 0:
            continue
        pp = part_by_prod[p]
        chosen = rng.choice(pp.part_id.values, size=n, p=pp.failure_weight.values)
        for part in chosen:
            pr = parts.loc[parts.part_id == part].iloc[0]
            day = int(rng.integers(1, m.days_in_month + 1))
            cause = rng.choice(CAUSES, p=[.28, .22, .2, .1, .08, .12])
            labour = float(np.round(rng.lognormal(6.0, 0.4), 0))
            repair_days = float(np.round(rng.lognormal(1.0, 0.5), 1))
            claims.append((f"C{cid:06d}", m.to_timestamp().replace(day=day).date(), p, part, r,
                           cause, pr.unit_cost + labour, repair_days))
            cid += 1
claims = pd.DataFrame(claims, columns=["claim_id", "claim_date", "product_id", "part_id",
                                       "region", "failure_cause", "claim_cost_inr", "repair_days"])

# ---------- Monthly inventory simulation (reorder-point policy) ----------
demand = (claims.assign(month=pd.to_datetime(claims.claim_date).dt.to_period("M").astype(str))
          .groupby(["part_id", "month"]).size().rename("demand").reset_index())
inv_rows = []
for part in parts.itertuples():
    d = demand[demand.part_id == part.part_id].set_index("month").demand
    d = d.reindex([str(m) for m in MONTHS], fill_value=0)
    lag = max(1, int(np.ceil(part.lead_time_days / 30)))
    stock = int(d.iloc[:3].mean() * 2) + 2
    pipeline = {}
    for i, m in enumerate(d.index):
        received = pipeline.pop(i, 0)
        opening = stock + received
        need = int(d.iloc[i])
        fulfilled = min(opening, need)
        stockout = need - fulfilled
        stock = opening - fulfilled
        avg3 = d.iloc[max(0, i - 2):i + 1].mean()
        # naive policy: order up to 1.2 x last-3-month average, no seasonality awareness
        target = int(np.ceil(avg3 * 1.2))
        on_order = sum(pipeline.values())
        order = max(0, target - stock - on_order)
        if order:
            pipeline[i + lag] = pipeline.get(i + lag, 0) + order
        inv_rows.append((m, part.part_id, need, opening, fulfilled, stockout, stock, order))
inventory = pd.DataFrame(inv_rows, columns=["month", "part_id", "demand", "opening_stock",
                                            "fulfilled", "stockout_units", "closing_stock", "units_ordered"])

# claims hit by a stock-out wait for the part -> longer repair
so = inventory.set_index(["month", "part_id"]).stockout_units
claims["month"] = pd.to_datetime(claims.claim_date).dt.to_period("M").astype(str)
claims["stockout_flag"] = [int(so.get((m, p), 0) > 0 and rng.random() < 0.6)
                           for m, p in zip(claims.month, claims.part_id)]
claims["repair_days"] += claims.stockout_flag * parts.set_index("part_id").lead_time_days.reindex(claims.part_id).values / 3
claims["repair_days"] = claims.repair_days.round(1)
claims = claims.drop(columns="month")

sales = sales.drop(columns="idx")
parts = parts.drop(columns="failure_weight")
products.to_csv("data/products.csv", index=False)
parts.to_csv("data/parts.csv", index=False)
sales.to_csv("data/sales.csv", index=False)
claims.to_csv("data/warranty_claims.csv", index=False)
inventory.to_csv("data/inventory_monthly.csv", index=False)
print({k: len(v) for k, v in dict(products=products, parts=parts, sales=sales,
                                    claims=claims, inventory=inventory).items()})
