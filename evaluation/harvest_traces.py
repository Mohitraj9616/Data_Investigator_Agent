import os
import json
import time
from dotenv import load_dotenv
load_dotenv()

from langfuse import Langfuse
from agent.llm_call import SYSTEM_PROMPT

lf = Langfuse(
    public_key=os.environ["LANGFUSE_PUBLIC_KEY"],
    secret_key=os.environ["LANGFUSE_SECRET_KEY"],
    host=os.environ.get("LANGFUSE_BASE_URL", "https://us.cloud.langfuse.com")
)


def fetch_trace_with_retry(trace_id: str, max_retries: int = 3) -> object:
    """Fetch a single trace with retry on rate limit."""
    for attempt in range(max_retries):
        try:
            return lf.client.trace.get(trace_id)
        except Exception as e:
            if "429" in str(e) or "rate_limited" in str(e):
                wait = 20 * (attempt + 1)
                print(f"\n  Rate limited — waiting {wait}s before retry {attempt+1}/{max_retries}")
                time.sleep(wait)
            else:
                raise e
    return None


def harvest_traces(output_path: str = "evaluation/training_data.jsonl"):
    """
    Pull all successful traces from Langfuse and format them
    as Llama 3 instruction-following fine-tuning data (JSONL).
    """

    print("Fetching traces from Langfuse...")

    all_traces = []
    page = 1
    while True:
        response = lf.client.trace.list(page=page, limit=50)
        traces = response.data
        if not traces:
            break
        all_traces.extend(traces)
        if len(traces) < 50:
            break
        page += 1

    print(f"Total traces fetched: {len(all_traces)}")

    training_examples = []
    skipped = 0

    for idx, trace in enumerate(all_traces):
        print(f"Processing trace {idx+1}/{len(all_traces)}...", end="\r")

        # check success from metadata
        metadata = getattr(trace, 'metadata', {}) or {}
        if not metadata.get("success", False):
            skipped += 1
            continue

        # extract question and answer
        question = trace.input.get("question", "") if trace.input else ""
        answer = trace.output.get("answer", "") if trace.output else ""

        if not question or not answer:
            skipped += 1
            continue

        # rate limit protection — 1 second between each trace fetch
        # keeps us well under the 15 requests/window limit
        time.sleep(1.5)

        full_trace = fetch_trace_with_retry(trace.id)
        if full_trace is None:
            print(f"\nFailed to fetch trace {trace.id} after retries — skipping")
            skipped += 1
            continue

        observations = sorted(
            full_trace.observations or [],
            key=lambda x: x.start_time
        )

        # extract only LLM generation calls
        llm_calls = [o for o in observations if o.type == "GENERATION"]

        if not llm_calls:
            skipped += 1
            continue

        # build conversation messages
        messages = []
        messages.append({
            "role": "user",
            "content": f"Answer this business question using the database: {question}"
        })

        for i, gen in enumerate(llm_calls):
            if not gen.output:
                continue

            output = gen.output
            if isinstance(output, dict):
                assistant_content = json.dumps(output)
            else:
                assistant_content = str(output)

            messages.append({
                "role": "assistant",
                "content": assistant_content
            })

            is_last_turn = i == len(llm_calls) - 1
            if not is_last_turn:
                messages.append({
                    "role": "user",
                    "content": "[Tool result: action executed successfully. Continue to next step.]"
                })

        if len(messages) < 2:
            skipped += 1
            continue

        training_example = {
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT}
            ] + messages
        }
        training_examples.append(training_example)

    print(f"\nSkipped  : {skipped} traces (failed, incomplete, or rate limited)")
    print(f"Harvested: {len(training_examples)} training examples")

    with open(output_path, "w") as f:
        for example in training_examples:
            f.write(json.dumps(example) + "\n")

    print(f"Saved to : {output_path}")
    return training_examples


if __name__ == "__main__":
    examples = harvest_traces()

    if examples:
        print(f"\n--- First example preview ---")
        first = examples[0]
        print(f"Total messages : {len(first['messages'])}")
        print(f"System prompt  : {len(first['messages'][0]['content'])} chars")
        print(f"Question       : {first['messages'][1]['content'][:80]}...")
        if len(first['messages']) > 2:
            print(f"First action   : {first['messages'][2]['content'][:120]}...")
        if len(first['messages']) > 4:
            print(f"Second action  : {first['messages'][4]['content'][:120]}...")

        print(f"\n--- Dataset stats ---")
        turn_counts = [len(ex['messages']) for ex in examples]
        print(f"Min turns      : {min(turn_counts)}")
        print(f"Max turns      : {max(turn_counts)}")
        print(f"Avg turns      : {sum(turn_counts)/len(turn_counts):.1f}")

        questions = set()
        for ex in examples:
            for msg in ex['messages']:
                if msg['role'] == 'user' and 'business question' in msg['content']:
                    questions.add(msg['content'])
        print(f"Unique questions: {len(questions)}")