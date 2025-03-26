from airflow.decorators import task
from airflow import DAG
from airflow.providers.snowflake.hooks.snowflake import SnowflakeHook
from datetime import datetime
import logging

def return_snowflake_conn():
    """Initialize Snowflake connection using Airflow Hook"""
    hook = SnowflakeHook(snowflake_conn_id='snowflake_conn')
    conn = hook.get_conn()
    return conn.cursor()

@task
def run_ctas(database, schema, table, select_sql, primary_key=None):
    """Create a new table using CTAS and perform primary key uniqueness check"""
    logging.info(f"Creating table {table} with SQL: {select_sql}")

    cur = return_snowflake_conn()

    try:
        # Step 1: Drop the existing table if it exists
        drop_table_sql = f"DROP TABLE IF EXISTS {database}.{schema}.{table};"
        logging.info(f"Executing SQL: {drop_table_sql}")
        cur.execute(drop_table_sql)

        # Step 2: Create the temporary table for the joined data
        sql = f"CREATE OR REPLACE TABLE {database}.{schema}.temp_{table} AS {select_sql}"
        logging.info(f"Executing SQL: {sql}")
        cur.execute(sql)

        # Step 3: Check for duplicates in the primary key column (if provided)
        if primary_key is not None:
            sql = f"""
              SELECT {primary_key}, COUNT(1) AS cnt 
              FROM {database}.{schema}.temp_{table}
              GROUP BY 1
              HAVING COUNT(1) > 1
              ORDER BY 2 DESC
              LIMIT 1"""
            logging.info(f"Checking for duplicates with SQL: {sql}")
            cur.execute(sql)
            result = cur.fetchone()
            if result and int(result[1]) > 1:
                raise Exception(f"Primary key uniqueness failed: {result}")

        # Step 4: Create the main table if it doesn't exist yet
        main_table_creation_sql = f"""
            CREATE TABLE IF NOT EXISTS {database}.{schema}.{table} AS
            SELECT * FROM {database}.{schema}.temp_{table} WHERE 1=0;"""
        logging.info(f"Creating main table with SQL: {main_table_creation_sql}")
        cur.execute(main_table_creation_sql)

        # Step 5: Swap the temp table with the main table
        swap_sql = f"""ALTER TABLE {database}.{schema}.{table} SWAP WITH {database}.{schema}.temp_{table};"""
        logging.info(f"Swapping tables with SQL: {swap_sql}")
        cur.execute(swap_sql)
    except Exception as e:
        logging.error(f"Error during CTAS execution: {e}")
        raise

with DAG(
    dag_id='BuildELT_CTAS',
    start_date=datetime(2024, 10, 2),
    catchup=False,
    tags=['ELT'],
    schedule='45 2 * * *'  # Run every day at 2:45 AM
) as dag:
    # Define parameters for the joined table creation
    database = "dev"
    schema = "analytics"
    table = "session_summary"  # The name of the joined table
    select_sql = """SELECT u.*, s.ts
    FROM dev.raw.user_session_channel u
    JOIN dev.raw.session_timestamp s ON u.sessionId = s.sessionId"""

    # Run the CTAS process for creating the joined table (session_summary)
    run_ctas(database, schema, table, select_sql, primary_key='sessionId')
