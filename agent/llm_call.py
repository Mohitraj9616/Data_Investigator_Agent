import os
import re
from dotenv import load_dotenv
import json
from openai import OpenAI, APIError
import ast

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
6. Your response must use double quotes for all JSON keys and string values. Never use single quotes.
7. In PostgreSQL, ALWAYS use single quotes for string values in WHERE clauses.
   NEVER use double quotes for string values — double quotes mean column/table 
   identifiers in PostgreSQL, not string literals.
   CORRECT:   WHERE order_status = 'Returned'
   INCORRECT: WHERE order_status = "Returned".
8. If the question clearly requires multiple tables, use action "get_schema_all" 
   instead of fetching each table one by one. This saves turns.
9. When calculating rates or percentages, NEVER filter the dataset before 
   counting — always compute numerator and denominator from the full dataset.
   CORRECT:   COUNT(*) FILTER (WHERE status = 'Returned') / COUNT(*) as rate
   INCORRECT: WHERE status = 'Returned' ... COUNT(*) / total as rate


You must ALWAYS respond with valid JSON in exactly this format, nothing else:
{
    "action": "get_schema" | "run_sql" | "answer",
    "table_name": "table_name_here",
    "sql": "SELECT ...",
    "answer": "your final answer here",
    "reasoning": "brief explanation of why you are taking this action"
}

Only include the key relevant to your action:
- get_schema: include "table_name"
- run_sql: include "sql"
- answer: include "answer"
Always include "reasoning" regardless of action.
"""


def call_llm(messages: list) -> dict:
    """
    Sends conversation history to OpenAI.
    System prompt is passed as the first message with role "system".
    Always returns a dict — never raises, never returns raw text.
    """
    # ALLOWLIST: add new actions here AND add their branch in loop.py
    VALID_ACTIONS = ("get_schema", "get_schema_all", "run_sql", "answer", "error")

    try:
        # OpenAI takes system prompt as a message with role "system"
        # prepend it to the messages list
        full_messages = [{"role": "system", "content": SYSTEM_PROMPT}] + messages

        response = client.chat.completions.create(
            model = 'gpt-4o-mini',
            max_tokens=1000,
            temperature=0,
            messages= full_messages 
            )

        raw_text = response.choices[0].message.content.strip()

        # strip markdown code fences if model wraps JSON in ```json ... ```
        if raw_text.startswith("```"):
            raw_text = re.sub(r"```(?:json)?", "", raw_text).strip().strip("```").strip()

        try:
            action  = json.loads(raw_text)
        except json.JSONDecodeError:
            try:
                action = ast.literal_eval(raw_text)
            except (ValueError, SyntaxError):
                return {
                    "action": "error",
                    "error_message": f"LLM returned non-parseable response: {raw_text}"
                }


        if "action" not in action:
            return {
                "action":"error",
                "error_message": f"LLM response missing 'action' key:{raw_text} "
            }
        
        if action["action"] not in VALID_ACTIONS:
            return {
                "action": "error",
                "error_message": f"Unknown action returned: {action['action']}"
            }

        return action
    
    except json.JSONDecodeError:
        return {
            "action": "error",
            "error_message": f"LLM returned non-JSON response: {raw_text}"
        }
    except APIError as e:
        return {
            "action": "error",
            "error_message": f"OpenAI API call failed: {str(e)}"
        }
    

if __name__ == "__main__":
    test_messages = [
        {
            "role": "user",
            "content": "Which product category had the highest return rate in 2024?"
        }
    ]
    result = call_llm(test_messages)
    print("LLM first action:", result)
    # should be get_schema — if it's run_sql, the system prompt isn't working



