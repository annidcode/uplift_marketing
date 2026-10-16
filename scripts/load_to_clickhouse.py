import pandas as pd
import clickhouse_connect

CH_HOST = 'clickhouse'
CH_PORT = 8123
CH_USER = 'admin'
CH_PASSWORD = 'admin123'

df = pd.read_csv('/opt/airflow/data/uplift_data.csv')
print(f"Прочитано {len(df)} строк")

ch = clickhouse_connect.get_client(
    host=CH_HOST, port=CH_PORT,
    username=CH_USER, password=CH_PASSWORD,
)

ch.command("DROP TABLE IF EXISTS uplift_users")
ch.command("""
CREATE TABLE uplift_users (
    user_id UInt32,
    segment UInt8,
    treatment UInt8,
    purchase UInt8,
    age UInt8,
    income Float64,
    loyalty_days UInt16,
    prev_purchases UInt8,
    base_prob Float32,
    final_prob Float32,
    effect Float32
)
ENGINE = MergeTree()
ORDER BY user_id
""")

ch.insert_df('uplift_users', df)
print(f"Загружено {len(df)} строк в uplift_users")
