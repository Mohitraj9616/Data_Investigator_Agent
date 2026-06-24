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
    

