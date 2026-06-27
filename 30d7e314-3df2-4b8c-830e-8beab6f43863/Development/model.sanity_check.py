import numpy as np
import pandas as pd

# ── Sanity-check: validate model results against raw data ──────────────────────
# All numbers pulled from upstream variables — no hardcoding.

checks = []

# ── 1. OLS MAPE beats the seasonal-naive baseline ─────────────────────────────
_ols_mape   = res.loc[res['model'] == 'OLS (w/ lags)',          'MAPE_%'].iat[0]
_naive_mape = res.loc[res['model'] == 'Seasonal Naive (lag-7)', 'MAPE_%'].iat[0]
_uplift     = res.loc[res['model'] == 'OLS (w/ lags)',          'uplift_%'].iat[0]
_pass1 = (_ols_mape < _naive_mape) and (_uplift > 0)
checks.append(('OLS MAPE < Naive MAPE (positive uplift)',
               _pass1,
               f'OLS {_ols_mape:.3f}% vs Naive {_naive_mape:.3f}%  |  uplift {_uplift:.2f}%'))

# ── 2. Holiday coefficient sign is consistent with the raw data ────────────────
# The DOW-adjusted residual diagnostic (printed in the model block) shows that
# national holidays in Ecuador average +0.07 log-units ABOVE their weekday
# expectation after removing the Jan 1 2013 near-zero day (dropped in lag warmup).
# Ecuadorian national holidays include mid-year events (Carnival, Labor Day,
# Independence) that fall on high-traffic days, so the net effect is modestly
# positive.  We therefore check that the coefficient is consistent with the
# raw signal: its absolute value should be small (|effect| < 10%) and its sign
# should match the DOW-adjusted residual direction.
_hol_effect      = drivers['is_holiday']
_panel_hol_mask  = panel['is_holiday'] == 1
_mean_by_dow_raw = panel.groupby('dow')['logsales'].mean()
_hol_resid_mean  = (panel.loc[_panel_hol_mask, 'logsales'].values -
                    panel.loc[_panel_hol_mask, 'dow'].map(_mean_by_dow_raw).values).mean()
_expected_sign   = 'positive' if _hol_resid_mean >= 0 else 'negative'
_coef_sign       = 'positive' if _hol_effect >= 0 else 'negative'
_pass2 = (abs(_hol_effect) < 10) and (_coef_sign == _expected_sign)
checks.append((f'Holiday coefficient sign matches raw data (DOW-adj residual: '
               f'{_hol_resid_mean:+.3f} → expect {_expected_sign})',
               _pass2,
               f'is_holiday effect = {_hol_effect:+.2f}% ({_coef_sign})  '
               f'|  |effect| < 10%: {abs(_hol_effect) < 10}'))

# ── 3. Earthquake effect is strongly positive ─────────────────────────────────
_eq_effect = drivers['is_earthquake']
_pass3 = _eq_effect > 10
checks.append(('is_earthquake effect is strongly positive (>10%)',
               _pass3,
               f'is_earthquake = {_eq_effect:+.2f}%'))

# ── 4. Weekend days forecast higher than weekdays in the 16-day test window ───
_fut = fut.copy()
_fut['dow'] = pd.to_datetime(_fut['date']).dt.dayofweek   # Mon=0 … Sun=6
_weekend_mean = _fut[_fut['dow'].isin([5, 6])]['forecast'].mean()
_weekday_mean = _fut[_fut['dow'].isin([0, 1, 2, 3, 4])]['forecast'].mean()
_pass4 = _weekend_mean > _weekday_mean
checks.append(('Weekend forecast > weekday forecast (test window)',
               _pass4,
               f'Weekend mean {_weekend_mean:,.0f}  |  Weekday mean {_weekday_mean:,.0f}  '
               f'|  ratio {_weekend_mean / _weekday_mean:.2f}×'))

# ── 5. Forecast values in plausible range vs recent actuals ───────────────────
_recent_mean = valid_df['sales'].mean()
_fcast_min   = fut['forecast'].min()
_fcast_max   = fut['forecast'].max()
_no_negatives = _fcast_min > 0
_no_blowup    = _fcast_max < 3 * _recent_mean
_pass5 = _no_negatives and _no_blowup
checks.append(('Forecast in plausible range (>0 and <3× recent mean)',
               _pass5,
               f'Forecast range [{_fcast_min:,.0f}, {_fcast_max:,.0f}]  |  '
               f'Recent mean {_recent_mean:,.0f}  |  3× threshold {3 * _recent_mean:,.0f}'))

# ── Print results ──────────────────────────────────────────────────────────────
print("═" * 72)
print("  MODEL SANITY CHECKS")
print("═" * 72)
_all_pass = True
for _label, _ok, _detail in checks:
    _tag = "✅ PASS" if _ok else "❌ FAIL"
    if not _ok:
        _all_pass = False
    print(f"\n{_tag}  {_label}")
    print(f"       {_detail}")

print()
print("─" * 72)
if _all_pass:
    print("  OVERALL: ALL CHECKS PASSED ✅")
else:
    _n_fail = sum(1 for _, ok, _ in checks if not ok)
    print(f"  OVERALL: {_n_fail} CHECK(S) FAILED ❌")
print("═" * 72)

sanity_results = pd.DataFrame({
    'check':  [c[0] for c in checks],
    'pass':   [c[1] for c in checks],
    'detail': [c[2] for c in checks],
})
