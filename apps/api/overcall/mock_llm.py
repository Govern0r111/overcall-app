import time

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

mock_app = FastAPI(title="Overcall mock OpenAI server")
REPLY = "This is a mock completion from Overcall's local LLM server. No real model was called."


def forced_error(request: Request):
    code = request.headers.get("x-mock-status", "")
    if code.isdigit() and int(code) >= 400:
        return JSONResponse({"error": {"message": "Mock error forced via X-Mock-Status", "type": "mock_error", "code": int(code)}},
                            status_code=int(code))
    return None


@mock_app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    if (err := forced_error(request)) is not None:
        return err
    body = await request.json()
    msgs = body.get("messages") or []
    prompt_tokens = max(1, sum(len(str(m.get("content", ""))) for m in msgs if isinstance(m, dict)) // 4)
    completion_tokens = min(int(body.get("max_tokens") or 64), len(REPLY) // 4)
    return {
        "id": f"chatcmpl-mock{int(time.time() * 1000)}", "object": "chat.completion", "created": int(time.time()),
        "model": body.get("model", "gpt-4o-mini"),
        "choices": [{"index": 0, "message": {"role": "assistant", "content": REPLY}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens, "total_tokens": prompt_tokens + completion_tokens},
    }


@mock_app.post("/v1/embeddings")
async def embeddings(request: Request):
    if (err := forced_error(request)) is not None:
        return err
    body = await request.json()
    inputs = body.get("input")
    inputs = inputs if isinstance(inputs, list) else [inputs]
    tokens = max(1, sum(len(str(i)) for i in inputs) // 4)
    data = [{"object": "embedding", "index": i, "embedding": [round(((hash(str(x)) >> k) % 1000) / 1000, 3) for k in range(8)]}
            for i, x in enumerate(inputs)]
    return {"object": "list", "data": data, "model": body.get("model", "text-embedding-3-small"),
            "usage": {"prompt_tokens": tokens, "total_tokens": tokens}}


@mock_app.get("/v1/models")
async def models():
    ids = ["gpt-4o", "gpt-4o-mini", "gpt-4.1", "gpt-4.1-mini", "text-embedding-3-small"]
    return {"object": "list", "data": [{"id": i, "object": "model", "owned_by": "mock"} for i in ids]}
