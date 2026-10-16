import pandas as pd
import clickhouse_connect

CH_HOST = 'clickhouse'
CH_PORT = 8123

df = pd.read_csv('/opt/airflow/data/uplift_predictions.csv')
print(f"Прочитано {len(df)} строк")

ch = clickhouse_connect.get_client(
    host=CH_HOST, port=CH_PORT,
    username='admin', password='admin123',
)

ch.command("DROP TABLE IF EXISTS uplift_predictions")
ch.command("""
CREATE TABLE uplift_predictions (
    age UInt8,
    income Float64,
    loyalty_days UInt16,
    prev_purchases UInt8,
    segment UInt8,
    uplift Float32,
    purchase UInt8,
    treatment UInt8,
    segment_true UInt8,
    targeted UInt8
)
ENGINE = MergeTree()
ORDER BY uplift
""")

ch.insert_df('uplift_predictions', df)
print(f"Загружено {len(df)} строк в uplift_predictions")
