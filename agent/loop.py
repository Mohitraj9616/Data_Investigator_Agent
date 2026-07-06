from agent.llm_call import call_llm
from agent.tool_call import (extract_table_from_sql,
                             ensure_schemas_cached,
                             format_schema_for_llm,
                             check_sql_safety,get_all_schemas)


from db_checks.database_conn_check import run_sql_query


def agent_loop(user_question: str, max_retries: int = 5) ->dict:
    """
    The core agent loop. Three phases every iteration:
    1. DECIDE  — call_llm returns next action
    2. ACT     — execute that action (schema fetch / SQL run / answer)
    3. OBSERVE — append result to messages so LLM sees what happened

    Loop exits when:
    - LLM produces "answer" action (success path)
    - retries hit max_retries (failure path)
    - LLM itself returns an error action (API/parse failure)
    """

    messages = [
        { 
          "role": "user",
          "content": f"Answer this business question using the database: {user_question}"
        }
    ]

    schema_cache = {}  # tables fetched in this session — never re-fetch same table
    retries = 0        # counts both SQL errors AND zero-row results

    print(f"\n{'='*60}")
    print(f"Question: {user_question}")
    print(f"{'='*60}\n")

    while retries <= max_retries:
        turn = len([m for m in messages if m["role"] == "assistant"]) + 1
        print(f"--- Turn {turn} (retries used: {retries}/{max_retries}) ---")

        #---------------Decide ------------------------

        llm_response = call_llm(messages)
        action = llm_response.get("action")
        reasoning = llm_response.get("reasoning","no reasoning provided")

        print(f"Action : {action} ")
        print(f"Reason : {reasoning} ")
        
        #------------ Database-connection-check

        try:
            schema_cache, newly_fetched = get_all_schemas(schema_cache)
        except ConnectionError as e:
            return {
                "status": "error",
                "reason": str(e),
                "conversation": messages
            }

        # ─---------------- ACT ─────────────────────────────────────────────────

        # LLM or API failure — surface immediately, don't retry
        if action == 'error':
            return {
                "status" : "error",
                "reason" : llm_response.get("error_message"),
                "conversation" : messages,
            }
        


        # ------------ get Schema --------------------------------------
        elif action == 'get_schema':
            table = llm_response.get("table_name")
            if not table:
                observation = {
                    "status" : "error",
                    "message" : "get_schema action missing 'table_name' field"
                }

            else:
                schema_cache,newly_fetched = ensure_schemas_cached([table],schema_cache)
                observation = {
                    "status" : "schema fetched",
                    "message": f" Schema fetched for : {table}. ",
                    "schema" : format_schema_for_llm({table : schema_cache.get(table, {})})
                }

                print(f"Schema fetched for '{table}' ")
        
        # ----------- get Schema for all ------------------------------

        elif action == "get_schema_all":
            schema_cache, newly_fetched = get_all_schemas(schema_cache)
            observation = {
                "status": "schema_fetched",
                "message": "All table schemas fetched.",
                "schema": format_schema_for_llm(schema_cache)
            }
            print(f"Schema : fetched all tables at once")
        

        # -------------------run_sql -----------------------------
        elif action == 'run_sql':
            sql = llm_response.get("sql","").strip()

            if not sql:
                observation = {
                    "status" : "error",
                    "messages" : "run sql action missing 'sql' field"
                }
                retries+=1

            else:
                safe, safety_msg = check_sql_safety(sql)
                if not safe:
                    observation = {
                        "status": "error",
                        "message" : f"SQL blocked by safety check: {safety_msg}",
                        "sql_attempted" : sql,
                    }
                    
                    retries+=1

                else:
                    # proactively fetch schemas for any table
                    # not yet in cache before running
                    tables_in_query = extract_table_from_sql(sql)
                    schema_cache,newly_fetched = ensure_schemas_cached(tables_in_query,schema_cache)

                    if newly_fetched:
                        # don't run SQL yet — tell LLM what schema it now has
                        # so it can validate its own column names first
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
                        # all schemas known — safe to execute
                        print(f"SQL    : {sql}")
                        result = run_sql_query(sql)

                        if result["status"] == "error":
                            retries+=1
                            observation = {
                                "status" : "error",
                                "error_message" : result["error_message"],
                                "sql_that_failed" : sql,
                                "hint": (
                                    "Fix the SQL based on the error message. "
                                    "Re-check the schema if it's a column error."
                                ),
                            }
                            print(f"Error  : {result['error_message']}")

                        elif result["row_count"] == 0:
                             retries+=1
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


                        else:
                            observation = {
                                "status" : "success",
                                "row_count" : result["row_count"],
                                "columns" : result["columns"],
                                "rows" : result["rows"],
                            }
                            print(f"Result : {result['row_count']} rows returned")

        
        elif action == "answer":
            answer = llm_response.get("answer", "")
            
            # accept both string and dict — LLM often returns structured data
            if isinstance(answer, dict):
                display_answer = "\n".join(f"  {k}: {v}" for k, v in answer.items())
                answer = str(answer)  # convert to string for storage
            else:
                answer = answer.strip()
                display_answer = answer

            if not answer:
                return {
                    "status": "error",
                    "reason": "LLM produced answer action with empty answer field.",
                    "conversation": messages,
                }

            print(f"\nAnswer :\n{display_answer}")
            print(f"{'='*60}\n")
            return {
                "status": "success",
                "answer": answer,
                "display": display_answer,      # always human-readable
                "schema_used": list(schema_cache.keys()),
                "turns_taken": len([m for m in messages if m["role"] == "assistant"]),
            }

        else:
            observation = {
                "status": "error",
                "message": f"Unknown action '{action}' — expected get_schema, get_schema_all, run_sql, or answer."
            }
            retries += 1

        # ── OBSERVE ─────────────────────────────────────────────
        messages.append({"role": "assistant", "content": str(llm_response)})
        messages.append({"role": "user", "content": str(observation)})

# # retry ceiling hit
#         elif action == "answer":
#             answer = llm_response.get("answer", "")
#             if isinstance(answer, dict):
#                  answer = str(answer)  # convert dict to string if LLM returned structured JSON
#             answer = answer.strip()
#             if not answer:
#                 return {
#                     "status": "error",
#                     "reason": "LLM produced answer action with empty answer field.",
#                     "conversation": messages,
#                 }
            
#             print(f"\nAnswer : {answer}")
#             print(f"{'='*60}\n")
#             return {
#                 "status":"success",
#                 "answer" : answer,
#                 "schema_used" : list(schema_cache.keys()),
#                 "turns_taken" : len(messages),
#             }
#         else:
#             observation = {
#                 "status" : "error",
#                 "message": f"Unknown action '{action}' — expected get_schema, run_sql, or answer."
#             }
#             retries += 1
            
#         # ── OBSERVE ─────────────────────────────────────────────
#         # append what the LLM decided AND what happened
#         # so the next iteration has the full context
#         messages.append({"role": "assistant", "content": str(llm_response)})
#         messages.append({"role": "user", "content": str(observation)})

#     # retry ceiling hit
#     return {
#         "status": "failed",
#         "reason": f"Could not produce a verified answer within {max_retries} attempts.",
#         "last_observation": str(observation),
#         "conversation": messages,
#     }


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





      