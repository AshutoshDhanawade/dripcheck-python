import uuid
from typing import List, Optional, Dict, Any

from models.types import WardrobeItem, OutfitBundle, WearLog, UserProfile, MarketplaceBundle, OccasionType
from data.mock_wardrobe import mock_wardrobe_items
from data.mock_bundles import mock_pre_generated_bundles
from data.mock_users import mock_users
from data.mock_marketplace import mock_marketplace_bundles
from engine.compatibility_engine import generate_bundles

_wardrobe: List[WardrobeItem] = list(mock_wardrobe_items)
_bundles: List[OutfitBundle] = list(mock_pre_generated_bundles)
_users: List[UserProfile] = list(mock_users)
_marketplace: List[MarketplaceBundle] = list(mock_marketplace_bundles)
_wear_log: List[WearLog] = []

async def get_wardrobe_items(user_id: str) -> List[WardrobeItem]:
    return [item for item in _wardrobe if item.user_id == user_id]

async def add_wardrobe_item(user_id: str, item_data: dict) -> WardrobeItem:
    from datetime import datetime
    new_item_dict = {
        **item_data,
        "item_id": str(uuid.uuid4()),
        "user_id": user_id,
        "added_at": datetime.utcnow().isoformat() + 'Z',
        "wear_count": 0
    }
    new_item = WardrobeItem(**new_item_dict)
    _wardrobe.append(new_item)
    return new_item

async def update_wardrobe_item(user_id: str, item_id: str, patch: dict) -> WardrobeItem:
    for i, item in enumerate(_wardrobe):
        if item.item_id == item_id and item.user_id == user_id:
            updated_dict = item.dict()
            updated_dict.update(patch)
            updated_item = WardrobeItem(**updated_dict)
            _wardrobe[i] = updated_item
            return updated_item
    raise ValueError("Item not found")

async def delete_wardrobe_item(user_id: str, item_id: str) -> None:
    global _wardrobe, _bundles
    _wardrobe = [item for item in _wardrobe if not (item.item_id == item_id and item.user_id == user_id)]
    
    for i, bundle in enumerate(_bundles):
        if bundle.user_id == user_id and item_id in bundle.items:
            _bundles[i].has_missing_item = True

async def get_bundles(user_id: str, occasion_filter: Optional[str] = None) -> List[OutfitBundle]:
    stored_bundles = [b for b in _bundles if b.user_id == user_id]
    if occasion_filter:
        stored_bundles = [b for b in stored_bundles if occasion_filter in b.occasion_tags]

    user_wardrobe = [i for i in _wardrobe if i.user_id == user_id]
    user = next((u for u in _users if u.user_id == user_id), None)
    avoided = user.avoided_colors if user else []

    occ_enum = None
    if occasion_filter:
        for oc in OccasionType:
            if oc.value == occasion_filter:
                occ_enum = oc
                break

    generated_bundles = generate_bundles(user_id, user_wardrobe, occ_enum, avoided)

    all_bundles = stored_bundles + generated_bundles

    seen = set()
    deduplicated = []

    for b in all_bundles:
        key = ",".join(sorted(b.items))
        if key not in seen:
            seen.add(key)
            deduplicated.append(b)

    deduplicated.sort(key=lambda b: b.compatibility_score, reverse=True)
    return deduplicated[:10]

async def save_bundle_for_user(user_id: str, bundle: OutfitBundle) -> OutfitBundle:
    for i, b in enumerate(_bundles):
        if b.bundle_id == bundle.bundle_id and b.user_id == user_id:
            _bundles[i].is_saved = True
            return _bundles[i]
    
    bundle.user_id = user_id
    bundle.is_saved = True
    _bundles.append(bundle)
    return bundle

async def log_wear(user_id: str, bundle_id: Optional[str], date: str, occasion: str) -> WearLog:
    item_ids = []
    
    if bundle_id:
        bundle = next((b for b in _bundles if b.bundle_id == bundle_id), None)
        if bundle:
            bundle.wear_count += 1
            item_ids = bundle.items
            
    for item_id in item_ids:
        item = next((i for i in _wardrobe if i.item_id == item_id and i.user_id == user_id), None)
        if item:
            item.wear_count += 1
            item.last_worn = date

    new_log = WearLog(
        log_id=str(uuid.uuid4()),
        user_id=user_id,
        bundle_id=bundle_id,
        item_ids=item_ids,
        occasion_tag=occasion,
        worn_date=date
    )
    _wear_log.append(new_log)
    return new_log

async def get_wear_log(user_id: str) -> List[WearLog]:
    return [log for log in _wear_log if log.user_id == user_id]

async def get_user_profile(user_id: str) -> UserProfile:
    user = next((u for u in _users if u.user_id == user_id), None)
    if not user:
        raise ValueError("User not found")
    return user

async def get_all_users() -> List[UserProfile]:
    return list(_users)

async def create_user_profile(user: UserProfile) -> UserProfile:
    _users.append(user)
    return user

async def update_user_profile(user_id: str, patch: dict) -> UserProfile:
    for i, user in enumerate(_users):
        if user.user_id == user_id:
            updated_dict = user.dict()
            updated_dict.update(patch)
            updated_user = UserProfile(**updated_dict)
            _users[i] = updated_user
            return updated_user
            
    new_user = UserProfile(**patch)
    _users.append(new_user)
    return new_user

async def get_marketplace_bundles(occasion_tag: Optional[str] = None, style_tag: Optional[str] = None) -> List[MarketplaceBundle]:
    bundles = list(_marketplace)
    if occasion_tag:
        bundles = [b for b in bundles if occasion_tag in b.occasion_tags]
    if style_tag:
        bundles = [b for b in bundles if style_tag in b.style_tags]
    return bundles

async def get_analytics(user_id: str) -> Dict[str, Any]:
    user_wardrobe = [i for i in _wardrobe if i.user_id == user_id]
    total_items = len(user_wardrobe)
    never_worn_count = sum(1 for i in user_wardrobe if i.wear_count == 0)

    most_worn_item = None
    max_wear = -1
    for item in user_wardrobe:
        if item.wear_count > max_wear:
            max_wear = item.wear_count
            most_worn_item = item

    utilization_percentage = ((total_items - never_worn_count) / total_items * 100) if total_items > 0 else 0

    saved_bundles = [b for b in _bundles if b.user_id == user_id and b.is_saved]
    score_sum = sum(b.compatibility_score for b in saved_bundles)
    avg_score = score_sum / len(saved_bundles) if saved_bundles else 0

    occasion_distribution = {}
    for item in user_wardrobe:
        for occ in item.occasion_type:
            val = occ.value if hasattr(occ, 'value') else str(occ)
            occasion_distribution[val] = occasion_distribution.get(val, 0) + 1

    return {
        "total_items": total_items,
        "never_worn_count": never_worn_count,
        "most_worn_item": most_worn_item.dict() if most_worn_item else None,
        "utilization_percentage": utilization_percentage,
        "average_compatibility_score": round(avg_score, 2),
        "occasion_distribution": occasion_distribution
    }
