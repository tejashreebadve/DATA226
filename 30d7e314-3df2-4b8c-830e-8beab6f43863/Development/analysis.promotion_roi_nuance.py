import os; os.environ.setdefault('MPLCONFIGDIR', '/tmp/mpl')
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

# ── Build family-level promo metrics ──────────────────────────────────────────
_tr = train.copy()
_tr['date'] = pd.to_datetime(_tr['date'])
_tr['_promo_flag'] = _tr['onpromotion'] > 0

_grp = (
    _tr.groupby(['family', '_promo_flag'])['sales']
       .mean()
       .unstack()
)
_grp.columns = ['avg_off', 'avg_on']
_grp = _grp.dropna(subset=['avg_off', 'avg_on'])

_grp['uplift_pct'] = (_grp['avg_on'] - _grp['avg_off']) / _grp['avg_off'].replace(0, np.nan) * 100

_promo_freq = (
    _tr.groupby('family')['_promo_flag'].mean().rename('promo_freq')
)
_grp = _grp.join(_promo_freq)
_grp['abs_incremental'] = (_grp['avg_on'] - _grp['avg_off']) * _grp['promo_freq']

# ── Quadrant classification ────────────────────────────────────────────────────
_uplift_med = _grp['uplift_pct'].median()
_abs_med    = _grp['abs_incremental'].median()

def _quadrant(row):
    hi_pct = row['uplift_pct'] > _uplift_med
    hi_abs = row['abs_incremental'] > _abs_med
    if hi_pct and hi_abs:
        return 'High % + High volume  ← Promote'
    elif hi_pct and not hi_abs:
        return 'High % + Low volume   ← Niche'
    elif not hi_pct and hi_abs:
        return 'Low % + High volume   ← Volume driver'
    else:
        return 'Low % + Low volume    ← Skip'

_grp['quadrant'] = _grp.apply(_quadrant, axis=1)
_roi = _grp.reset_index().sort_values('abs_incremental', ascending=False)

# ── Print table ────────────────────────────────────────────────────────────────
print(f"Promotion ROI nuance  |  All {len(_roi)} product families")
print(f"Medians:  uplift% = {_uplift_med:.1f}%  |  abs incremental = {_abs_med:.1f} units/day")
print()
print(f"{'Family':<35}  {'Uplift %':>9}  {'Abs Incr':>10}  {'Promo freq':>11}  Quadrant")
print("─" * 100)
for _, _r in _roi.iterrows():
    print(f"{_r['family']:<35}  {_r['uplift_pct']:>8.1f}%  "
          f"{_r['abs_incremental']:>10.1f}  {_r['promo_freq']:>10.1%}  {_r['quadrant']}")

# ── Summary ────────────────────────────────────────────────────────────────────
print()
_promote  = _roi[_roi['quadrant'].str.startswith('High % + High')]
_niche    = _roi[_roi['quadrant'].str.startswith('High % + Low')]
_volume   = _roi[_roi['quadrant'].str.startswith('Low % + High')]
_skip     = _roi[_roi['quadrant'].str.startswith('Low % + Low')]

print(f"✅ Worth promoting (high % uplift + high absolute volume) [{len(_promote)}]:")
for _, _r in _promote.iterrows():
    print(f"   {_r['family']:35}  +{_r['uplift_pct']:.0f}% uplift, {_r['abs_incremental']:.0f} incremental units/day")

print(f"\n📦 Volume drivers — promos move real units even if % gain is modest [{len(_volume)}]:")
for _, _r in _volume.iterrows():
    print(f"   {_r['family']:35}  +{_r['uplift_pct']:.0f}% uplift, {_r['abs_incremental']:.0f} incremental units/day")

print(f"\n🎯 Niche — high % uplift but tiny absolute volume [{len(_niche)}]:")
for _, _r in _niche.iterrows():
    print(f"   {_r['family']:35}  +{_r['uplift_pct']:.0f}% uplift, {_r['abs_incremental']:.1f} incremental units/day")

