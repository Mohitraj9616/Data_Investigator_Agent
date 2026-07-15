import os
from pathlib import Path
from dotenv import load_dotenv

# load .env from project root explicitly
load_dotenv()

from huggingface_hub import HfApi, login

print("Token found:", os.environ.get("HF_TOKEN", "NOT FOUND")[:10] + "...")

login(token=os.environ["HF_TOKEN"])

api = HfApi()

api.create_repo(
    repo_id="Mohitraj16/data-investigator-training",
    repo_type="dataset",
    private=True,
    exist_ok=True
)

api.upload_file(
    path_or_fileobj="evaluation/training_data.jsonl",
    path_in_repo="training_data.jsonl",
    repo_id="Mohitraj16/data-investigator-training",
    repo_type="dataset",
)
print("Uploaded successfully")