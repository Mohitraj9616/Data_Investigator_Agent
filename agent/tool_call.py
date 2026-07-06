import re
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from db_checks.database_conn_check import run_sql_query,get_schema

def extract_table_from_sql(sql:str)->list[str]:
    """
    Deterministically extracts table names from SQL.
    Looks for any word following FROM or JOIN.
    Not using LLM for this — deterministic is safer for
    anything that controls what data the agent can see.
    """
    pattern = r'\b(?:from|join)\s+([a-zA-Z_][a-zA-Z0-9_]*)'
    tables = list(set(re.findall(pattern,sql,re.IGNORECASE)))

    return tables


def get_all_schemas(schema_cache: dict) -> tuple[dict, dict]:
    """Fetch schemas for all known tables in one go."""
    all_tables = ["fact_sales", "dim_products", "dim_customers", 
                  "dim_date", "dim_sellers"]
    return ensure_schemas_cached(all_tables, schema_cache)

def ensure_schemas_cached(tables: list, schema_cache: dict) -> tuple[dict, dict]:
    """
    Checks which tables are missing from cache, fetches only those.
    Returns updated cache + a dict of what was newly fetched
    (so the loop can tell the LLM exactly what it just learned).
    """
    newly_fetched = {}
    failed_tables = []
    
    for table in tables:
        if table not in schema_cache:
            result = get_schema(table)
            if result["status"] == "success":
                schema_cache[table] = result["schema"]
                newly_fetched[table] = result["schema"]
            else:
                failed_tables.append(table)
    
    # raise immediately if any schema fetch failed
    # don't let the loop continue with missing schema
    if failed_tables:
        raise ConnectionError(
            f"Database connection failed for tables: {failed_tables}. "
            f"Error: {result.get('error_message', 'unknown')}"
        )
    
    return schema_cache, newly_fetched


def format_schema_for_llm(schema_cache: dict) -> str:
    """
    Formats cached schemas into a readable string the LLM can
    parse easily in the next message. Flat and explicit beats
    nested JSON for schema context.
    """
    lines = []
    for table,columns in schema_cache.items():
        lines.append(f"Table: {table}")
        if isinstance(columns,list):
            for col in columns:
                lines.append(f"  -{col['column_name']}({col['data_type']})")
        lines.append("")

    return "\n".join(lines)



def check_sql_safety(sql: str) -> tuple[bool, str]:
    """
    Last line of defence before executing any SQL.
    The DB-level REVOKE handles most of this, but we check
    in Python too so the agent gets a clear error message
    rather than a cryptic Postgres permission denial.
    """
    sql_upper = sql.upper().strip()
    forbidden = ["INSERT", "UPDATE", "DELETE", "DROP", "TRUNCATE",
                 "ALTER", "CREATE", "GRANT", "REVOKE"]
    for keyword in forbidden:
        # word boundary check so SELECT doesn't match (edge case)
        if re.search(rf'\b{keyword}\b',sql_upper):
            return False,f"Forbidden keyword '{keyword}' detected in SQL."
    
    return True,"ok"

if __name__=="__main__":
     # 1. table extraction
    test_sql = """
        SELECT p.category, COUNT(*) 
        FROM fact_sales f 
        JOIN dim_products p ON f.product_id = p.product_id
        JOIN dim_date d ON f.date_id = d.date_id
        WHERE d.year = 2024
        GROUP BY p.category
    """
    tables = extract_table_from_sql(test_sql)
    print("Extracted tables:", tables)
    # should be: ['fact_sales', 'dim_products', 'dim_date']

    # 2. schema cache fetch
    cache = {}
    cache, fetched = ensure_schemas_cached(tables, cache)
    print("\nFetched schemas for:", list(fetched.keys()))
    print("Formatted for LLM:\n", format_schema_for_llm(cache))

    # 3. safety check
    print(check_sql_safety("SELECT * FROM fact_sales"))          # safe
    print(check_sql_safety("DROP TABLE fact_sales"))             # blocked
    print(check_sql_safety("DELETE FROM fact_sales WHERE 1=1"))  # blocked
        



    