print(f"\n🚫 Skip — low % uplift and low absolute volume [{len(_skip)}]:")
for _, _r in _skip.iterrows():
    print(f"   {_r['family']:35}  +{_r['uplift_pct']:.0f}% uplift, {_r['abs_incremental']:.1f} incremental units/day")

# ── Chart constants ────────────────────────────────────────────────────────────
_X_CAP     = 350.0          # clip x-axis here; outliers beyond get a note
_clipped   = _roi[_roi['uplift_pct'] > _X_CAP]   # families off the right edge
_in_view   = _roi[_roi['uplift_pct'] <= _X_CAP].copy()

# Clamp plotted x to cap (some families may sit exactly at cap due to rounding)
_in_view['_x_plot'] = _in_view['uplift_pct'].clip(upper=_X_CAP)

# Families to label: top 8 by abs_incremental (from full list) that are in view,
# plus the single highest-uplift outlier from the clipped set (if any).
_top8_names = set(_roi.nlargest(8, 'abs_incremental')['family'])
_extreme_outlier = (
    _clipped.nlargest(1, 'uplift_pct') if len(_clipped) > 0 else pd.DataFrame()
)

_quad_colors = {
    'High % + High volume  ← Promote':       '#8DE5A1',
    'High % + Low volume   ← Niche':         '#D0BBFF',
    'Low % + High volume   ← Volume driver': '#FFB482',
    'Low % + Low volume    ← Skip':          '#909094',
}

fig_promo_roi, ax_roi = plt.subplots(figsize=(13, 7.5))
fig_promo_roi.patch.set_facecolor('#1D1D20')
ax_roi.set_facecolor('#1D1D20')

# ── Highlight Promote quadrant background ──────────────────────────────────────
_y_top = _roi['abs_incremental'].max() * 1.25
ax_roi.fill_betweenx(
    [_abs_med, _y_top], _uplift_med, _X_CAP,
    color='#8DE5A1', alpha=0.06, zorder=1
)
# Bright border on the Promote quadrant
ax_roi.plot([_uplift_med, _X_CAP], [_abs_med, _abs_med],
            color='#8DE5A1', lw=1.2, alpha=0.45, zorder=2)
ax_roi.plot([_uplift_med, _uplift_med], [_abs_med, _y_top],
            color='#8DE5A1', lw=1.2, alpha=0.45, zorder=2)

# ── Scatter points ──────────────────────────────────────────────────────────────
for _q, _color in _quad_colors.items():
    _sub = _in_view[_in_view['quadrant'] == _q]
    ax_roi.scatter(
        _sub['_x_plot'], _sub['abs_incremental'],
        color=_color, s=95, alpha=0.92, edgecolors='#1D1D20', linewidth=0.6,
        label=_q.split('←')[1].strip() if '←' in _q else _q, zorder=4
    )

# ── Labels: top-8 by abs volume (only those in view) ───────────────────────────
_labeled = set()
for _, _r in _in_view.iterrows():
    if _r['family'] not in _top8_names:
        continue
    _labeled.add(_r['family'])
    _x, _y = _r['_x_plot'], _r['abs_incremental']
    _fam_short = (_r['family'][:22] + '…') if len(_r['family']) > 23 else _r['family']
    # Nudge labels away from the median lines
    _xoff = 8 if _x > _uplift_med else -8
    _yoff = 5 if _y > _abs_med else -10
    _ha   = 'left' if _xoff > 0 else 'right'
    ax_roi.annotate(
        _fam_short, (_x, _y),
        xytext=(_xoff, _yoff), textcoords='offset points',
        fontsize=7.5, color='#fbfbff', alpha=0.95, ha=_ha,
        arrowprops=dict(arrowstyle='-', color='#666', lw=0.6),
    )

# ── Median reference lines (draw after fill so they're on top) ─────────────────
ax_roi.axvline(_uplift_med, color='#555', lw=1.0, linestyle='--', zorder=3)
ax_roi.axhline(_abs_med,    color='#555', lw=1.0, linestyle='--', zorder=3)

# ── Quadrant watermark labels ──────────────────────────────────────────────────
_q_label_kw = dict(fontsize=8.5, alpha=0.45, style='italic',
                   bbox=dict(boxstyle='round,pad=0.2', facecolor='#1D1D20', alpha=0.0))

