# add this debug script temporarily
# save as evaluation/debug_traces.py

import os
import json
from dotenv import load_dotenv
load_dotenv()

from langfuse import Langfuse

lf = Langfuse(
    public_key=os.environ["LANGFUSE_PUBLIC_KEY"],
    secret_key=os.environ["LANGFUSE_SECRET_KEY"],
    host=os.environ.get("LANGFUSE_BASE_URL", "https://us.cloud.langfuse.com")
)

# fetch first 5 traces and print their raw structure
response = lf.client.trace.list(page=1, limit=5)
traces = response.data

for i, trace in enumerate(traces[:3]):
    print(f"\n=== Trace {i+1} ===")
    print(f"Name: {trace.name}")
    print(f"Input: {trace.input}")
    print(f"Output: {trace.output}")
    print(f"Scores: {trace.scores}")
    print(f"Tags: {getattr(trace, 'tags', None)}")
    print(f"Metadata: {getattr(trace, 'metadata', None)}")