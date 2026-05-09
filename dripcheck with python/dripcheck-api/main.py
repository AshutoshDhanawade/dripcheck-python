from fastapi import FastAPI, HTTPException, Query
from typing import List, Optional, Any
from fastapi.middleware.cors import CORSMiddleware

from models.types import WardrobeItem, UserProfile, WearLog
import services.data_service as data_service

app = FastAPI(title="Dripcheck API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/wardrobe/{user_id}", response_model=List[WardrobeItem])
async def get_wardrobe(user_id: str):
    return await data_service.get_wardrobe_items(user_id)

@app.post("/api/wardrobe/{user_id}", response_model=WardrobeItem)
async def add_wardrobe_item(user_id: str, item: dict):
    return await data_service.add_wardrobe_item(user_id, item)

@app.put("/api/wardrobe/{user_id}/{item_id}", response_model=WardrobeItem)
async def update_wardrobe_item(user_id: str, item_id: str, patch: dict):
    try:
        return await data_service.update_wardrobe_item(user_id, item_id, patch)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@app.delete("/api/wardrobe/{user_id}/{item_id}")
async def delete_wardrobe_item(user_id: str, item_id: str):
    await data_service.delete_wardrobe_item(user_id, item_id)
    return {"status": "success"}

@app.get("/api/users/{user_id}", response_model=UserProfile)
async def get_user_profile(user_id: str):
    try:
        return await data_service.get_user_profile(user_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@app.put("/api/users/{user_id}", response_model=UserProfile)
async def update_user_profile(user_id: str, patch: dict):
    return await data_service.update_user_profile(user_id, patch)


@app.get("/api/analytics/{user_id}")
async def get_analytics(user_id: str):
    return await data_service.get_analytics(user_id)

@app.get("/api/wearlog/{user_id}", response_model=List[WearLog])
async def get_wear_log(user_id: str):
    return await data_service.get_wear_log(user_id)

@app.post("/api/wearlog/{user_id}", response_model=WearLog)
async def log_wear(user_id: str, data: dict):
    bundle_id = data.get("bundle_id")
    date = data.get("worn_date")
    occasion = data.get("occasion_tag")
    if not date or not occasion:
        raise HTTPException(status_code=400, detail="Missing worn_date or occasion_tag")
    return await data_service.log_wear(user_id, bundle_id, date, occasion)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
