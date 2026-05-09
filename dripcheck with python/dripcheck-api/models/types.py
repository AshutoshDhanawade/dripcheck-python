from enum import Enum
from typing import List, Optional, Dict, Literal
from pydantic import BaseModel, Field

class Category(str, Enum):
    TOP = 'Top'
    BOTTOM = 'Bottom'
    FOOTWEAR = 'Footwear'
    LAYER = 'Layer'
    ACCESSORY = 'Accessory'

class ColorFamily(str, Enum):
    NEUTRAL = 'Neutral'
    EARTH = 'Earth'
    DARK = 'Dark'
    BOLD = 'Bold'
    PASTEL = 'Pastel'
    WARM = 'Warm'

class Pattern(str, Enum):
    SOLID = 'Solid'
    STRIPES = 'Stripes'
    CHECKS = 'Checks'
    GRAPHIC = 'Graphic'
    FLORAL = 'Floral'
    ABSTRACT = 'Abstract'

class Fit(str, Enum):
    SLIM = 'Slim'
    REGULAR = 'Regular'
    RELAXED = 'Relaxed'
    OVERSIZED = 'Oversized'
    CROPPED = 'Cropped'
    BAGGY = 'Baggy'
    TAPERED = 'Tapered'

class OccasionType(str, Enum):
    CASUAL = 'Casual'
    FORMAL = 'Formal'
    BUSINESS = 'Business'
    PARTY = 'Party'
    GYM = 'Gym'
    DATE_NIGHT = 'Date Night'
    WEEKEND = 'Weekend'

class Season(str, Enum):
    SUMMER = 'Summer'
    WINTER = 'Winter'
    MONSOON = 'Monsoon'
    ALL_SEASON = 'All-season'

class StyleTag(str, Enum):
    MINIMALIST = 'Minimalist'
    STREETWEAR = 'Streetwear'
    SPORTY = 'Sporty'
    VINTAGE = 'Vintage'
    BOHEMIAN = 'Bohemian'
    CLASSIC = 'Classic'
    BUSINESS_CASUAL = 'Business Casual'
    Y2K = 'Y2K'
    PREPPY = 'Preppy'
    GRUNGE = 'Grunge'
    MONOCHROME = 'Monochrome'
    TECHWEAR = 'Techwear'
    COTTAGECORE = 'Cottagecore'
    BOLD = 'Bold'
    LAYERED = 'Layered'
    DESIGNER = 'Designer'

class WardrobeItem(BaseModel):
    item_id: str
    user_id: str
    name: str
    category: Category
    subcategory: str
    primary_color: str
    secondary_color: Optional[str] = None
    color_family: ColorFamily
    pattern: Pattern
    fit: Fit
    occasion_type: List[OccasionType]
    season: Season
    formality_level: int = Field(ge=1, le=5)
    brand: Optional[str] = None
    material: Optional[str] = None
    style_tags: Optional[List[str]] = None
    mood_tags: Optional[List[str]] = None
    aesthetic_tone: Optional[str] = None
    wear_count: int = 0
    last_worn: Optional[str] = None
    image_url: Optional[str] = None
    added_at: str

class OutfitBundle(BaseModel):
    bundle_id: str
    user_id: str
    items: List[str]
    compatibility_score: float
    dominant_color: str
    dominant_palette: str
    occasion_tags: List[str]
    style_tags: List[str]
    mood_tags: List[str]
    is_saved: bool = False
    wear_count: int = 0
    source: Literal['user_generated', 'marketplace_inspiration']
    has_missing_item: Optional[bool] = None
    created_at: str

class WearLog(BaseModel):
    log_id: str
    user_id: str
    bundle_id: Optional[str] = None
    item_ids: List[str]
    occasion_tag: str
    worn_date: str
    notes: Optional[str] = None

class UserProfile(BaseModel):
    user_id: str
    username: str
    email: str
    skin_tone: str
    hair_color: str
    body_type: str
    daily_routines: List[str]
    occasion_frequency: Dict[str, str]
    style_vibes: List[str]
    favorite_colors: List[str]
    avoided_colors: List[str]
    fit_preferences: List[str]
    material_sensitivity: List[str]
    pattern_preferences: List[str]
    onboarding_complete: bool
    created_at: str

class MarketplaceItem(BaseModel):
    name: str
    brand: str
    price: float
    category: str
    image_url: str

class MarketplaceBundle(BaseModel):
    bundle_id: str
    title: str
    description: str
    items: List[MarketplaceItem]
    total_price: float
    match_percentage: float
    occasion_tags: List[str]
    style_tags: List[str]
    source: Literal['marketplace']
