import os
import re
import json
import ast
from openai import OpenAI, APIError
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

SYSTEM_PROMPT = """You are a data analyst agent working on a Flipkart e-commerce 
database with these tables:
- fact_sales: order_item_id, customer_id, product_id, seller_id, date_id, 
  quantity, unit_mrp, discount_pct, unit_selling_price, line_total, 
  payment_method, order_status, promised_delivery_days, actual_delivery_days, 
  delivery_delay_flag, rating
- dim_products: product_id, product_name, category, sub_category, brand, mrp, 
  weight_kg, launch_date
- dim_customers: customer_id, customer_name, gender, age, city, state, 
  city_tier, signup_date, customer_segment
- dim_date: date_id, date, day_name, month, month_name, quarter, year, 
  is_weekend, is_festival_sale, festival_name, demand_multiplier
- dim_sellers: seller_id, seller_name, seller_city, seller_state, 
  is_flipkart_assured, seller_rating

Rules you must follow without exception:
1. ALWAYS call get_schema for any table before writing SQL against it
2. NEVER guess column names — only use columns confirmed from schema
3. On a column error, ALWAYS fetch schema again before retrying
4. On zero rows, run a broader exploratory query to check filter values
5. Only produce "answer" action when you have verified data in hand
6. In PostgreSQL, ALWAYS use single quotes for string values in WHERE clauses.
   NEVER use double quotes for string values — double quotes mean column/table 
   identifiers in PostgreSQL, not string literals.
   CORRECT:   WHERE order_status = 'Returned'
   INCORRECT: WHERE order_status = "Returned"
7. Your response must use double quotes for all JSON keys and string values.
   Never use single quotes in JSON output.
8. If the question clearly requires multiple tables, use action "get_schema_all" 
   instead of fetching each table one by one. This saves turns.
9. When calculating rates or percentages, NEVER filter the dataset before 
   counting — always compute numerator and denominator from the full dataset.
   CORRECT:   COUNT(*) FILTER (WHERE status = 'Returned') / COUNT(*) as rate
   INCORRECT: WHERE status = 'Returned' ... COUNT(*) / total as rate
10. SQL values containing single quotes must use the correct quoting.
    The outer JSON must always use double quotes for all string values.
    CORRECT:   "sql": "SELECT * FROM fact_sales WHERE gender = 'M'"
    INCORRECT: 'sql': "SELECT * FROM fact_sales WHERE gender = 'M'"
11. Always return human-readable names not IDs in your final answer.
    If you have an ID in the result, JOIN to the relevant dimension table
    to get the name before producing the answer action.
12. When a query returns 0 rows and you are filtering on a string value,
    ALWAYS run SELECT DISTINCT <column> FROM <table> to verify the exact
    value before concluding data does not exist. Never give up after one
    zero-rows result without first verifying the filter value is correct.

You must ALWAYS respond with valid JSON in exactly this format, nothing else:
{
    "action": "get_schema" | "get_schema_all" | "run_sql" | "answer",
    "table_name": "table_name_here",
    "sql": "SELECT ...",
    "answer": "your final answer here as a plain English string",
    "reasoning": "brief explanation of why you are taking this action"
}

Only include the key relevant to your action:
- get_schema: include "table_name"
- get_schema_all: no extra fields needed
- run_sql: include "sql"
- answer: include "answer" as a plain English string describing the result
Always include "reasoning" regardless of action.
"""


