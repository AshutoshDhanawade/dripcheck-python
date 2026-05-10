import random
from datetime import datetime
from typing import List, Dict, Optional, Tuple, Set
from api.models import WardrobeItem, ColorFamily, OccasionType, Category, OutfitBundle

# ==========================================
# PART 1: Color System
# ==========================================

PRIMARY_COLOR_TO_FAMILY: Dict[str, ColorFamily] = {
    # Neutral
    'White': ColorFamily.NEUTRAL, 'Black': ColorFamily.NEUTRAL, 'Grey': ColorFamily.NEUTRAL, 'Beige': ColorFamily.NEUTRAL,
    'Ivory': ColorFamily.NEUTRAL, 'Off-White': ColorFamily.NEUTRAL, 'Charcoal': ColorFamily.NEUTRAL,
    # Earth
    'Brown': ColorFamily.EARTH, 'Camel': ColorFamily.EARTH, 'Khaki': ColorFamily.EARTH, 'Olive': ColorFamily.EARTH,
    'Tan': ColorFamily.EARTH, 'Rust': ColorFamily.EARTH, 'Terracotta': ColorFamily.EARTH,
    # Dark / Cool
    'Navy': ColorFamily.DARK, 'Dark Green': ColorFamily.DARK, 'Burgundy': ColorFamily.DARK,
    'Slate': ColorFamily.DARK, 'Midnight Blue': ColorFamily.DARK,
    # Bold / Vibrant
    'Red': ColorFamily.BOLD, 'Yellow': ColorFamily.BOLD, 'Cobalt Blue': ColorFamily.BOLD, 'Fuchsia': ColorFamily.BOLD,
    'Orange': ColorFamily.BOLD, 'Neon Green': ColorFamily.BOLD, 'Purple': ColorFamily.BOLD,
    # Pastel
    'Baby Pink': ColorFamily.PASTEL, 'Mint': ColorFamily.PASTEL, 'Lavender': ColorFamily.PASTEL,
    'Baby Blue': ColorFamily.PASTEL, 'Blush': ColorFamily.PASTEL, 'Peach': ColorFamily.PASTEL,
    # Warm / Mid
    'Mustard': ColorFamily.WARM, 'Sage Green': ColorFamily.WARM, 'Dusty Rose': ColorFamily.WARM,
    'Mauve': ColorFamily.WARM, 'Warm Beige': ColorFamily.WARM,
}

def get_harmony_tier(color1: ColorFamily, color2: ColorFamily) -> int:
    pair_list = sorted([color1, color2])
    pair = f"{pair_list[0]}+{pair_list[1]}"

    if pair == 'Neutral+Neutral': return 2
    if pair == 'Bold+Neutral': return 3
    if pair == 'Dark+Neutral': return 3
    if pair == 'Earth+Neutral': return 3
    if pair == 'Neutral+Pastel': return 3
    if pair == 'Neutral+Warm': return 2
    if pair == 'Earth+Earth': return 2
    if pair == 'Dark+Earth': return 1 # Earth + Dark/Cool
    if pair == 'Earth+Warm': return 1 # Warm + Earth
    if pair == 'Dark+Dark': return 2
    if pair == 'Bold+Bold': return 0 # Blocked
    if pair == 'Pastel+Pastel': return 2
    if pair == 'Bold+Pastel': return 0 # Blocked

    if color1 == color2:
        return 2
    return 3

# ==========================================
# PART 3: Dominant Color
# ==========================================

def compute_dominant_color(items: List[WardrobeItem]) -> dict:
    weights = {
        Category.TOP: 3,
        Category.BOTTOM: 3,
        Category.LAYER: 2,
        Category.FOOTWEAR: 1,
        Category.ACCESSORY: 0.5
    }

    color_scores: Dict[str, float] = {}

    for item in items:
        weight = weights.get(item.category, 1)
        color = item.primary_color
        color_scores[color] = color_scores.get(color, 0) + weight

    max_score = 0.0
    dominant_colors: List[str] = []

    for color, score in color_scores.items():
        if score > max_score:
            max_score = score
            dominant_colors = [color]
        elif score == max_score:
            dominant_colors.append(color)

    final_color_str = " / ".join(dominant_colors)
    final_palette = PRIMARY_COLOR_TO_FAMILY.get(dominant_colors[0], ColorFamily.NEUTRAL)

    return {
        "color": final_color_str,
        "palette": final_palette
    }

# ==========================================
# PART 2: Scoring
# ==========================================

