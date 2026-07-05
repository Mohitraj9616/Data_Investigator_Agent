from fastapi import FastAPI,HTTPException
from pydantic import BaseModel
from agent.loop import agent_loop
import uvicorn

app = FastAPI(title="Data Investigator Agent")

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

    return QueryResponse(**result)

@app.get("/health")
async def health():
    return {"status": "ok"}