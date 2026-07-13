# create evaluation/generate_traces.py
import sys
sys.path.insert(0, '.')
from dotenv import load_dotenv
load_dotenv()

from agent.loop import agent_loop
import json

with open("evaluation/golden_dataset.json") as f:
    cases = json.load(f)

questions = [c["question"] for c in cases]

# run each question 5 times to generate 75 traces
for run in range(5):
    print(f"\n=== Run {run+1}/5 ===")
    for i, q in enumerate(questions):
        print(f"[{i+1}/{len(questions)}] {q[:60]}...")
        result = agent_loop(q, max_retries=5)
        print(f"  Status: {result['status']} | Turns: {result.get('turns_taken')}")