def clean_llm_response(raw_text: str) -> dict:
    """
    Robustly parse LLM response to dict.
    Handles: proper JSON, markdown-wrapped JSON,
    Python dicts with single quotes, and mixed quote edge cases.
    """
    # strip markdown fences
    if raw_text.startswith("```"):
        raw_text = re.sub(r"```(?:json)?", "", raw_text).strip().strip("```").strip()

    # attempt 1: proper JSON — fastest and most reliable
    try:
        return json.loads(raw_text)
    except json.JSONDecodeError:
        pass

    # attempt 2: regex field extraction — handles mixed quotes
    # and SQL strings containing single quotes inside single-quoted dicts
    try:
        result = {}

        # extract action
        action_match = re.search(r"['\"]action['\"]\s*:\s*['\"](\w+)['\"]", raw_text)
        if action_match:
            result["action"] = action_match.group(1)

        # extract reasoning
        reasoning_match = re.search(
            r"['\"]reasoning['\"]\s*:\s*['\"](.+?)['\"](?=\s*[,}])",
            raw_text, re.DOTALL
        )
        if reasoning_match:
            result["reasoning"] = reasoning_match.group(1)

        # extract table_name
        table_match = re.search(r"['\"]table_name['\"]\s*:\s*['\"](\w+)['\"]", raw_text)
        if table_match:
            result["table_name"] = table_match.group(1)

        # extract answer
        answer_match = re.search(
            r"['\"]answer['\"]\s*:\s*['\"](.+?)['\"](?=\s*[,}])",
            raw_text, re.DOTALL
        )
        if answer_match:
            result["answer"] = answer_match.group(1)

        # extract SQL — try double-quoted value first, then single-quoted
        # double-quoted handles SQL with internal single quotes correctly
        sql_match = re.search(
            r"['\"]sql['\"]\s*:\s*\"(.*?)\"(?=\s*[,}])",
            raw_text, re.DOTALL
        )
        if not sql_match:
            sql_match = re.search(
                r"['\"]sql['\"]\s*:\s*'(.*?)'(?=\s*[,}'])",
                raw_text, re.DOTALL
            )
        if sql_match:
            result["sql"] = sql_match.group(1)

        # return if we at least got an action
        if result.get("action"):
            return result

    except Exception:
        pass

    # attempt 3: ast.literal_eval as last resort
    # works for clean Python dicts but fails when SQL has single quotes inside
    try:
        return ast.literal_eval(raw_text)
    except (ValueError, SyntaxError):
        pass

    # all attempts failed
    return {
        "action": "error",
        "error_message": f"LLM returned non-parseable response: {raw_text}"
    }


def call_llm(messages: list) -> dict:
    """
    Sends conversation history to OpenAI.
    System prompt passed as role=system message.
    Always returns a dict — never raises, never returns raw text.
    Uses clean_llm_response to handle all LLM output format variations.
    """
    try:
        full_messages = [{"role": "system", "content": SYSTEM_PROMPT}] + messages

        response = client.chat.completions.create(
            model="gpt-4o",
            max_tokens=1000,
            temperature=0,        # deterministic — critical for an agent
            messages=full_messages
        )
        raw_text = response.choices[0].message.content.strip()
        action = clean_llm_response(raw_text)

        # validate action field exists
        if "action" not in action:
            return {
                "action": "error",
                "error_message": f"LLM response missing 'action' key: {raw_text}"
            }

        # validate action is one we recognise
        # IMPORTANT: add new actions here AND in loop.py
        VALID_ACTIONS = ("get_schema", "get_schema_all", "run_sql", "answer", "error")
        if action["action"] not in VALID_ACTIONS:
            return {
                "action": "error",
                "error_message": f"Unknown action returned: {action['action']}"
            }

        return action

    except APIError as e:
        return {
            "action": "error",
            "error_message": f"OpenAI API call failed: {str(e)}"
        }


if __name__ == "__main__":
    # test 1: basic action returns get_schema_all for multi-table question
    test_messages = [
        {
            "role": "user",
            "content": "Which product category had the highest return rate in 2024?"
        }
    ]
    result = call_llm(test_messages)
    print("Test 1 - first action:", result)
    assert result["action"] in ("get_schema", "get_schema_all"), \
        f"Expected schema fetch first, got: {result['action']}"

    # test 2: clean_llm_response handles single-quoted dict with SQL
    messy_response = """{'action': 'run_sql', 'table_name': '', \
'sql': "SELECT payment_method FROM fact_sales WHERE gender = 'M'", \
'answer': '', 'reasoning': 'test'}"""
    parsed = clean_llm_response(messy_response)
    print("Test 2 - messy parse:", parsed)
    assert parsed.get("action") == "run_sql", f"Parse failed: {parsed}"
    assert "gender = 'M'" in parsed.get("sql", ""), "SQL not extracted correctly"

    # test 3: markdown-wrapped JSON
    markdown_response = """```json
{"action": "answer", "sql": "", "table_name": "", 
 "answer": "Fashion has the highest return rate", "reasoning": "done"}
```"""
    parsed2 = clean_llm_response(markdown_response)
    print("Test 3 - markdown parse:", parsed2)
    assert parsed2.get("action") == "answer", f"Markdown parse failed: {parsed2}"

    print("\nAll tests passed.")
