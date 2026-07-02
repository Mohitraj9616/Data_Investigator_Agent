import os
import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

load_dotenv()


pg_engine = create_engine(os.environ["DATABASE_URL"],pool_pre_ping=True)


def run_sql_query(sql:str,max_rows:int = 200,timeout_seconds: int = 10)-> dict:
    """
    Executes a read-only SQL query and returns a structured result.
    The agent's loop should call this, then branch on result["status"].
    """
    try: 
        with pg_engine.connect() as conn:
            conn.execute(text(f"SET statement_timeout = {timeout_seconds * 1000}"))
            conn = conn.execution_options(stream_results=True)
            result = conn.execute(text(sql))
            rows = result.fetchmany(max_rows)  
            columns = list(result.keys())
            table = pd.DataFrame(rows,columns=columns)
            return {
                "status": "success",
                "columns": columns,
                "rows": [dict(zip(columns, row)) for row in rows],
                "row_count": len(rows),
            }

    except SQLAlchemyError as e:
        return {
            "status": "error",
            "error_message": str(e.orig) if hasattr(e, "orig") else str(e),
        }
    


def get_schema(table_name: str = None) -> dict:
    """
    Returns column names and types for one table, or all tables if no table_name given.
    Agent calls this after a column/table error before retrying SQL.
    """
    try:
        with pg_engine.connect() as conn:
            if table_name:
                result = conn.execute(text("""SELECT column_name, data_type 
                    FROM information_schema.columns
                    WHERE table_schema = 'public' AND table_name = :table
                    ORDER BY ordinal_position"""), {"table": table_name})
            else:
                result = conn.execute(text("""
                    SELECT table_name, column_name, data_type
                    FROM information_schema.columns
                    WHERE table_schema = 'public'
                    ORDER BY table_name, ordinal_position
                """))

            rows = result.fetchall()
            columns = list(result.keys())
            return {
                "status": 'success',
                "schema": [dict(zip(columns, row)) for row in rows]
            }

    except SQLAlchemyError as e:
        return {
            "status": "error",
            "error_message": str(e.orig) if hasattr(e, "orig") else str(e),
        }
                
        



if __name__ == "__main__":
    # test 1: specific table
    print(get_schema("dim_products"))

    # test 2: column error recovery simulation
    error_result = run_sql_query("SELECT festival_name FROM fact_sales LIMIT 5")
    print("Error result:", error_result)

    if error_result["status"] == "error":
        print("Column error detected — fetching schema to correct...")
        schema = get_schema("fact_sales")
        print("Real fact_sales columns:", 
              [col["column_name"] for col in schema["schema"]])

