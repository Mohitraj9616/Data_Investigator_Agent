from fastapi import FastAPI,HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
from agent.loop import agent_loop
import uvicorn

app = FastAPI(title="Data Investigator Agent")

# "https://card-youth-special-notices.trycloudflare.com",
# "https://*.vercel.app",  # allows all your Vercel deployments
# CORS — allows browser requests from any origin
# tighten this to your Vercel URL once deployed
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],         
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

class QueryRequest(BaseModel):
    question: str
    max_retries: int = 5

class QueryResponse(BaseModel):
    status: str
    answer: str | None = None
    display: str | None = None
    schema_used: list[str]| None = None
    turns_taken: int | None = None
    reason: str | None = None
    sql_queries: list[str] | None = None  # new — SQL runs extracted from conversation




@app.post("/agent/query", response_model=QueryResponse)
async def query(req: QueryRequest):
    result = agent_loop(req.question,max_retries=req.max_retries)


    if result["status"] == "error":
        raise HTTPException(
            status_code=500,
            detail=result.get("reason", "Agent encountered an internal error")
        )

    if result["status"] == "failed":
        raise HTTPException(
            status_code=422,
            detail=result.get("reason", "Agent failed to produce an answer within retry limit")
        )
    
    # extract SQL queries from conversation for UI display
    sql_queries = []
    for msg in result.get("conversation", []):
        content = msg.get("content", "")
        if isinstance(content, str) and "'sql'" in content or '"sql"' in content:
            try:
                import re
                sql_match = re.search(r"['\"]sql['\"]\s*:\s*['\"](.+?)['\"](?=\s*[,}])",
                                     content, re.DOTALL)
                if sql_match:
                    sql = sql_match.group(1).strip()
                    if sql and sql not in sql_queries:
                        sql_queries.append(sql)
            except Exception:
                pass

    return QueryResponse(
        status=result["status"],
        answer=result.get("answer"),
        display=result.get("display"),
        schema_used=result.get("schema_used"),
        turns_taken=result.get("turns_taken"),
        sql_queries=sql_queries if sql_queries else None
    )




@app.get("/health")
async def health():
    return {"status": "ok"}