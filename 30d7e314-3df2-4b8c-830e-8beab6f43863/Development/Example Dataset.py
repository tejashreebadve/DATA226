import pandas as pd

# Load all datasets
holidays_events = pd.read_csv('holidays_events.csv')
oil = pd.read_csv('oil.csv')
sample_submission = pd.read_csv('sample_submission.csv')
stores = pd.read_csv('stores.csv')
test = pd.read_csv('test.csv')
train = pd.read_csv('train.csv')
transactions = pd.read_csv('transactions.csv')

# Preview each dataset
datasets = {
    'holidays_events': holidays_events,
    'oil': oil,
    'sample_submission': sample_submission,
    'stores': stores,
    'test': test,
    'train': train,
    'transactions': transactions
}

for name, df in datasets.items():
    print(f"\n{'='*50}")
    print(f"Dataset: {name}")
    print(f"Shape: {df.shape}")
    print(f"Columns: {list(df.columns)}")
    print(df.head())