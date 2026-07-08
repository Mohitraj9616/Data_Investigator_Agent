# replace test_langfuse.py with this
from dotenv import load_dotenv
load_dotenv()

import os
from langfuse import Langfuse

public_key = os.environ.get("LANGFUSE_PUBLIC_KEY")
secret_key = os.environ.get("LANGFUSE_SECRET_KEY")
host = os.environ.get("LANGFUSE_BASE_URL") or os.environ.get("LANGFUSE_HOST")

print(f"Public key : {public_key}")
print(f"Secret key : {secret_key[:20]}...")
print(f"Host       : {host}")

lf = Langfuse(
    public_key=public_key,
    secret_key=secret_key,
    host=host,
    debug=True  # this prints every HTTP call langfuse makes
)

trace = lf.trace(name="test_connection", input={"test": "hello"})
trace.update(output={"result": "connection test"})
lf.flush()
print("Done - trace ID:", trace.id)