_y_max_plot = _y_top
_x_lo       = _uplift_med * 0.35
_x_hi       = _uplift_med + (_X_CAP - _uplift_med) * 0.55

ax_roi.text(_x_hi, _abs_med * 0.25, 'Volume driver', color='#FFB482', ha='center', va='center', **_q_label_kw)
ax_roi.text(_x_lo, _y_max_plot * 0.75, 'Niche',        color='#D0BBFF', ha='center', va='center', **_q_label_kw)
ax_roi.text(_x_hi, _y_max_plot * 0.75, '★ Promote',    color='#8DE5A1', ha='center', va='center',
            fontsize=9.5, fontweight='bold', alpha=0.75,
            bbox=dict(boxstyle='round,pad=0.3', facecolor='#1D1D20', alpha=0.0))
ax_roi.text(_x_lo, _abs_med * 0.25, 'Skip',           color='#909094', ha='center', va='center', **_q_label_kw)

# ── Off-scale annotation (clipped outliers) ────────────────────────────────────
if len(_clipped) > 0:
    _n_clipped = len(_clipped)
    _names_str = ', '.join(_clipped.sort_values('uplift_pct', ascending=False)['family'].tolist())
    _note = (f"  ▶ {_n_clipped} famil{'y' if _n_clipped == 1 else 'ies'} off-scale (uplift > {_X_CAP:.0f}%):\n"
             f"     {_names_str}")
    ax_roi.text(
        0.99, 0.01, _note.strip(),
        transform=ax_roi.transAxes,
        fontsize=7, color='#D0BBFF', alpha=0.80,
        ha='right', va='bottom',
        bbox=dict(boxstyle='round,pad=0.4', facecolor='#2a2a2e', edgecolor='#444', alpha=0.85)
    )
    # Draw an arrow from the right edge indicating the off-scale family
    for _, _or in _clipped.iterrows():
        _y_ofs = _or['abs_incremental']
        ax_roi.annotate(
            '',
            xy=(_X_CAP, _y_ofs), xytext=(_X_CAP * 0.90, _y_ofs),
            arrowprops=dict(arrowstyle='->', color='#D0BBFF', lw=1.2),
            zorder=5
        )
        _fam_s = (_or['family'][:20] + '…') if len(_or['family']) > 21 else _or['family']
        ax_roi.text(
            _X_CAP * 0.89, _y_ofs, f"{_fam_s}  ({_or['uplift_pct']:.0f}%) →",
            fontsize=7, color='#D0BBFF', alpha=0.85,
            ha='right', va='center'
        )

# ── Axes, ticks, labels ───────────────────────────────────────────────────────
ax_roi.set_xlim(0, _X_CAP * 1.02)
ax_roi.set_ylim(bottom=0, top=_y_top)

_tick_vals = [0, 50, 100, 150, 200, 250, 300, 350]
ax_roi.set_xticks(_tick_vals)
ax_roi.set_xticklabels([f'{v}%' for v in _tick_vals], color='#fbfbff', fontsize=8)
ax_roi.tick_params(axis='y', colors='#fbfbff', labelsize=8)

ax_roi.set_xlabel('Uplift % (on-promo avg ÷ off-promo avg − 1)', color='#909094', fontsize=9)
ax_roi.set_ylabel('Absolute incremental units/day (uplift × promo frequency)', color='#909094', fontsize=9)
ax_roi.set_title(
    'Promotion ROI — uplift % vs absolute incremental volume\n'
    'Top-right (★ Promote) = highest business value; x-axis capped at 350% for readability',
    color='#fbfbff', fontsize=11, fontweight='bold'
)
ax_roi.legend(facecolor='#2a2a2e', edgecolor='#555', labelcolor='#fbfbff', fontsize=8,
              title='Quadrant', title_fontsize=8, loc='upper left')
ax_roi.spines[['top', 'right']].set_visible(False)
ax_roi.spines[['left', 'bottom']].set_color('#444')
ax_roi.grid(color='#2a2a2e', linewidth=0.5, zorder=0)

plt.tight_layout()
plt.close('all')
