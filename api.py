from typing import Optional

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import config
from main import run_recommend

app = FastAPI(title="Bangumi 推荐系统", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/recommend")
async def recommend(
    user_id: str = Query(..., description="Bangumi 用户 ID"),
    top_k: int = Query(20, ge=1, le=100, description="推荐数量"),
    use_cache: bool = Query(True, description="是否使用缓存"),
    token: Optional[str] = Query(None, description="API Access Token"),
):
    result = run_recommend(user_id, top_k, use_cache=use_cache, token=token)
    if "error" in result:
        return JSONResponse(status_code=404, content=result)
    return result


@app.get("/health")
async def health():
    return {"status": "ok"}
