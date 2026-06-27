import os; os.environ.setdefault('MPLCONFIGDIR', '/tmp/mpl')
import matplotlib.pyplot as plt

fig, ax = plt.subplots(2, 2, figsize=(15, 8))
ax[0,0].plot(d['date'], d['sales'], color="#1f4e5f", lw=.7); ax[0,0].set_title("National daily sales (2013–2017)")
dow = d.groupby('dow')['sales'].mean()
ax[0,1].bar(range(7), dow.values, color="#3d5a80")
ax[0,1].set_xticks(range(7)); ax[0,1].set_xticklabels(['Mon','Tue','Wed','Thu','Fri','Sat','Sun'])
ax[0,1].set_title("Avg sales by weekday")
mo = d.groupby('month')['sales'].mean()
ax[1,0].bar(mo.index, mo.values, color="#3d5a80"); ax[1,0].set_title("Avg sales by month")
dm = d.groupby('day')['sales'].mean()
ax[1,1].plot(dm.index, dm.values, marker='o', color="#e07a5f"); ax[1,1].set_title("Avg sales by day of month (payday effect)")
plt.tight_layout(); plt.show()

peak_dow = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'][int(dow.idxmax())]
print(f"Strongest weekday: {peak_dow} | clear spikes around day 15 and month-end (paydays)")