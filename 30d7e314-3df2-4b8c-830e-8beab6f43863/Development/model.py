import os; os.environ.setdefault('MPLCONFIGDIR', '/tmp/mpl')
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

# ── 0. Data setup ──────────────────────────────────────────────────────────────
panel = d.copy()
panel = panel.sort_values('date').reset_index(drop=True)

# ── 1. Global scaling constants (computed on full panel) ───────────────────────
OIL_MEAN  = panel['dcoilwtico'].mean()
OIL_STD   = panel['dcoilwtico'].std()
PROMO_MAX = panel['onpromotion'].max()
T0        = panel['date'].min()
T_TOTAL   = (panel['date'].max() - T0).days

# ── 2. Log-sales + lag features ───────────────────────────────────────────────
panel['logsales'] = np.log1p(panel['sales'])
panel = panel.sort_values('date').reset_index(drop=True)

panel['lag7']  = panel['logsales'].shift(7)
# roll7: 7-day rolling mean, shifted 1 day so it only uses past data
panel['roll7'] = panel['logsales'].shift(1).rolling(7).mean()

# Drop first 7 rows that have no lag value
panel = panel.iloc[7:].reset_index(drop=True)

# ── 3. Diagnostic: raw holiday effect vs DOW-adjusted expectation ──────────────
# Used to verify sign direction before model fit.
_panel_diag = panel.copy()
_mean_by_dow = _panel_diag.groupby('dow')['logsales'].mean()
_panel_diag['dow_expected'] = _panel_diag['dow'].map(_mean_by_dow)
_panel_diag['hol_residual'] = _panel_diag['logsales'] - _panel_diag['dow_expected']
_hol_raw_mean    = _panel_diag.loc[_panel_diag['is_holiday']==1, 'logsales'].mean()
_nonhol_raw_mean = _panel_diag.loc[_panel_diag['is_holiday']==0, 'logsales'].mean()
_hol_dow_resid   = _panel_diag.loc[_panel_diag['is_holiday']==1, 'hol_residual'].mean()
print(f"Holiday diagnostic:")
print(f"  Raw mean logsales on holidays     : {_hol_raw_mean:.4f}")
print(f"  Raw mean logsales on non-holidays : {_nonhol_raw_mean:.4f}")
print(f"  DOW-adjusted holiday residual     : {_hol_dow_resid:.4f}  "
      f"({'negative → coefficient will be negative' if _hol_dow_resid < 0 else 'positive'})")

# ── 4. Feature function ────────────────────────────────────────────────────────
# include_lags=False → calendar-only features for the interpretable driver model
# include_lags=True  → full feature set for the forecast model
def features(fr, include_lags=True):
    """Return feature matrix X.
    fr must contain: date, onpromotion, dcoilwtico
    and (when include_lags=True): lag7, roll7
    """
    n     = len(fr)
    dates = pd.to_datetime(fr['date'])
    day_num = (dates - T0).dt.days.values

    # 1. intercept
    intercept = np.ones(n)

    # 2. trend = days-since-start / total-days
    trend = day_num / T_TOTAL

    # 3. weekday dummies dow 1..6  (0=Mon … 6=Sun in pandas)
    dow = dates.dt.dayofweek.values
    dow_dummies = (dow[:, None] == np.arange(1, 7)).astype(float)   # (n, 6)

    # 4. Fourier pairs k=1..3, period 365.25
    t_norm  = day_num / 365.25
    fourier = np.column_stack([
        f(2 * np.pi * k * t_norm)
        for k in range(1, 4)
        for f in (np.sin, np.cos)
    ])  # (n, 6)

    # 5. is_holiday
    is_holiday = dates.isin(nat).astype(float).values

    # 6. is_monthstart (day <= 2)
    is_monthstart = (dates.dt.day <= 2).astype(float).values

    # 7. is_payday (day 14–16 or month-end)
    dom          = dates.dt.day.values
    is_month_end = dates.dt.is_month_end.values
    is_payday    = (((dom >= 14) & (dom <= 16)) | is_month_end).astype(float)

    # 8. is_earthquake
    is_earthquake = ((dates >= '2016-04-16') & (dates <= '2016-05-15')).astype(float).values

    # 9. promo = onpromotion / max (from training)
    promo = (fr['onpromotion'].values / PROMO_MAX).astype(float)

    # 10. oil = standardized
    oil_z = ((fr['dcoilwtico'].values - OIL_MEAN) / OIL_STD).astype(float)

    calendar_cols = np.column_stack([
        intercept, trend,
        dow_dummies,           # 6 cols
        fourier,               # 6 cols
        is_holiday, is_monthstart, is_payday, is_earthquake,
        promo, oil_z
    ])

    if not include_lags:
        return calendar_cols

    # Lag columns are excluded from the driver model so that calendar effects
    # are not absorbed / shrunk by the highly correlated lag terms.
    lag7_col  = fr['lag7'].values.reshape(-1, 1).astype(float)
    roll7_col = fr['roll7'].values.reshape(-1, 1).astype(float)
    return np.column_stack([calendar_cols, lag7_col, roll7_col])

