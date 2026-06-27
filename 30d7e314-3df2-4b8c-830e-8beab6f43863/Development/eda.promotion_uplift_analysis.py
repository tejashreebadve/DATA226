import numpy as np
import matplotlib.pyplot as plt

# Compute average sales per family: off-promo (onpromotion==0) vs on-promo (onpromotion>0)
promo_grp = (
    train
    .assign(_promo_flag=train['onpromotion'] > 0)
    .groupby(['family', '_promo_flag'])['sales']
    .mean()
    .unstack()
)
promo_grp.columns = ['avg_sales_off', 'avg_sales_on']

# Uplift multiplier: on ÷ off (guard against zero-off divisions)
promo_grp['uplift_multiplier'] = promo_grp['avg_sales_on'] / promo_grp['avg_sales_off'].replace(0, np.nan)

# Top 12 families by uplift
eda_promos = (
    promo_grp
    .dropna(subset=['uplift_multiplier'])
    .sort_values('uplift_multiplier', ascending=False)
    .head(12)
)

# ── Horizontal bar chart ──────────────────────────────────────────────────────
fig_eda_promos, ax_eda_promos = plt.subplots(figsize=(10, 6))

colors = plt.cm.RdYlGn(
    np.linspace(0.3, 0.9, len(eda_promos))
)[::-1]  # green = highest uplift

bars_eda = ax_eda_promos.barh(
    eda_promos.index[::-1],
    eda_promos['uplift_multiplier'].iloc[::-1],
    color=colors,
    edgecolor='white',
    linewidth=0.6
)

# Annotate each bar with the multiplier value
for bar_p, val_p in zip(bars_eda, eda_promos['uplift_multiplier'].iloc[::-1]):
    ax_eda_promos.text(
        bar_p.get_width() + 0.2,
        bar_p.get_y() + bar_p.get_height() / 2,
        f'{val_p:.2f}×',
        va='center', fontsize=9, color='#333333'
    )

ax_eda_promos.set_xlabel('Uplift multiplier  (on-promo avg ÷ off-promo avg)', fontsize=11)
ax_eda_promos.set_title('Top 12 product families by promotion uplift', fontsize=13, fontweight='bold')
ax_eda_promos.spines[['top', 'right']].set_visible(False)
ax_eda_promos.set_xlim(0, eda_promos['uplift_multiplier'].max() * 1.12)
plt.tight_layout()
fig_eda_promos = fig_eda_promos   # capture figure variable
plt.close('all')

# ── Print summary table ───────────────────────────────────────────────────────
print("Top 12 product families by promotion uplift\n")
print(f"{'Family':<35} {'Off-promo avg':>13} {'On-promo avg':>12} {'Uplift ×':>9}")
print("─" * 73)
for _fam, _row in eda_promos.iterrows():
    print(
        f"{_fam:<35} "
        f"{round(_row['avg_sales_off'], 2):>13} "
        f"{round(_row['avg_sales_on'], 2):>12} "
        f"{round(_row['uplift_multiplier'], 2):>9}×"
    )