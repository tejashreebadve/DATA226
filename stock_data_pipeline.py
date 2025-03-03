from airflow import DAG
from airflow.models import Variable
from airflow.decorators import task
from airflow.providers.snowflake.hooks.snowflake import SnowflakeHook
from datetime import datetime, timedelta
import requests
import snowflake.connector

# Define constants
SNOWFLAKE_CONN_ID = "snowflake_conn"
ALPHA_VANTAGE_API_KEY = Variable.get("Alpha_vantage_api_key")
SYMBOL = "IBM"  # Example stock symbol

# Function to get Snowflake connection using SnowflakeHook
def get_snowflake_cursor():
    hook = SnowflakeHook(snowflake_conn_id=SNOWFLAKE_CONN_ID)
    conn = hook.get_conn()

    cursor=conn.cursor()
    cursor.execute("USE WAREHOUSE compute_wh")
    cursor.execute("USE DATABASE dev") 
    cursor.execute("USE SCHEMA raw")

    return conn.cursor()



# Task to extract data from Alpha Vantage API
@task
def extract_data():
    url = f"https://www.alphavantage.co/query?function=TIME_SERIES_DAILY&symbol={SYMBOL}&apikey={ALPHA_VANTAGE_API_KEY}"
    response = requests.get(url)
    if response.status_code != 200:
        raise ValueError(f"Failed to fetch data: {response.text}")
    data = response.json().get("Time Series (Daily)", {})
    return list(data.items())  # Convert to list of tuples for easier processing

# Task to transform raw API data into database-ready format
@task
def transform_data(raw_data):
    records = []
    for date_str, daily_info in raw_data:
        try:
            date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
            record = (
                SYMBOL,
                float(daily_info["1. open"]),
                float(daily_info["2. high"]),
                float(daily_info["3. low"]),
                float(daily_info["4. close"]),
                int(daily_info["5. volume"]),
                date_obj
            )
            records.append(record)
        except Exception as e:
            print(f"Skipping invalid entry {date_str}: {str(e)}")
    return records

# Task to load transformed data into Snowflake
@task
def load_data(records):
    target_table = "dev.raw.stock_price_tbl"
    cursor = get_snowflake_cursor()
    try:
        cursor.execute("BEGIN")
        cursor.execute(f"DELETE FROM {target_table}")  # Delete all rows
        cursor.executemany(
            f"INSERT INTO {target_table} (symbol, open, high, low, close, volume, date) VALUES (%s, %s, %s, %s, %s, %s, %s)",
            records
        )
        cursor.execute("COMMIT")
        print(f"Loaded {len(records)} records into {target_table}")
    except Exception as e:
        cursor.execute("ROLLBACK")
        raise RuntimeError(f"Load failed: {str(e)}")
    finally:
        cursor.close()


with DAG(
    dag_id='stock_data_pipeline',
    start_date=datetime(2025, 3, 1),
    catchup=False,
    schedule='30 17 * * *',
    tags=['ETL', 'Snowflake']
) as dag:
    raw_data = extract_data()
    transformed_data = transform_data(raw_data)
    load_data(transformed_data)

    