CALENDAR_NAMES = (
    ['intercept', 'trend']
    + [f'dow_{k}' for k in range(1, 7)]
    + [f'fourier_sin{k}' if i % 2 == 0 else f'fourier_cos{k}'
       for k in range(1, 4) for i in range(2)]
    + ['is_holiday', 'is_monthstart', 'is_payday', 'is_earthquake',
       'promo', 'oil']
)
FORECAST_NAMES = CALENDAR_NAMES + ['lag7', 'roll7']

# ── 5. Target ──────────────────────────────────────────────────────────────────
panel['y'] = panel['logsales']      # already log1p(sales)

# ── 6. Time-based split: hold out last 60 days ────────────────────────────────
split_date = panel['date'].max() - pd.Timedelta(days=59)
train_mask = panel['date'] < split_date
train_df   = panel[train_mask].copy()
valid_df   = panel[~train_mask].copy()

X_tr_full = features(train_df, include_lags=True)
X_va_full = features(valid_df, include_lags=True)
y_tr = train_df['y'].values
y_va = valid_df['y'].values

# ── 7. Forecast model (with lags) ─────────────────────────────────────────────
coefs_fcast, _, _, _ = np.linalg.lstsq(X_tr_full, y_tr, rcond=None)

y_hat_va_log     = X_va_full @ coefs_fcast
valid_df = valid_df.copy()
valid_df['fitted'] = np.expm1(y_hat_va_log)

# ── 8. Seasonal-naive baseline (sales lagged 7 days) ──────────────────────────
_panel_idx = panel.set_index('date')['sales']
valid_df['naive'] = valid_df['date'].map(
    lambda _d: _panel_idx.get(_d - pd.Timedelta(days=7), np.nan)
)

# ── 9. Metrics ─────────────────────────────────────────────────────────────────
def mape(actual, pred):
    _m = actual > 0
    return np.mean(np.abs((actual[_m] - pred[_m]) / actual[_m])) * 100

def rmse(actual, pred):
    return np.sqrt(np.mean((actual - pred) ** 2))

va_sales  = valid_df['sales'].values
va_fit    = valid_df['fitted'].values
va_naive  = valid_df['naive'].values
_nmask    = ~np.isnan(va_naive)

mape_model = mape(va_sales, va_fit)
rmse_model = rmse(va_sales, va_fit)
mape_naive = mape(va_sales[_nmask], va_naive[_nmask])
rmse_naive = rmse(va_sales[_nmask], va_naive[_nmask])

uplift_mape = (mape_naive - mape_model) / mape_naive * 100
uplift_rmse = (rmse_naive - rmse_model) / rmse_naive * 100

res = pd.DataFrame({
    'model':    ['OLS (w/ lags)', 'Seasonal Naive (lag-7)'],
    'MAPE_%':   [round(mape_model, 3), round(mape_naive, 3)],
    'RMSE':     [round(rmse_model, 1), round(rmse_naive, 1)],
    'uplift_%': [round(uplift_mape, 2), 0.0]
})

best_model = 'OLS (w/ lags)' if mape_model < mape_naive else 'Seasonal Naive'
best_mape  = min(mape_model, mape_naive)

print("\n── Validation results ─────────────────────────────────")
print(res.to_string(index=False))
print(f"\nbest_model = {best_model}  |  best_mape = {best_mape:.3f}%")

# ── 10. Driver model (calendar-only, no lags) ──────────────────────────────────
# Fit on FULL dataset so all holiday obs (including Jan 1 2013) contribute.
# Lags are excluded so the calendar coefficients capture the true causal effects
# without being absorbed by the highly correlated lag terms.
X_cal_all  = features(panel, include_lags=False)
y_all_cal  = panel['y'].values
coefs_drv, _, _, _ = np.linalg.lstsq(X_cal_all, y_all_cal, rcond=None)

_idx = {nm: i for i, nm in enumerate(CALENDAR_NAMES)}
drivers = {
    'is_holiday':    round(np.expm1(coefs_drv[_idx['is_holiday']])    * 100, 2),
    'is_monthstart': round(np.expm1(coefs_drv[_idx['is_monthstart']]) * 100, 2),
    'is_payday':     round(np.expm1(coefs_drv[_idx['is_payday']])     * 100, 2),
    'is_earthquake': round(np.expm1(coefs_drv[_idx['is_earthquake']]) * 100, 2),
}
promo_coef = round(float(coefs_drv[_idx['promo']]), 6)
oil_coef   = round(float(coefs_drv[_idx['oil']]),   6)

print("\n── Driver effects (calendar-only model, % change in sales) ──")
for k, v in drivers.items():
    _sign = '+' if v >= 0 else ''
    print(f"  {k:20s}  {_sign}{v:.2f}%")
print(f"  promo_coef (log-scale) :  {promo_coef}")
print(f"  oil_coef   (log-scale) :  {oil_coef}")

