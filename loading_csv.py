import pandas as pd
from sqlalchemy import create_engine
import os
from dotenv import load_dotenv


load_dotenv()
engine = create_engine(os.environ["DATABASE_URL"])
DATA_DIR = "files"
for table in ["dim_date", "dim_customers", "dim_products", "dim_sellers", "fact_sales"]:
    path = os.path.join(DATA_DIR,f"{table}.csv")
    df = pd.read_csv(path)
    df.to_sql(table,engine,if_exists="replace",index=False)
    print(table,"loaded: into Flipkart_ecom database ",f"dataframe rows {len(df)}")
    # path = os.path.join(DATA_DIR, f"{table}.csv")
    # df = pd.read_csv(path)
    # # df = pd.read_csv(f"files/{table}.csv")
    # df.to_sql(table, engine, if_exists="replace", index=False)
    # print(table, "loaded:", len(df), "rows")
