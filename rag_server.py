import os
import httpx
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
import rag_core

LLAMA = os.environ.get("LLAMA_URL", "http://127.0.0.1:8081")
API_KEY = os.environ.get("API_KEY", "")

print("Membangun indeks RAG...", flush=True)
IDX = rag_core.load_index()
print("Indeks siap: %d potongan" % IDX.N, flush=True)

app = FastAPI()
client = httpx.AsyncClient(timeout=None)


def check(req: Request):
    if API_KEY and req.headers.get("authorization", "") != "Bearer " + API_KEY:
        raise HTTPException(status_code=401, detail="API key salah")


@app.get("/")
async def root():
    return {"status": "ok", "model": "micromind", "chunks": IDX.N}


@app.get("/v1/models")
async def models(request: Request):
    check(request)
    return {"object": "list", "data": [{"id": "micromind", "object": "model"}]}


@app.get("/search")
async def search(request: Request, q: str):
    check(request)
    return [{"source": s, "preview": t[:200]} for s, t in IDX.search(q)]


@app.post("/v1/chat/completions")
async def chat(request: Request):
    check(request)
    body = await request.json()
    body["messages"] = rag_core.augment(body.get("messages", []), IDX)
    if not body.get("max_tokens"):
        body["max_tokens"] = 1024
    if body.get("stream"):
        async def gen():
            async with client.stream("POST", LLAMA + "/v1/chat/completions", json=body) as r:
                async for chunk in r.aiter_raw():
                    yield chunk
        return StreamingResponse(gen(), media_type="text/event-stream")
    r = await client.post(LLAMA + "/v1/chat/completions", json=body)
    return JSONResponse(r.json(), status_code=r.status_code)
