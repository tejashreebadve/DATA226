import pandas as pd, numpy as np

train = pd.read_csv('train.csv', parse_dates=['date'])
test  = pd.read_csv('test.csv',  parse_dates=['date'])
oil   = pd.read_csv('oil.csv',   parse_dates=['date'])
hol   = pd.read_csv('holidays_events.csv', parse_dates=['date'])
txn   = pd.read_csv('transactions.csv', parse_dates=['date'])

# National daily sales + promo volume
d = train.groupby('date', as_index=False).agg(
        sales=('sales','sum'),
        onpromotion=('onpromotion','sum'))
t = txn.groupby('date', as_index=False)['transactions'].sum()
d = d.merge(t, on='date', how='left')

# OIL — fill weekend/holiday gaps so there are no NaNs
rng = pd.date_range(d['date'].min(), test['date'].max())
o = oil.set_index('date').reindex(rng).rename_axis('date')
o['dcoilwtico'] = o['dcoilwtico'].ffill().bfill()        # the fix
d = d.merge(o.reset_index(), on='date', how='left')

# HOLIDAYS — national days OFF only; exclude 'Work Day'/'Event' and transferred-away dates
hh = hol.copy()
hh['transferred'] = hh['transferred'].astype(str).str.lower().eq('true')
nat = set(hh[(hh['locale']=='National') &
             (hh['type'].isin(['Holiday','Additional','Bridge','Transfer'])) &  # NOT 'Work Day'/'Event'
             (~hh['transferred'])]['date'])
d['is_holiday'] = d['date'].isin(nat).astype(int)

# Calendar + event flags
d['dow']   = d['date'].dt.dayofweek
d['day']   = d['date'].dt.day
d['month'] = d['date'].dt.month
d['is_payday']     = ((d['day']==15) | d['date'].dt.is_month_end).astype(int)
d['is_earthquake'] = ((d['date']>='2016-04-16') & (d['date']<='2016-05-15')).astype(int)

# ---- validation ----
print("Shape:", d.shape)
print("Dates:", d['date'].min().date(), "→", d['date'].max().date())
print("Missing oil after fill:", int(d['dcoilwtico'].isna().sum()))   # must be 0
print("National holiday days:", int(d['is_holiday'].sum()))
print("2013-01-05 is_holiday (was wrongly True):",
      int(d.loc[d['date']=='2013-01-05','is_holiday'].iat[0]))         # must be 0
d.head()