# ── 11. Refit forecast model on ALL data ──────────────────────────────────────
X_all_full = features(panel, include_lags=True)
y_all      = panel['y'].values
coefs_all, _, _, _ = np.linalg.lstsq(X_all_full, y_all, rcond=None)

# ── 12. Recursive 16-day forward forecast ─────────────────────────────────────
test_raw = pd.read_csv('test.csv', parse_dates=['date'])
fut = test_raw.groupby('date', as_index=False)['onpromotion'].sum()
fut = fut.sort_values('date').reset_index(drop=True)

# Merge oil (ffill/bfill)
oil_raw  = pd.read_csv('oil.csv', parse_dates=['date'])
_full_rng = pd.date_range(panel['date'].min(), fut['date'].max())
oil_full  = (oil_raw.set_index('date')
                    .reindex(_full_rng)
                    .rename_axis('date')['dcoilwtico']
                    .ffill().bfill()
                    .reset_index())
fut = fut.merge(oil_full, on='date', how='left')

# Running history: logsales series extended with predictions
_history = panel.set_index('date')['logsales'].copy()

fut['forecast'] = np.nan
for _i, _row in fut.iterrows():
    _dt = _row['date']

    # lag7 and roll7 from running history (never leaks future data)
    _lag7  = _history.get(_dt - pd.Timedelta(days=7), np.nan)
    _past7 = [_history.get(_dt - pd.Timedelta(days=j), np.nan) for j in range(1, 8)]
    _roll7 = np.nanmean(_past7) if not all(np.isnan(_past7)) else np.nan

    _row_df = pd.DataFrame({
        'date':          [_dt],
        'onpromotion':   [_row['onpromotion']],
        'dcoilwtico':    [_row['dcoilwtico']],
        'lag7':          [_lag7],
        'roll7':         [_roll7],
    })
    _X = features(_row_df, include_lags=True)
    _yhat_log = float(_X @ coefs_all)
    _yhat     = np.expm1(_yhat_log)
    fut.at[_i, 'forecast'] = _yhat

    # Append prediction to running history for the next step
    _history[_dt] = _yhat_log

proj_sum = float(fut['forecast'].sum())

print(f"\n── 16-day test window forecast  (proj_sum = {proj_sum:,.0f}) ──")
print(fut[['date', 'onpromotion', 'forecast']].to_string(index=False))

# ── 13. Plot: held-out actual vs fitted + forward forecast ─────────────────────
panel['fitted_all'] = np.expm1(X_all_full @ coefs_all)

fig_model, ax_model = plt.subplots(figsize=(14, 5))
ax_model.set_facecolor('#1D1D20')
fig_model.patch.set_facecolor('#1D1D20')

ax_model.plot(panel.loc[train_mask, 'date'], panel.loc[train_mask, 'fitted_all'],
        color='#909094', lw=0.8, alpha=0.5, label='Train fitted')
ax_model.plot(valid_df['date'], valid_df['sales'],
        color='#A1C9F4', lw=1.8, label='Held-out actual')
ax_model.plot(valid_df['date'], valid_df['fitted'],
        color='#FFB482', lw=1.8, linestyle='--', label='OLS fitted (w/ lags)')
ax_model.plot(valid_df['date'], valid_df['naive'],
        color='#8DE5A1', lw=1.2, linestyle=':', alpha=0.8, label='Naive (lag-7)')
ax_model.plot(fut['date'], fut['forecast'],
        color='#ffd400', lw=2.2, label='Forecast (test window)')

ax_model.axvline(split_date, color='#FF9F9B', lw=1.2, linestyle='--',
           alpha=0.8, label='Train/valid split')
ax_model.axvline(panel['date'].max(), color='#D0BBFF', lw=1.2, linestyle='--',
           alpha=0.8, label='History end')

ax_model.xaxis.set_major_formatter(mdates.DateFormatter('%b %Y'))
ax_model.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
plt.setp(ax_model.get_xticklabels(), rotation=30, ha='right', color='#fbfbff', fontsize=8)
_yticks = [int(v) for v in ax_model.get_yticks() if v >= 0]
ax_model.set_yticks(_yticks)
ax_model.set_yticklabels([f'{int(v/1e3)}K' for v in _yticks], color='#fbfbff', fontsize=8)
ax_model.tick_params(axis='x', colors='#fbfbff')
ax_model.set_xlabel('Date', color='#909094', fontsize=9)
ax_model.set_ylabel('National Sales', color='#909094', fontsize=9)
ax_model.set_title('OLS Model (w/ Lags) — Held-out Actual vs Fitted + Forward Forecast',
             color='#fbfbff', fontsize=11, pad=10)
ax_model.spines[['top', 'right']].set_visible(False)
ax_model.spines[['left', 'bottom']].set_color('#909094')
ax_model.legend(fontsize=7, facecolor='#2a2a2e', edgecolor='#909094',
          labelcolor='#fbfbff', loc='upper left')
plt.tight_layout()
plt.close('all')