def calculate_compatibility_score(items: List[WardrobeItem]) -> dict:
    if len(items) < 2:
        return {"score": 0, "is_valid": False, "rejection_reason": "not_enough_items"}

    # HARD REJECT R1: Formality gap >= 3
    formalities = [i.formality_level for i in items]
    min_f, max_f = min(formalities), max(formalities)
    if max_f - min_f >= 3:
        return {"score": 0, "is_valid": False, "rejection_reason": "formality_gap"}

    # HARD REJECT R2: Season mismatch
    specific_seasons = set(i.season for i in items if i.season != 'All-season')
    if len(specific_seasons) > 1:
        return {"score": 0, "is_valid": False, "rejection_reason": "season_mismatch"}

    # HARD REJECT R3: Pattern conflict
    patterned_items = [i for i in items if i.pattern != 'Solid']
    if len(patterned_items) >= 2:
        has_graphic = any(i.pattern == 'Graphic' for i in patterned_items)
        if has_graphic:
            return {"score": 0, "is_valid": False, "rejection_reason": "pattern_conflict"}
        complex_patterns = {'Stripes', 'Checks', 'Floral', 'Abstract'}
        complex_count = sum(1 for i in patterned_items if i.pattern in complex_patterns)
        if complex_count >= 2:
            return {"score": 0, "is_valid": False, "rejection_reason": "pattern_conflict"}

    # HARD REJECT R4: Color clash
    highest_tier = 3
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            c1 = items[i].color_family or PRIMARY_COLOR_TO_FAMILY.get(items[i].primary_color, ColorFamily.NEUTRAL)
            c2 = items[j].color_family or PRIMARY_COLOR_TO_FAMILY.get(items[j].primary_color, ColorFamily.NEUTRAL)
            tier = get_harmony_tier(c1, c2)

            if tier == 0:
                return {"score": 0, "is_valid": False, "rejection_reason": "color_clash"}

            if tier == 1 and highest_tier > 1: highest_tier = 1
            if tier == 2 and highest_tier > 2: highest_tier = 2

    # SCORING
    score = 0

    # Occasion Match
    common_occasions = set(items[0].occasion_type)
    for i in range(1, len(items)):
        common_occasions.intersection_update(items[i].occasion_type)
    
    if common_occasions:
        score += 25

    # Color Harmony Points
    if highest_tier == 1: score += 30
    elif highest_tier == 2: score += 20
    elif highest_tier == 3: score += 10

    # Pattern Balance
    if len(patterned_items) == 0:
        score += 10
    elif len(patterned_items) == 1:
        score += 15

    # Fit Harmony
    top = next((i for i in items if i.category == 'Top'), None)
    bottom = next((i for i in items if i.category == 'Bottom'), None)
    if top and bottom:
        if top.fit == 'Oversized' and bottom.fit in ['Slim', 'Tapered']:
            score += 10
        elif top.fit == 'Oversized' and bottom.fit in ['Baggy', 'Oversized']:
            score -= 10

    # Brand Cohesion
    brands = [i.brand for i in items if i.brand]
    brand_counts = {}
    has_brand_cohesion = False
    for b in brands:
        brand_counts[b] = brand_counts.get(b, 0) + 1
        if brand_counts[b] >= 2:
            has_brand_cohesion = True
    
    if has_brand_cohesion:
        score += 5

    # Footwear Presence
    has_footwear = any(i.category == 'Footwear' for i in items)
    if has_footwear:
        score += 5

    # Formality penalty for gap of 2 (exempting 'versatile'/'smart casual' tags)
    standard_items = []
    for i in items:
        tags = [t.lower() for t in (i.style_tags or [])]
        if 'versatile' not in tags and 'smart casual' not in tags:
            standard_items.append(i)

    if len(standard_items) >= 2:
        standard_formalities = [i.formality_level for i in standard_items]
        standard_min_f = min(standard_formalities)
        standard_max_f = max(standard_formalities)
        if standard_max_f - standard_min_f == 2:
            score -= 15

    # Cap score
    score = min(100, max(0, score))

    return {"score": score, "is_valid": True}

# ==========================================
# PART 4: Style Tag Assignment
# ==========================================

