# retrace (Python SDK)

Python SDK for Retrace.

## Install

```bash
pip install retrace-sdk[openai,anthropic]
```

## Usage (target API for Days 4-5)

```python
import retrace

retrace.init(api_key="...", project_id="...")

# Auto-instrumented:
from openai import OpenAI
client = OpenAI()
response = client.chat.completions.create(...)  # traced automatically

# Manual RAG instrumentation:
@retrace.trace_retrieval
def retrieve_docs(query: str):
    chunks = vector_db.search(query, top_k=5)
    retrace.log_chunks(chunks)
    return chunks
```

**Day 1 status:** package skeleton only. SDK functionality lands Days 4-5.
