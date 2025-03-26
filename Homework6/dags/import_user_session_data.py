from airflow import DAG
from airflow.providers.snowflake.operators.snowflake import SnowflakeOperator
from datetime import datetime

# Snowflake connection details
SNOWFLAKE_STAGE = 'dev.raw.blob_stage'
SNOWFLAKE_TABLE_USER_SESSION_CHANNEL = 'dev.raw.user_session_channel'
SNOWFLAKE_TABLE_SESSION_TIMESTAMP = 'dev.raw.session_timestamp'

# Define the DAG
with DAG(
    dag_id='import_user_session_data_from_s3',
    start_date=datetime(2025, 2, 21),
    schedule_interval='@daily',  # Set your desired schedule interval
    catchup=False,
    tags=['ETL', 'Snowflake', 'S3', 'Session'],
) as dag:

    # Step 1: Create the Snowflake stage if it doesn't exist
    create_stage_sql = """
    CREATE OR REPLACE STAGE dev.raw.blob_stage
    URL = 's3://s3-geospatial/readonly/'
    FILE_FORMAT = (TYPE = 'CSV', SKIP_HEADER = 1, FIELD_OPTIONALLY_ENCLOSED_BY = '"');
    """
    
    create_stage = SnowflakeOperator(
        task_id='create_stage',
        sql=create_stage_sql,
        snowflake_conn_id='snowflake_conn',  # Update with your connection ID
        autocommit=True,
        dag=dag
    )

    # Step 2: Copy data into the user_session_channel table
    copy_user_session_channel_sql = """
    COPY INTO dev.raw.user_session_channel
    FROM @dev.raw.blob_stage/user_session_channel.csv
    FILE_FORMAT = (TYPE = 'CSV', SKIP_HEADER = 1, FIELD_OPTIONALLY_ENCLOSED_BY = '"')
    ON_ERROR = 'CONTINUE';
    """

    copy_user_session_channel = SnowflakeOperator(
        task_id='copy_user_session_channel',
        sql=copy_user_session_channel_sql,
        snowflake_conn_id='snowflake_conn',  # Update with your connection ID
        autocommit=True,
        dag=dag
    )

    # Step 3: Copy data into the session_timestamp table
    copy_session_timestamp_sql = """
    COPY INTO dev.raw.session_timestamp
    FROM @dev.raw.blob_stage/session_timestamp.csv
    FILE_FORMAT = (TYPE = 'CSV', SKIP_HEADER = 1, FIELD_OPTIONALLY_ENCLOSED_BY = '"')
    ON_ERROR = 'CONTINUE';
    """

    copy_session_timestamp = SnowflakeOperator(
        task_id='copy_session_timestamp',
        sql=copy_session_timestamp_sql,
        snowflake_conn_id='snowflake_conn',  # Update with your connection ID
        autocommit=True,
        dag=dag
    )

    # Set task dependencies
    create_stage >> copy_user_session_channel >> copy_session_timestamp
