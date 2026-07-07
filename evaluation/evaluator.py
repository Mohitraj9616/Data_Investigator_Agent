import json
import requests
from datetime import datetime
from langfuse import Langfuse
import os
from dotenv import load_dotenv
load_dotenv()


AGENT_URL = "http://3.6.91.181:8000/agent/query"
GOLDEN_DATASET_PATH = "evaluation/golden_dataset.json"

langfuse = Langfuse(
    public_key=os.environ.get("LANGFUSE_PUBLIC_KEY"),
    secret_key=os.environ.get("LANGFUSE_SECRET_KEY"),
    host=os.environ.get("LANGFUSE_HOST", "https://cloud.langfuse.com")
)


def load_golden_dataset() -> list[dict]:
    with open(GOLDEN_DATASET_PATH) as f:
        return json.load(f)


def call_agent(question: str) -> dict:
    try:
        response = requests.post(
            AGENT_URL,
            json={"question": question, "max_retries": 5},
            timeout=120
        )
        return response.json()
    except Exception as e:
        return {"status": "error", "reason": str(e)}


def check_answer(agent_answer: str, case: dict) -> bool:
    """
    Check if expected answer appears in agent response.
    Deterministic check against ground truth — no fuzzy scoring.
    """
    expected = case["expected_answer"].lower()
    answer_lower = str(agent_answer).lower()

    # check expected key values if present
    key_values = case.get("expected_key_values", {})
    key_hits = 0
    for key, value in key_values.items():
        value_str = str(value).lower()
        try:
            numeric = float(value)
            rounded = [str(int(numeric)), str(round(numeric, 1)), str(round(numeric, 2))]
            if any(v in answer_lower for v in rounded):
                key_hits += 1
        except (ValueError, TypeError):
            if value_str in answer_lower:
                key_hits += 1

    key_score = key_hits / max(len(key_values), 1)

    # primary match: any meaningful word from expected answer found
    primary = any(
        word in answer_lower
        for word in expected.split()
        if len(word) > 3
    )

    return primary and key_score >= 0.5


def run_evaluation():
    cases = load_golden_dataset()
    passed = 0
    total = len(cases)
    results = []
    turns_list = []

    print(f"\n{'='*60}")
    print(f"EVALUATION — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"Agent: {AGENT_URL}")
    print(f"Questions: {total}")
    print(f"{'='*60}\n")

    # langfuse: one trace for the entire evaluation run
    eval_trace = langfuse.trace(
        name="evaluation_run",
        input={"total_questions": total, "agent_url": AGENT_URL},
        metadata={"golden_dataset": GOLDEN_DATASET_PATH}
    )

    for i, case in enumerate(cases, 1):
        print(f"[{i}/{total}] {case['question']}")

        agent_result = call_agent(case["question"])

        if agent_result.get("status") != "success":
            result = {
                "question": case["question"],
                "passed": False,
                "status": "agent_failed",
                "reason": agent_result.get("reason", "unknown"),
                "turns_taken": None,
            }
            print(f"  ❌ Agent failed: {result['reason']}\n")

            # langfuse: log failed case
            langfuse.score(
                trace_id=eval_trace.id,
                name=f"q{i}_correct",
                value=0,
                comment=f"Agent failed: {result['reason']}"
            )

        else:
            agent_answer = agent_result.get("answer", "")
            turns = agent_result.get("turns_taken", 0)
            correct = check_answer(agent_answer, case)

            if correct:
                passed += 1
            turns_list.append(turns)

            result = {
                "question": case["question"],
                "passed": correct,
                "status": "completed",
                "agent_answer": str(agent_answer)[:200],
                "expected_answer": case["expected_answer"],
                "turns_taken": turns,
            }

            status_icon = "✅" if correct else "❌"
            print(f"  {status_icon} {'PASS' if correct else 'FAIL'}")
            print(f"  Answer   : {str(agent_answer)[:100]}")
            print(f"  Expected : {case['expected_answer']}")
            print(f"  Turns    : {turns}\n")

            # langfuse: score each question individually
            langfuse.score(
                trace_id=eval_trace.id,
                name=f"q{i}_correct",
                value=1 if correct else 0,
                comment=f"Expected: {case['expected_answer']}"
            )
            langfuse.score(
                trace_id=eval_trace.id,
                name=f"q{i}_turns",
                value=turns,
            )

        results.append(result)

    # ── summary ──────────────────────────────────────────────────
    accuracy = passed / total * 100
    avg_turns = sum(turns_list) / max(len(turns_list), 1)
    failed_questions = [r["question"] for r in results if not r["passed"]]

    print(f"{'='*60}")
    print(f"SUMMARY")
    print(f"{'='*60}")
    print(f"Accuracy  : {passed}/{total} ({accuracy:.1f}%)")
    print(f"Avg turns : {avg_turns:.1f}")
    if failed_questions:
        print(f"\nFailed questions:")
        for q in failed_questions:
            print(f"  - {q}")
    print(f"{'='*60}\n")

    # langfuse: score the overall evaluation run
    eval_trace.score(name="accuracy", value=accuracy / 100)
    eval_trace.score(name="avg_turns", value=avg_turns)
    eval_trace.update(
        output={
            "accuracy": accuracy,
            "passed": passed,
            "total": total,
            "avg_turns": avg_turns,
            "failed_questions": failed_questions,
        }
    )

    # save results locally for tracking over time
    output = {
        "timestamp": datetime.now().isoformat(),
        "accuracy": accuracy,
        "passed": passed,
        "total": total,
        "avg_turns": avg_turns,
        "failed_questions": failed_questions,
        "results": results,
    }
    path = f"evaluation/results_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
    with open(path, "w") as f:
        json.dump(output, f, indent=2)

    langfuse.flush()
    print(f"Results saved : {path}")
    print(f"Langfuse dashboard : https://cloud.langfuse.com")
    return output


if __name__ == "__main__":
    run_evaluation()