import random
from datetime import datetime
from typing import List, Dict, Optional, Tuple, Set
from api.models import WardrobeItem, ColorFamily, OccasionType, Category, OutfitBundle
from services.occasion_taxonomy import (
    derive_bundle_occasions,
    expand_occasion_list,
    normalize_occasion_list,
)

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
    occasion_filter: Optional[object] = None,
    avoided_colors: List[str] = None
) -> List[dict]:
    if avoided_colors is None:
        avoided_colors = []

    # Occasion filter: accept a single occasion or a list, expand through the
    # hierarchy (a parent request matches every descendant child, and a child
    # request matches its implied parent).
    expanded_occasions: Optional[Set[str]] = None
    if occasion_filter:
        filters = occasion_filter if isinstance(occasion_filter, (list, tuple, set)) else [occasion_filter]
        expanded_occasions = expand_occasion_list(filters)

    initial_pool = wardrobe_items

    if avoided_colors:
        avoided_lower = [c.lower() for c in avoided_colors]
        filtered_pool = []
        for item in initial_pool:
            p_color_family = PRIMARY_COLOR_TO_FAMILY.get(item.primary_color, ColorFamily.NEUTRAL)
            if item.primary_color.lower() not in avoided_lower and p_color_family.lower() not in avoided_lower:
                filtered_pool.append(item)
        initial_pool = filtered_pool

    if expanded_occasions is not None:
        initial_pool = [
            i for i in initial_pool
            if expanded_occasions & set(normalize_occasion_list(i.occasion_type))
        ]

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

    bundles = []
    for combo in valid_combinations:
        rand_str = ''.join(random.choices('0123456789abcdefghijklmnopqrstuvwxyz', k=7))
        # Bundle occasions are DERIVED from the constituent items' occasions
        # (intersection -> majority -> union), never a blind union, and never
        # sent back to Gemini. Parent tags are implied automatically.
        occ_tags = derive_bundle_occasions([
            getattr(item, 'occasion_type', None) or [] for item in combo['items']
        ])
        if expanded_occasions is not None:
            occ_tags = [tag for tag in occ_tags if tag in expanded_occasions]
        
        mood_tags_set = set()
        for item in combo['items']:
            if item.mood_tags:
                mood_tags_set.update(item.mood_tags)

        bundles.append(OutfitBundle(
            bundle_id=f"GEN-{rand_str}",
            user_id=None,
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


# ==========================================
# PART 6: Diversity / Similarity
# ==========================================

# Configurable penalties applied at selection time. The base bundle score is
# 0–100, so top/bottom identity dominates: two bundles sharing the same top
# AND bottom are visually the same outfit with different footwear and must
# not both crowd the top of the UI.
DIVERSITY_PENALTIES = {
    'same_top': 20,
    'same_bottom': 20,
    'same_layer': 5,
    'same_footwear': 10,
    'same_color': 5,
    'same_style': 5,
    'same_fit': 5,
    'same_occasion': 3,
}


def bundle_diversity_profile(bundle, item_lookup=None) -> dict:
    """Precompute a normalized similarity profile for one bundle.

    Profiles are built once per bundle and reused for every comparison against
    the selected set, so no database access is needed during re-ranking.
    ``item_lookup`` maps item ids to ``WardrobeItem`` objects so the bundle's
    top/bottom/footwear/layer slots and visual attributes can be resolved.
    Bundle-level attributes (style_tags, occasion_tags, dominant palette/color)
    are used as fallbacks when item objects are unavailable.
    """
    slots = {'Top': set(), 'Bottom': set(), 'Footwear': set(), 'Layer': set()}
    colors: set[str] = set()
    styles: set[str] = set()
    fits: set[str] = set()
    occasions: set[str] = set()
    item_ids: set[str] = set()

    for item_id in (getattr(bundle, 'items', None) or []):
        str_id = str(item_id)
        item_ids.add(str_id)
        item = item_lookup.get(str_id) if item_lookup else None
        if item is None:
            continue
        category = getattr(item, 'category', None)
        if category in slots:
            slots[category].add(str_id)

        primary = getattr(item, 'primary_color', '') or ''
        if primary:
            colors.add(str(primary).strip().lower())
        for tag in (getattr(item, 'style_tags', None) or []):
            if tag:
                styles.add(str(tag).strip().lower())
        fit = getattr(item, 'fit', None)
        if fit:
            fits.add(str(fit).strip().lower())
        for occ in (getattr(item, 'occasion_type', None) or []):
            if occ:
                occasions.add(str(occ).strip().lower())

    # Bundle-level attribute fallbacks.
    for tag in (getattr(bundle, 'style_tags', None) or []):
        if tag:
            styles.add(str(tag).strip().lower())
    for occ in (getattr(bundle, 'occasion_tags', None) or []):
        if occ:
            occasions.add(str(occ).strip().lower())
    palette = getattr(bundle, 'dominant_palette', None)
    if palette:
        colors.add(str(palette).strip().lower())
    dominant = getattr(bundle, 'dominant_color', None)
    if dominant:
        colors.add(str(dominant).strip().lower())

    return {
        'top': slots['Top'],
        'bottom': slots['Bottom'],
        'layer': slots['Layer'],
        'footwear': slots['Footwear'],
        'colors': colors,
        'styles': styles,
        'fits': fits,
        'occasions': occasions,
        'item_ids': item_ids,
    }


def similarity_penalty_between(
    profile_a: dict,
    profile_b: dict,
    penalties: Optional[dict] = None,
) -> tuple:
    """Penalty (and component breakdown) for comparing two bundle profiles.

    Returns ``(penalty, breakdown)`` where ``breakdown`` maps each similarity
    component (same_top, same_bottom, ...) to a boolean. Only the highest
    contribution per component matters; attributes absent from a profile simply
    contribute nothing instead of guessing.
    """
    effective = dict(DIVERSITY_PENALTIES)
    if penalties:
        effective.update(penalties)

    breakdown = {
        'same_top': bool(profile_a['top'] & profile_b['top']),
        'same_bottom': bool(profile_a['bottom'] & profile_b['bottom']),
        'same_layer': bool(profile_a['layer'] & profile_b['layer']),
        'same_footwear': bool(profile_a['footwear'] & profile_b['footwear']),
        'same_color': bool(profile_a['colors'] & profile_b['colors']),
        'same_style': bool(profile_a['styles'] & profile_b['styles']),
        'same_fit': bool(profile_a['fits'] & profile_b['fits']),
        'same_occasion': bool(profile_a['occasions'] & profile_b['occasions']),
    }

    # Identity fallback: when slots could not be resolved (no item_lookup),
    # an identical item-id composition is still treated as same top+bottom+shoe.
    slot_keys = ('same_top', 'same_bottom', 'same_footwear', 'same_layer')
    if not any(breakdown[k] for k in slot_keys):
        if profile_a['item_ids'] and profile_a['item_ids'] == profile_b['item_ids']:
            breakdown['same_top'] = True
            breakdown['same_bottom'] = True
            breakdown['same_footwear'] = True

    penalty = sum(effective[key] for key, matched in breakdown.items() if matched)
    return penalty, breakdown


def diversity_breakdown_penalties(
    breakdown: dict,
    penalties: Optional[dict] = None,
) -> dict:
    """Map a boolean similarity breakdown to the numeric penalty per component.

    Each matched component contributes its configured ``DIVERSITY_PENALTIES``
    value (0 when unmatched), so the numeric breakdown always sums back to the
    total penalty: ``sum(values) == similarity_penalty_between(...)[0]``.

    This is purely presentational — it reuses the exact penalty constants the
    similarity calculation already applied, it does not compute new penalties.
    """
    effective = dict(DIVERSITY_PENALTIES)
    if penalties:
        effective.update(penalties)
    return {
        key: (effective[key] if matched else 0)
        for key, matched in (breakdown or {}).items()
    }


def recommend_bundle_for_anchor(
    anchor_item: WardrobeItem,
    wardrobe_items: List[WardrobeItem],
    max_per_category: Optional[int] = None
) -> dict:
    """Find the strongest outfit bundle anchored on a user-uploaded item.

    Reuses the existing compatibility scoring engine to keep recommendation logic
    consistent with the rest of the application. Every eligible complement item
    is considered (no per-category cap unless ``max_per_category`` is set).
    """
    complement_map = {
        'Top': ['Bottom', 'Footwear'],
        'Bottom': ['Top', 'Footwear'],
        'Footwear': ['Top', 'Bottom'],
    }
    required_categories = complement_map.get(anchor_item.category, ['Top', 'Bottom', 'Footwear'])
    optional_category = 'Layer'

    categories = required_categories + [optional_category]
    grouped: dict[str, list[WardrobeItem]] = {}
    for cat in categories:
        items_for_cat = [item for item in wardrobe_items if item.category == cat]
        if max_per_category:
            items_for_cat = items_for_cat[:max_per_category]
        grouped[cat] = items_for_cat

    def iter_combinations(categories_left: list[str], current: list[WardrobeItem]):
        if not categories_left:
            yield current
            return

        category = categories_left[0]
        candidates = grouped.get(category, [])
        if not candidates:
            yield from iter_combinations(categories_left[1:], current)
            return

        for item in candidates:
            yield from iter_combinations(categories_left[1:], current + [item])

    best_bundle = None
    best_score = 0
    best_items = []
    all_valid_combos = []

    for combo in iter_combinations(required_categories, [anchor_item]):
        if len(combo) != len(required_categories) + 1:
            continue
        result = calculate_compatibility_score(combo)
        if not result['is_valid']:
            continue
        all_valid_combos.append((result['score'], combo))

        # Try optional layer if available
        for layer_item in grouped.get(optional_category, []):
            layered_combo = combo + [layer_item]
            layered_result = calculate_compatibility_score(layered_combo)
            if layered_result['is_valid']:
                all_valid_combos.append((layered_result['score'], layered_combo))

    if not all_valid_combos:
        return {
            'recommended_bundle': {},
            'matching_score': 0.0,
            'items': [],
            'has_recommendations': False,
        }

    best_score, best_items = max(all_valid_combos, key=lambda pair: pair[0])

    bundle = {
        'topwear': None,
        'bottomwear': None,
        'footwear': None,
        'outerwear': None,
    }

    category_key_map = {
        'Top': 'topwear',
        'Bottom': 'bottomwear',
        'Footwear': 'footwear',
        'Layer': 'outerwear',
    }

    for item in best_items:
        slot = category_key_map.get(item.category)
        if slot:
            bundle[slot] = item

    return {
        'recommended_bundle': bundle,
        'matching_score': round(best_score / 100, 2),
        'items': best_items,
        'has_recommendations': True,
    }