def assign_style_tags(items: List[WardrobeItem]) -> List[dict]:
    result = []
    
    tags_config = [
        {
            'name': 'Minimalist',
            'rules': [
                lambda: sum(1 for i in items if i.pattern == 'Solid') >= 2,
                lambda: all(i.color_family == 'Neutral' or PRIMARY_COLOR_TO_FAMILY.get(i.primary_color, ColorFamily.NEUTRAL) == 'Neutral' for i in items),
                lambda: all(i.fit not in ['Oversized', 'Baggy'] for i in items)
            ]
        },
        {
            'name': 'Streetwear',
            'rules': [
                lambda: any(i.fit in ['Oversized', 'Baggy'] for i in items),
                lambda: any(i.pattern == 'Graphic' for i in items),
                lambda: any(i.category == 'Footwear' and i.subcategory == 'Sneakers' for i in items)
            ]
        },
        {
            'name': 'Sporty/Athleisure',
            'rules': [
                lambda: any(i.subcategory in ['Joggers', 'Leggings', 'Hoodie'] for i in items),
                lambda: any(i.material in ['Polyester', 'Spandex'] for i in items),
                lambda: any(i.category == 'Footwear' and i.subcategory == 'Running Shoes' for i in items)
            ]
        },
        {
            'name': 'Vintage/Retro',
            'rules': [
                lambda: any(i.pattern in ['Checks', 'Floral'] for i in items),
                lambda: any(i.primary_color in ['Mustard', 'Navy', 'Olive'] for i in items),
                lambda: any(i.fit in ['Relaxed', 'Oversized'] for i in items)
            ]
        },
        {
            'name': 'Bohemian/Boho',
            'rules': [
                lambda: any(i.material in ['Cotton', 'Linen'] for i in items),
                lambda: any(i.pattern in ['Floral', 'Abstract'] for i in items),
                lambda: all(i.color_family == 'Earth' for i in items),
                lambda: any(i.fit in ['Relaxed', 'Baggy', 'Oversized'] for i in items)
            ]
        },
        {
            'name': 'Classic/Timeless',
            'rules': [
                lambda: all(i.primary_color in ['Navy', 'White', 'Beige', 'Charcoal'] for i in items),
                lambda: all(i.fit in ['Slim', 'Regular'] for i in items),
                lambda: all(i.pattern == 'Solid' for i in items)
            ]
        },
        {
            'name': 'Business Casual',
            'rules': [
                lambda: any(i.subcategory in ['Chinos', 'Blazer'] for i in items),
                lambda: any(i.category == 'Footwear' and i.subcategory in ['Loafers', 'Oxfords'] for i in items),
                lambda: all(i.color_family in ['Neutral', 'Dark'] or PRIMARY_COLOR_TO_FAMILY.get(i.primary_color, ColorFamily.NEUTRAL) in ['Neutral', 'Dark'] for i in items)
            ]
        },
        {
            'name': 'Y2K',
            'rules': [
                lambda: any(i.primary_color in ['Baby Pink', 'Silver', 'Neon Green'] for i in items),
                lambda: any(i.subcategory in ['Crop Top', 'Tank Top'] for i in items),
                lambda: any(i.pattern in ['Graphic', 'Abstract'] for i in items)
            ]
        },
        {
            'name': 'Preppy',
            'rules': [
                lambda: any(i.subcategory in ['Polo', 'Blazer'] for i in items),
                lambda: any(i.primary_color in ['Navy', 'Burgundy', 'Dark Green'] for i in items),
                lambda: any(i.pattern in ['Stripes', 'Checks'] for i in items)
            ]
        },
        {
            'name': 'Grunge',
            'rules': [
                lambda: any(i.primary_color in ['Black', 'Dark Green', 'Burgundy'] for i in items),
                lambda: any(i.subcategory == 'Shirt' and i.pattern == 'Checks' for i in items),
                lambda: any(i.subcategory in ['Jeans', 'Boots'] for i in items)
            ]
        },
        {
            'name': 'Monochrome',
            'rules': [
                lambda: len(set(i.primary_color for i in items)) == 1 if items else False,
                lambda: len(set(i.color_family or PRIMARY_COLOR_TO_FAMILY.get(i.primary_color, ColorFamily.NEUTRAL) for i in items)) == 1 if items else False
            ]
        },
        {
            'name': 'Techwear',
            'rules': [
                lambda: all(i.primary_color in ['Black', 'Grey'] for i in items),
                lambda: any(i.subcategory in ['Jacket', 'Boots'] for i in items),
                lambda: any(i.material in ['Polyester', 'Nylon'] for i in items)
            ]
        },
        {
            'name': 'Cottagecore',
            'rules': [
                lambda: any(i.primary_color in ['Ivory', 'Lavender', 'Sage Green'] for i in items),
                lambda: any(i.pattern in ['Floral', 'Checks'] for i in items),
                lambda: any(i.material in ['Cotton', 'Linen'] for i in items)
            ]
        },
        {
            'name': 'Bold/Statement',
            'rules': [
                lambda: any(i.primary_color in ['Red', 'Yellow', 'Cobalt Blue', 'Fuchsia', 'Neon Green'] for i in items),
                lambda: any(i.pattern in ['Graphic', 'Abstract'] for i in items),
                lambda: any(i.fit == 'Oversized' for i in items)
            ]
        },
        {
            'name': 'Layered',
            'rules': [
                lambda: sum(1 for i in items if i.category in ['Top', 'Layer', 'Accessory']) >= 3,
                lambda: any(i.category == 'Layer' for i in items),
                lambda: any(i.category == 'Accessory' for i in items)
            ]
        }
    ]

    for tag in tags_config:
        matched = sum(1 for rule in tag['rules'] if rule())
        confidence = matched / len(tag['rules'])
        if confidence >= 0.5:
            result.append({'name': tag['name'], 'confidence': round(confidence, 2)})

    return sorted(result, key=lambda x: x['confidence'], reverse=True)

