from agent.llm_call import call_llm
from agent.tool_call import (extract_table_from_sql,
                             ensure_schemas_cached,
                             format_schema_for_llm,
                             check_sql_safety, get_all_schemas)
from db_checks.database_conn_check import run_sql_query
from langfuse import Langfuse
import os
from dotenv import load_dotenv
load_dotenv()


langfuse = Langfuse(
    public_key=os.environ.get("LANGFUSE_PUBLIC_KEY"),
    secret_key=os.environ.get("LANGFUSE_SECRET_KEY"),
    host=os.environ.get("LANGFUSE_BASE_URL", "https://cloud.langfuse.com")
)


def agent_loop(user_question: str, max_retries: int = 5) -> dict:
    """
    The core agent loop. Three phases every iteration:
    1. DECIDE  — call_llm returns next action
    2. ACT     — execute that action
    3. OBSERVE — append result to messages so LLM sees what happened

    Loop exits when:
    - LLM produces "answer" action (success path)
    - retries hit max_retries (failure path)
    - LLM itself returns an error action (API/parse failure)
    """

    # ── LANGFUSE: one trace per user question ──────────────────
    trace = langfuse.trace(
        name="agent_loop",
        input={"question": user_question},
        metadata={"max_retries": max_retries}
    )

    messages = [
        {
            "role": "user",
            "content": f"Answer this business question using the database: {user_question}"
        }
    ]

    schema_cache = {}
    retries = 0
    observation = {}

    print(f"\n{'='*60}")
    print(f"Question: {user_question}")
    print(f"{'='*60}\n")

    while retries <= max_retries:
        turn = len([m for m in messages if m["role"] == "assistant"]) + 1
        print(f"--- Turn {turn} (retries used: {retries}/{max_retries}) ---")

        # ── DECIDE ──────────────────────────────────────────────
        # langfuse: span for each turn
        turn_span = trace.span(
            name=f"turn_{turn}",
            input={"retries": retries, "messages_count": len(messages)}
        )

        # langfuse: generation for the LLM call
        generation = trace.generation(
            name=f"llm_call_turn_{turn}",
            model ='gpt-4o-mini',
            input=messages,
        )

        llm_response = call_llm(messages)

        # langfuse: log what LLM returned
        generation.end(output=llm_response)

        action = llm_response.get("action")
        reasoning = llm_response.get("reasoning", "no reasoning provided")

        print(f"Action : {action}")
        print(f"Reason : {reasoning}")

        # ── ACT ─────────────────────────────────────────────────

        if action == "error":
            turn_span.end(output={"action": "error"}, level="ERROR")
            trace.update(
                output={"status": "error", "reason": llm_response.get("error_message")},
                metadata={"success": False}
            )
            langfuse.flush()
            return {
                "status": "error",
                "reason": llm_response.get("error_message"),
                "conversation": messages,
            }

        # ── get_schema ──
        elif action == "get_schema":
            table = llm_response.get("table_name")
            if not table:
                observation = {
                    "status": "error",
                    "message": "get_schema action missing 'table_name' field"
                }
            else:
                schema_cache, newly_fetched = ensure_schemas_cached([table], schema_cache)
                observation = {
                    "status": "schema_fetched",
                    "message": f"Schema fetched for: {table}.",
                    "schema": format_schema_for_llm({table: schema_cache.get(table, {})})
                }
                print(f"Schema fetched for '{table}'")

        # ── get_schema_all ──
        elif action == "get_schema_all":
            try:
                schema_cache, newly_fetched = get_all_schemas(schema_cache)
                observation = {
                    "status": "schema_fetched",
                    "message": "All table schemas fetched.",
                    "schema": format_schema_for_llm(schema_cache)
                }
                print(f"Schema : fetched all tables at once")
            except ConnectionError as e:
                turn_span.end(output={"action": "get_schema_all", "error": str(e)}, level="ERROR")
                trace.update(output={"status": "error"}, metadata={"success": False})
                langfuse.flush()
                return {
                    "status": "error",
                    "reason": str(e),
                    "conversation": messages
                }

        # ── run_sql ──
        elif action == "run_sql":
            sql = llm_response.get("sql", "").strip()

            if not sql:
                observation = {
                    "status": "error",
                    "message": "run_sql action missing 'sql' field"
                }
                retries += 1

            else:
                safe, safety_msg = check_sql_safety(sql)
                if not safe:
                    observation = {
                        "status": "error",
                        "message": f"SQL blocked by safety check: {safety_msg}",
                        "sql_attempted": sql,
                    }
                    retries += 1

                else:
                    # proactively fetch schemas for tables not yet in cache
                    tables_in_query = extract_table_from_sql(sql)
                    schema_cache, newly_fetched = ensure_schemas_cached(
                        tables_in_query, schema_cache
                    )

                    if newly_fetched:
                        observation = {
                            "status": "schema_auto_fetched",
                            "message": (
                                "Schema was missing for some tables in your SQL. "
                                "Fetched automatically. Validate your column names "
                                "against this schema, then re-submit the SQL."
                            ),
                            "newly_fetched": format_schema_for_llm(newly_fetched),
                        }
                        print(f"Schema : auto-fetched for {list(newly_fetched.keys())}")

                    else:
                        # langfuse: span for SQL execution
                        sql_span = trace.span(
                            name=f"sql_execution_turn_{turn}",
                            input={"sql": sql}
                        )

                        print(f"SQL    : {sql}")
                        result = run_sql_query(sql)

                        if result["status"] == "error":
                            retries += 1
                            observation = {
                                "status": "sql_error",
                                "error_message": result["error_message"],
                                "sql_that_failed": sql,
                                "hint": (
                                    "Fix the SQL based on the error message. "
                                    "Re-check the schema if it's a column error."
                                ),
                            }
                            print(f"Error  : {result['error_message']}")
                            sql_span.end(
                                output={"error": result["error_message"]},
                                level="ERROR"
                            )

                        elif result["row_count"] == 0:
                            retries += 1
                            observation = {
                                "status": "empty_result",
                                "sql_that_ran": sql,
                                "hint": (
                                    "Query ran without error but returned 0 rows. "
                                    "Your filter value is likely wrong — check the exact "
                                    "values that exist in the column you are filtering on. "
                                    "For example, if filtering on order_status = 'returned', "
                                    "first run: SELECT DISTINCT order_status FROM fact_sales "
                                    "to see the actual values stored in that column. "
                                    "Values may be capitalised differently than you expect."
                                ),
                            }
                            print(f"Result : 0 rows — prompting broader query")
                            sql_span.end(output={"row_count": 0})

                        else:
                            observation = {
                                "status": "success",
                                "row_count": result["row_count"],
                                "columns": result["columns"],
                                "rows": result["rows"],
                            }
                            print(f"Result : {result['row_count']} rows returned")
                            sql_span.end(output={
                                "row_count": result["row_count"],
                                "columns": result["columns"]
                            })

        # ── answer ──
        elif action == "answer":
            answer = llm_response.get("answer", "")

            if isinstance(answer, dict):
                display_answer = "\n".join(f"  {k}: {v}" for k, v in answer.items())
                answer = str(answer)
            else:
                answer = answer.strip()
                display_answer = answer

            if not answer:
                trace.update(
                    output={"status": "error", "reason": "empty answer"},
                    metadata={"success": False}
                )
                langfuse.flush()
                return {
                    "status": "error",
                    "reason": "LLM produced answer action with empty answer field.",
                    "conversation": messages,
                }

            turns_taken = len([m for m in messages if m["role"] == "assistant"])

            # langfuse: score and close the trace on success
            trace.score(name="success", value=1)
            trace.score(name="turns_taken", value=turns_taken)
            trace.update(
                output={"answer": answer, "turns_taken": turns_taken},
                metadata={"success": True, "schema_used": list(schema_cache.keys())}
            )
            langfuse.flush()

            print(f"\nAnswer :\n{display_answer}")
            print(f"{'='*60}\n")
            return {
                "status": "success",
                "answer": answer,
                "display": display_answer,
                "schema_used": list(schema_cache.keys()),
                "turns_taken": turns_taken,
                "conversation": messages,  # needed for evaluator
            }

        else:
            observation = {
                "status": "error",
                "message": f"Unknown action '{action}' — expected get_schema, get_schema_all, run_sql, or answer."
            }
            retries += 1

        # ── OBSERVE ─────────────────────────────────────────────
        turn_span.end(output={"action": action, "observation_status": observation.get("status")})
        messages.append({"role": "assistant", "content": str(llm_response)})
        messages.append({"role": "user", "content": str(observation)})

    # ── retry ceiling hit ────────────────────────────────────────
    trace.score(name="success", value=0)
    trace.update(
        output={"status": "failed", "reason": "max retries reached"},
        metadata={"success": False}
    )
    langfuse.flush()

    return {
        "status": "failed",
        "reason": f"Could not produce a verified answer within {max_retries} attempts.",
        "last_observation": str(observation),
        "conversation": messages,
    }


if __name__ == "__main__":
    questions = [
        "Which product category had the highest return rate in 2024?",
        "Which city tier has the highest Cash on Delivery usage?",
        "Did average delivery delay get worse during Diwali Sale 2025?",
    ]
    for q in questions:
        result = agent_loop(q, max_retries=5)
        print(f"Status : {result['status']}")
        print(f"Turns  : {result.get('turns_taken')}")
        print()