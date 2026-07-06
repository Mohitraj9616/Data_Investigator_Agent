import os
from pathlib import Path
import pandas as pd
from sqlalchemy import create_engine, text

RDS_URL = "postgresql+psycopg2://postgres:Chrome12345@data-agent-db.cjese66iclir.ap-south-1.rds.amazonaws.com:5432/flipkart_ecom"

engine = create_engine(RDS_URL)

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "files"

tables = ["dim_date", "dim_customers", "dim_products", "dim_sellers", "fact_sales"]

for table in tables:
    df = pd.read_csv(DATA_DIR / f"{table}.csv")
    df.to_sql(table, engine, if_exists="replace", index=False)
    print(f"{table}: {len(df)} rows loaded")

# lock down permissions
with engine.connect() as conn:
    conn.execute(text("CREATE USER agent_user WITH PASSWORD 'agentpass123'"))
    conn.execute(text("GRANT SELECT ON ALL TABLES IN SCHEMA public TO agent_user"))
    conn.execute(text("REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON ALL TABLES IN SCHEMA public FROM agent_user"))
    conn.commit()
    print("agent_user created and permissions set")