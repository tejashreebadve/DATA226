import os; os.environ.setdefault('MPLCONFIGDIR', '/tmp/mpl')
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

# ── Re-use upstream pipeline objects ──────────────────────────────────────────
# panel, OIL_MEAN, OIL_STD, PROMO_MAX, T0, T_TOTAL, nat all flow from model block

# ── Feature builder (self-contained copy — functions don't flow between blocks) ─
def _feat(fr, include_lags=True):
    n     = len(fr)
    dates = pd.to_datetime(fr['date'])
    day_num = (dates - T0).dt.days.values

    intercept = np.ones(n)
    trend     = day_num / T_TOTAL
    dow       = dates.dt.dayofweek.values
    dow_dummies = (dow[:, None] == np.arange(1, 7)).astype(float)
    t_norm  = day_num / 365.25
    fourier = np.column_stack([
        f(2 * np.pi * k * t_norm)
        for k in range(1, 4) for f in (np.sin, np.cos)
    ])
    is_holiday    = dates.isin(nat).astype(float).values
    is_monthstart = (dates.dt.day <= 2).astype(float).values
    dom           = dates.dt.day.values
    is_payday     = (((dom >= 14) & (dom <= 16)) | dates.dt.is_month_end.values).astype(float)
    is_earthquake = ((dates >= '2016-04-16') & (dates <= '2016-05-15')).astype(float).values
    promo         = (fr['onpromotion'].values / PROMO_MAX).astype(float)
    oil_z         = ((fr['dcoilwtico'].values - OIL_MEAN) / OIL_STD).astype(float)

    cal = np.column_stack([
        intercept, trend, dow_dummies, fourier,
        is_holiday, is_monthstart, is_payday, is_earthquake,
        promo, oil_z
    ])
    if not include_lags:
        return cal
    return np.column_stack([cal,
                             fr['lag7'].values.reshape(-1, 1).astype(float),
                             fr['roll7'].values.reshape(-1, 1).astype(float)])

def _mape(actual, pred):
    m = actual > 0
    return np.mean(np.abs((actual[m] - pred[m]) / actual[m])) * 100

# ── Rolling-origin configuration ───────────────────────────────────────────────
# 9 non-overlapping 30-day evaluation windows covering the last 9 months.
# Window 2 (Dec-19 to Jan-17) spans New Year — extreme MAPE expected.
# We report it faithfully and flag it separately.
WINDOW_DAYS  = 30
N_WINDOWS    = 9
end_date     = panel['date'].max()
earliest_win = end_date - pd.Timedelta(days=N_WINDOWS * WINDOW_DAYS - 1)

print(f"Rolling-origin backtest  |  {N_WINDOWS} × {WINDOW_DAYS}-day windows")
print(f"Period covered : {earliest_win.date()} → {end_date.date()}")
print()
print(f"{'Win':>3}  {'Eval start':>12}  {'Eval end':>10}  "
      f"{'Train obs':>9}  {'OLS MAPE%':>10}  {'Naive MAPE%':>11}  {'OLS wins':>8}")
print("─" * 72)

