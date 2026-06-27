import os; os.environ.setdefault('MPLCONFIGDIR', '/tmp/mpl')
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

# ── Build family-level daily series ───────────────────────────────────────────
# train flows from aggregate_national_daily (raw store-level df, 3M rows)
_tr = train.copy()
_tr['date'] = pd.to_datetime(_tr['date'])

# Aggregate to family × date level (sum sales across all stores)
_fam_daily = (
    _tr.groupby(['family', 'date'], as_index=False)['sales'].sum()
       .sort_values(['family', 'date'])
)

# ── Evaluation window: last 60 days of history ────────────────────────────────
_cutoff = _fam_daily['date'].max()
_eval_start = _cutoff - pd.Timedelta(days=59)

# ── Seasonal-naive lag-7 MAPE per family ──────────────────────────────────────
def _lag7_mape(grp):
    """Compute lag-7 MAPE on the last-60-day window for one family."""
    _g = grp.sort_values('date').set_index('date')['sales']
    _eval = _g[_g.index >= _eval_start]
    if len(_eval) < 7:
        return np.nan
    _actual = _eval.values
    # naive = same day 7 days earlier; available since we have full history
    _naive  = np.array([
        _g.get(_d - pd.Timedelta(days=7), np.nan)
        for _d in _eval.index
    ])
    _mask = (_actual > 0) & ~np.isnan(_naive)
    if _mask.sum() < 5:
        return np.nan
    return np.mean(np.abs((_actual[_mask] - _naive[_mask]) / _actual[_mask])) * 100

_mapes = (
    _fam_daily
    .groupby('family')
    .apply(_lag7_mape)
    .dropna()
    .rename('lag7_mape')
    .sort_values()
    .reset_index()
)
_mapes.columns = ['family', 'lag7_mape']

# ── Print ranked table ─────────────────────────────────────────────────────────
print(f"Per-family forecastability  |  Seasonal Naive (lag-7) MAPE — last 60 days")
print(f"{'Rank':>4}  {'Family':<35}  {'MAPE %':>8}  {'Tier':>14}")
print("─" * 67)
_n = len(_mapes)
for _i, (_fam, _m) in enumerate(_mapes[['family', 'lag7_mape']].itertuples(index=False)):
    _tier = ('Most forecastable' if _i < _n * 0.33 else
             'Least forecastable' if _i >= _n * 0.67 else
             'Moderate')
    print(f"  {_i+1:>2}  {_fam:<35}  {_m:>8.1f}%  {_tier}")

print()
_best  = _mapes.iloc[0]
_worst = _mapes.iloc[-1]
print(f"Most forecastable  : {_best['family']} ({_best['lag7_mape']:.1f}% MAPE) → "
      f"stable pattern; keep lean safety stock, reduce over-ordering.")
print(f"Least forecastable : {_worst['family']} ({_worst['lag7_mape']:.1f}% MAPE) → "
      f"high volatility; hold larger buffers or use slower-reacting reorder policies.")

# ── Horizontal bar chart ───────────────────────────────────────────────────────
_n_fam   = len(_mapes)
_bar_h   = 0.55
_fig_h   = max(8, _n_fam * 0.38)

fig_forecastability, ax_fc = plt.subplots(figsize=(11, _fig_h))
fig_forecastability.patch.set_facecolor('#1D1D20')
ax_fc.set_facecolor('#1D1D20')

# Colour: green (low MAPE = forecastable) → red (high MAPE = volatile)
_norm  = (_mapes['lag7_mape'] - _mapes['lag7_mape'].min()) / \
         (_mapes['lag7_mape'].max() - _mapes['lag7_mape'].min() + 1e-9)
_palette = [
    '#8DE5A1' if v < 0.33 else ('#FFB482' if v < 0.67 else '#FF9F9B')
    for v in _norm
]

_bars = ax_fc.barh(
    _mapes['family'], _mapes['lag7_mape'],
    height=_bar_h, color=_palette, edgecolor='#2a2a2e', linewidth=0.5
)

# Annotate bars
for _bar, _val in zip(_bars, _mapes['lag7_mape']):
    ax_fc.text(
        _bar.get_width() + 0.5, _bar.get_y() + _bar.get_height() / 2,
        f'{_val:.1f}%', va='center', ha='left', fontsize=8, color='#fbfbff'
    )

# Tier separator lines
_t1 = _mapes['lag7_mape'].quantile(0.33)
_t2 = _mapes['lag7_mape'].quantile(0.67)
ax_fc.axvline(_t1, color='#8DE5A1', lw=1.0, linestyle='--', alpha=0.6)
ax_fc.axvline(_t2, color='#FF9F9B', lw=1.0, linestyle='--', alpha=0.6)
ax_fc.text(_t1 + 0.3, _n_fam - 0.7, 'forecastable threshold',
           color='#8DE5A1', fontsize=7.5, va='top')
ax_fc.text(_t2 + 0.3, _n_fam - 0.7, 'volatile threshold',
           color='#FF9F9B', fontsize=7.5, va='top')

_xmax = _mapes['lag7_mape'].max() * 1.18
ax_fc.set_xlim(0, _xmax)
ax_fc.set_xlabel('Seasonal Naive Lag-7 MAPE % (last 60 days)', color='#909094', fontsize=9)
ax_fc.set_title(
    'Per-family forecastability ranking\n'
    'Lower MAPE = more predictable = safer for lean inventory',
    color='#fbfbff', fontsize=11, fontweight='bold'
)
ax_fc.tick_params(axis='y', colors='#fbfbff', labelsize=8)
ax_fc.tick_params(axis='x', colors='#fbfbff', labelsize=8)
ax_fc.set_yticks(range(len(_mapes)))
ax_fc.set_yticklabels(_mapes['family'], fontsize=8, color='#fbfbff')
ax_fc.spines[['top', 'right']].set_visible(False)
ax_fc.spines[['left', 'bottom']].set_color('#444')
ax_fc.grid(axis='x', color='#333', linewidth=0.5, linestyle='--')

plt.tight_layout()
plt.close('all')