# ==========================================
# PART 5: Bundle Generator
# ==========================================

def generate_bundles(
    user_id: str,
    wardrobe_items: List[WardrobeItem],
    occasion_filter: Optional[OccasionType] = None,
    avoided_colors: List[str] = None
) -> List[dict]:
    if avoided_colors is None:
        avoided_colors = []

    initial_pool = wardrobe_items

    if avoided_colors:
        avoided_lower = [c.lower() for c in avoided_colors]
        filtered_pool = []
        for item in initial_pool:
            p_color_family = PRIMARY_COLOR_TO_FAMILY.get(item.primary_color, ColorFamily.NEUTRAL)
            if item.primary_color.lower() not in avoided_lower and p_color_family.lower() not in avoided_lower:
                filtered_pool.append(item)
        initial_pool = filtered_pool

    if occasion_filter:
        initial_pool = [i for i in initial_pool if occasion_filter in i.occasion_type]

    tops = [i for i in initial_pool if i.category == 'Top']
    bottoms = [i for i in initial_pool if i.category == 'Bottom']
    shoes = [i for i in initial_pool if i.category == 'Footwear']
    layers = [i for i in initial_pool if i.category == 'Layer']

    valid_combinations = []

    for top in tops:
        for bottom in bottoms:
            for shoe in shoes:
                current_combo = [top, bottom, shoe]
                base_eval = calculate_compatibility_score(current_combo)

                if not base_eval['is_valid']:
                    continue

                final_combo = current_combo.copy()
                final_score = base_eval['score']

                best_layer = None
                best_score = base_eval['score']

                for layer in layers:
                    test_combo = current_combo + [layer]
                    test_eval = calculate_compatibility_score(test_combo)
                    if test_eval['is_valid'] and test_eval['score'] > best_score:
                        best_score = test_eval['score']
                        best_layer = layer

                if best_layer:
                    final_combo.append(best_layer)
                    final_score = best_score

                dom_color_result = compute_dominant_color(final_combo)
                style_tags_result = assign_style_tags(final_combo)

                valid_combinations.append({
                    'items': final_combo,
                    'score': final_score,
                    'dominantColor': dom_color_result['color'],
                    'dominantPalette': dom_color_result['palette'],
                    'tags': style_tags_result
                })

    valid_combinations.sort(key=lambda x: x['score'], reverse=True)
    top_10 = valid_combinations[:10]

    bundles = []
    for combo in top_10:
        rand_str = ''.join(random.choices('0123456789abcdefghijklmnopqrstuvwxyz', k=7))
        occ_tags = list(set([occ for item in combo['items'] for occ in item.occasion_type]))
        if occasion_filter:
            occ_tags = [tag for tag in occ_tags if tag == occasion_filter]
        
        mood_tags_set = set()
        for item in combo['items']:
            if item.mood_tags:
                mood_tags_set.update(item.mood_tags)

        bundles.append(OutfitBundle(
            bundle_id=f"GEN-{rand_str}",
            user_id=user_id,
            items=[i.item_id for i in combo['items']],
            compatibility_score=combo['score'],
            dominant_color=combo['dominantColor'],
            dominant_palette=combo['dominantPalette'],
            occasion_tags=occ_tags,
            style_tags=[t['name'] for t in combo['tags'][:2]],
            mood_tags=list(mood_tags_set)[:2],
            is_saved=False,
            wear_count=0,
            source='user_generated',
            created_at=datetime.utcnow().isoformat() + 'Z'
        ))

    return bundles