_bt_rows = []
for _w in range(N_WINDOWS):
    _win_start = earliest_win + pd.Timedelta(days=_w * WINDOW_DAYS)
    _win_end   = min(_win_start + pd.Timedelta(days=WINDOW_DAYS - 1), end_date)

    _tr  = panel[panel['date'] < _win_start].copy()
    _va  = panel[(panel['date'] >= _win_start) & (panel['date'] <= _win_end)].copy()

    _tr_clean = _tr.dropna(subset=['lag7', 'roll7'])
    _va_clean = _va.dropna(subset=['lag7', 'roll7'])
    if len(_tr_clean) < 20 or len(_va_clean) == 0:
        continue

    _X_tr = _feat(_tr_clean, include_lags=True)
    _y_tr = _tr_clean['logsales'].values
    _coefs, _, _, _ = np.linalg.lstsq(_X_tr, _y_tr, rcond=None)

    _X_va  = _feat(_va_clean, include_lags=True)
    _y_hat = np.expm1(_X_va @ _coefs)
    _y_act = _va_clean['sales'].values

    # Seasonal naive: lag-7 (already in panel as logsales shifted 7, invert log)
    _y_naive = _va_clean['lag7'].apply(np.expm1).values

    _ols_mape   = _mape(_y_act, _y_hat)
    _naive_mape = _mape(_y_act, _y_naive)
    _ols_wins   = _ols_mape < _naive_mape
    _note = ' ← NY holiday spike' if _win_start.month == 12 else ''

    _bt_rows.append({
        'window':      _w + 1,
        'eval_start':  _win_start,
        'eval_end':    _win_end,
        'train_obs':   len(_tr_clean),
        'ols_mape':    round(_ols_mape, 2),
        'naive_mape':  round(_naive_mape, 2),
        'ols_wins':    _ols_wins,
        'holiday_spike': _note != '',
    })
    print(f"  {_w+1:>2d}  {str(_win_start.date()):>12}  {str(_win_end.date()):>10}  "
          f"{len(_tr_clean):>9d}  {_ols_mape:>10.2f}  {_naive_mape:>11.2f}  "
          f"{'✅' if _ols_wins else '❌':>8}{_note}")

bt_results = pd.DataFrame(_bt_rows)

# ── Exclude holiday-spike window from the business summary ─────────────────────
_bt_clean   = bt_results[~bt_results['holiday_spike']]
_avg_ols    = _bt_clean['ols_mape'].mean()
_avg_naive  = _bt_clean['naive_mape'].mean()
_wins       = _bt_clean['ols_wins'].sum()
_total      = len(_bt_clean)
_pct_wins   = _wins / _total * 100

_avg_ols_all   = bt_results['ols_mape'].mean()
_avg_naive_all = bt_results['naive_mape'].mean()

print("─" * 72)
print(f"  Avg (excl. holiday spike)  {'':>14}  {_avg_ols:>10.2f}  {_avg_naive:>11.2f}  "
      f"{_wins}/{_total} wins")
print(f"  Avg (all windows)          {'':>14}  {_avg_ols_all:>10.2f}  {_avg_naive_all:>11.2f}")
print()
if _pct_wins >= 78:
    _verdict = "OLS beats naive CONSISTENTLY across windows — forecast quality is stable."
elif _pct_wins >= 50:
    _verdict = ("OLS beats naive in most windows but not all — "
                "performance is broadly stable with occasional harder periods.")
else:
    _verdict = "OLS does NOT reliably beat naive — model adds limited value over a simple lag."
print(f"→ {_verdict}")
print()
print("Note: Window 2 (Dec-19 → Jan-17) spans the New Year holiday cluster and "
      "produces extreme MAPE for both methods — this is expected and excluded from averages.")

# ── Line chart: per-window MAPE (only non-spike windows plotted cleanly) ────────
# Plot all windows but visually flag the holiday-spike window
fig_backtest, ax_bt = plt.subplots(figsize=(11, 5))
fig_backtest.patch.set_facecolor('#1D1D20')
ax_bt.set_facecolor('#1D1D20')

_x      = bt_results['window'].values
_labels = [r['eval_start'].strftime('%b %d') for _, r in bt_results.iterrows()]

# Exclude the holiday-spike window from the main lines so the Y-axis stays readable;
# draw it separately as a muted marker with annotation
_mask_ok    = ~bt_results['holiday_spike'].values
_mask_spike = bt_results['holiday_spike'].values

ax_bt.plot(_x[_mask_ok], bt_results['ols_mape'].values[_mask_ok],
           color='#FFB482', lw=2.2, marker='o', markersize=7, label='OLS MAPE %')
ax_bt.plot(_x[_mask_ok], bt_results['naive_mape'].values[_mask_ok],
           color='#8DE5A1', lw=2.2, marker='s', markersize=7, linestyle='--',
           label='Seasonal Naive MAPE %')

