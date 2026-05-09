from fastapi import FastAPI, HTTPException, Query
from typing import List, Optional
from fastapi.middleware.cors import CORSMiddleware

from models.types import OutfitBundle, MarketplaceBundle
import services.data_service as data_service

app = FastAPI(title="Dripcheck Bundle Generation API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/bundles/{user_id}", response_model=List[OutfitBundle])
async def get_bundles(user_id: str, occasion: Optional[str] = Query(None)):
    return await data_service.get_bundles(user_id, occasion)

@app.post("/api/bundles/{user_id}/save", response_model=OutfitBundle)
async def save_bundle(user_id: str, bundle: OutfitBundle):
    return await data_service.save_bundle_for_user(user_id, bundle)

@app.get("/api/marketplace", response_model=List[MarketplaceBundle])
async def get_marketplace_bundles(occasion: Optional[str] = Query(None), style: Optional[str] = Query(None)):
    return await data_service.get_marketplace_bundles(occasion_tag=occasion, style_tag=style)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("bundlegeneration:app", host="0.0.0.0", port=8001, reload=True)
