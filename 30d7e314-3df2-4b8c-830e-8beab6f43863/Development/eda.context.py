import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

# ── 1. Load stores from CSV ───────────────────────────────────────────────────
stores_ctx = pd.read_csv("stores.csv")

# ── 2. Prepare national daily series from upstream `d` ───────────────────────
_ctx = d.copy()
_ctx["date"] = pd.to_datetime(_ctx["date"])
_ctx = _ctx.set_index("date").sort_index()

_sales_roll  = _ctx["sales"].rolling(30).mean().dropna()
_oil_roll    = _ctx["dcoilwtico"].rolling(30).mean().dropna()
_aligned     = pd.concat([_sales_roll, _oil_roll], axis=1).dropna()
_aligned.columns = ["sales_30d", "oil_30d"]

# ── 3. Correlation ────────────────────────────────────────────────────────────
oil_corr = float(_aligned["sales_30d"].corr(_aligned["oil_30d"]))
print(f"30-day Rolling Correlation  →  Oil vs National Sales: {oil_corr:.4f}")

# ── 4. Dual-axis chart ────────────────────────────────────────────────────────
fig_ctx, ax1 = plt.subplots(figsize=(14, 5))

color_sales = "#1f77b4"
color_oil   = "#d62728"

ax1.plot(_aligned.index, _aligned["sales_30d"], color=color_sales, linewidth=1.8, label="Sales (30d roll.)")
ax1.set_ylabel("National Sales (30-day rolling mean)", color=color_sales, fontsize=11)
ax1.tick_params(axis="y", labelcolor=color_sales)
ax1.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x/1e6:.1f}M"))

ax2 = ax1.twinx()
ax2.plot(_aligned.index, _aligned["oil_30d"], color=color_oil, linewidth=1.8, linestyle="--", label="Oil Price (30d roll.)")
ax2.set_ylabel("Oil Price – WTI (30-day rolling mean)", color=color_oil, fontsize=11)
ax2.tick_params(axis="y", labelcolor=color_oil)

_title = f"National Sales vs Oil Price (30-day Rolling Mean)  |  Pearson r = {oil_corr:.4f}"
fig_ctx.suptitle(_title, fontsize=13, fontweight="bold")
fig_ctx.autofmt_xdate()

lines1, labels1 = ax1.get_legend_handles_labels()
lines2, labels2 = ax2.get_legend_handles_labels()
ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper left", fontsize=10)

plt.tight_layout()
fig_oil_corr = fig_ctx
plt.close("all")

# ── 5. Sales by city (train × stores) ────────────────────────────────────────
_train_stores = train.merge(stores_ctx[["store_nbr", "city", "type"]], on="store_nbr", how="left")

# Total sales per city
_city_sales = (
    _train_stores.groupby("city")["sales"]
    .sum()
    .sort_values(ascending=False)
)
_total_national = _city_sales.sum()
_city_pct       = (_city_sales / _total_national * 100).round(2)

top_city_name = _city_sales.index[0]
top_city_pct  = float(_city_pct.iloc[0])

print(f"\n── Top City ──────────────────────────────────")
print(f"  {top_city_name}: {top_city_pct:.2f}% of national sales")

# Top-10 cities summary
print(f"\n── Top-10 Cities by Sales Share ──────────────")
_top10 = pd.concat([_city_sales.head(10).rename("total_sales"), _city_pct.head(10).rename("share_pct")], axis=1)
_top10["total_sales"] = _top10["total_sales"].map("{:,.0f}".format)
_top10["share_pct"]   = _top10["share_pct"].map("{:.2f}%".format)
print(_top10.to_string())

# ── 6. Average store sales by store type ─────────────────────────────────────
_type_sales = (
    _train_stores.groupby(["store_nbr", "type"])["sales"]
    .sum()
    .reset_index()
    .groupby("type")["sales"]
    .mean()
    .sort_values(ascending=False)
)

print(f"\n── Avg Store Sales by Store Type ─────────────")
for _stype, _val in _type_sales.items():
    print(f"  Type {_stype}: {_val:,.0f}")