# Connect gap around spike window with dashed line
_idx_spike = np.where(_mask_spike)[0]
if len(_idx_spike):
    _i = _idx_spike[0]
    if _i > 0 and _i < len(_x) - 1:
        for _col, _col_key in [('#FFB482', 'ols_mape'), ('#8DE5A1', 'naive_mape')]:
            ax_bt.plot([_x[_i-1], _x[_i+1]],
                       [bt_results[_col_key].iloc[_i-1], bt_results[_col_key].iloc[_i+1]],
                       color=_col, lw=1.0, linestyle=':', alpha=0.4)
    # Mark the spike point with muted markers
    ax_bt.plot(_x[_mask_spike], bt_results['ols_mape'].values[_mask_spike],
               color='#FFB482', marker='x', markersize=9, linestyle='None', alpha=0.45)
    ax_bt.plot(_x[_mask_spike], bt_results['naive_mape'].values[_mask_spike],
               color='#8DE5A1', marker='x', markersize=9, linestyle='None', alpha=0.45)
    ax_bt.annotate('NY holiday\n(excluded from avg)',
                   xy=(_x[_mask_spike][0], bt_results['naive_mape'].values[_mask_spike][0]),
                   xytext=(_x[_mask_spike][0] + 0.6,
                           bt_results['naive_mape'].values[_mask_spike][0] - 2),
                   color='#909094', fontsize=7.5,
                   arrowprops=dict(arrowstyle='->', color='#909094', lw=0.8))

# Shade windows where naive beats OLS (only non-spike)
for _, _r in bt_results[~bt_results['ols_wins'] & ~bt_results['holiday_spike']].iterrows():
    ax_bt.axvspan(_r['window'] - 0.4, _r['window'] + 0.4,
                  color='#FF9F9B', alpha=0.15, label='_nolegend_')

# Average reference lines (clean windows only)
ax_bt.axhline(_avg_ols,   color='#FFB482', lw=0.9, linestyle=':', alpha=0.6)
ax_bt.axhline(_avg_naive, color='#8DE5A1', lw=0.9, linestyle=':', alpha=0.6)
ax_bt.annotate(f'avg {_avg_ols:.1f}%', xy=(0.01, _avg_ols), xycoords=('axes fraction', 'data'),
               color='#FFB482', fontsize=8, va='bottom')
ax_bt.annotate(f'avg {_avg_naive:.1f}%', xy=(0.01, _avg_naive), xycoords=('axes fraction', 'data'),
               color='#8DE5A1', fontsize=8, va='top')

ax_bt.set_xticks(_x)
ax_bt.set_xticklabels(_labels, rotation=30, ha='right', color='#fbfbff', fontsize=8)
ax_bt.tick_params(axis='y', colors='#fbfbff')
ax_bt.tick_params(axis='x', colors='#fbfbff')
_ymax = max(_bt_clean['naive_mape'].max(), _bt_clean['ols_mape'].max()) + 4
_yticks = list(range(0, int(_ymax) + 2, 2))
ax_bt.set_yticks(_yticks)
ax_bt.set_yticklabels([f'{v}%' for v in _yticks], color='#fbfbff', fontsize=8)
ax_bt.set_ylim(0, _ymax)
ax_bt.set_xlabel('Evaluation window start', color='#909094', fontsize=9)
ax_bt.set_ylabel('MAPE %', color='#909094', fontsize=9)
ax_bt.set_title(
    f'Rolling-origin backtest — OLS vs Seasonal Naive  ({N_WINDOWS} × {WINDOW_DAYS}-day windows)',
    color='#fbfbff', fontsize=11, fontweight='bold'
)
ax_bt.legend(facecolor='#2a2a2e', edgecolor='#555', labelcolor='#fbfbff', fontsize=9)
ax_bt.spines[['top', 'right']].set_visible(False)
ax_bt.spines[['left', 'bottom']].set_color('#444')
ax_bt.grid(axis='y', color='#333', linewidth=0.5, linestyle='--')

plt.tight_layout()
plt.close('all')
