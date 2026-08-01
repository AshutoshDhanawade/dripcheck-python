import random

from api.models import Category
from bundle_generate.models import (
    TopwearAiRecommendation,
    BottomwearAiGeneration,
    FootwearAiRecommendation,
)
from engine.compatibility_engine import (
    calculate_compatibility_score,
    get_harmony_tier,
    PRIMARY_COLOR_TO_FAMILY,
)

AI_MODEL_MAP = {
    Category.TOP: TopwearAiRecommendation,
    Category.BOTTOM: BottomwearAiGeneration,
    Category.FOOTWEAR: FootwearAiRecommendation,
}

COMPLEMENT_CATEGORIES = {
    Category.TOP: [Category.BOTTOM, Category.FOOTWEAR],
    Category.BOTTOM: [Category.TOP, Category.FOOTWEAR],
    Category.FOOTWEAR: [Category.TOP, Category.BOTTOM],
}

ITEM_FIELDS = [
    'item_id',
    'name',
    'category',
    'subcategory',
    'primary_color',
    'secondary_color',
    'color_family',
    'pattern',
    'fit',
    'occasion_type',
    'season',
    'formality_level',
    'brand',
    'material',
    'style_tags',
    'mood_tags',
    'aesthetic_tone',
    'wear_count',
    'last_worn',
    'image_url',
    'original_image',
    'processed_image',
    'product_url',
    'ai_generated',
    'fallback_used',
    'added_at',
]


def serialize_item(item, is_ai=False):
    return {
        **{field: getattr(item, field, None) for field in ITEM_FIELDS},
        'is_ai': is_ai,
    }


def get_ai_candidates(category, user_id=None, occasion=None, season=None, excluded_ids=None, limit=20):
    model = AI_MODEL_MAP[category]
    queryset = model.objects.all()

    if occasion:
        queryset = queryset.filter(occasion_type__contains=occasion)
    if season:
        queryset = queryset.filter(season=season)
    if user_id:
        try:
            queryset = queryset.filter(user_id=int(user_id))
        except (TypeError, ValueError):
            pass
    if excluded_ids:
        queryset = queryset.exclude(item_id__in=excluded_ids)

    return list(queryset.order_by('-ai_generated', '-wear_count')[:limit])


def _harmony_label(tier):
    return {3: 'versatile', 2: 'well-matched', 1: 'complementary'}.get(tier, 'complementary')


def build_explanation(combo, score_result):
    if not score_result.get('is_valid'):
        reason = score_result.get('rejection_reason', 'unknown').replace('_', ' ')
        return f"Not compatible: {reason}."

    ai_item = combo[0]
    others = combo[1:]
    parts = [f"AI-picked {ai_item.name} styled with {', '.join(o.name for o in others)}."]

    tiers = []
    for i in range(len(combo)):
        for j in range(i + 1, len(combo)):
            c1 = combo[i].color_family or PRIMARY_COLOR_TO_FAMILY.get(combo[i].primary_color, 'Neutral')
            c2 = combo[j].color_family or PRIMARY_COLOR_TO_FAMILY.get(combo[j].primary_color, 'Neutral')
            tiers.append(get_harmony_tier(c1, c2))
    if tiers:
        parts.append(f"Color harmony is {_harmony_label(max(tiers))}.")

    common_occasions = set(combo[0].occasion_type)
    for item in others:
        common_occasions.intersection_update(item.occasion_type)
    if common_occasions:
        parts.append(f"Works for {', '.join(sorted(common_occasions)[:2])}.")

    formalities = [item.formality_level for item in combo]
    if max(formalities) - min(formalities) <= 1:
        parts.append("Formality levels are aligned.")

    return ' '.join(parts)


def build_bundle(combo, score_result):
    ai_item = combo[0]
    return {
        'bundle_id': 'AI-' + ''.join(random.choices('0123456789abcdefghijklmnopqrstuvwxyz', k=7)),
        'ai_item_id': ai_item.item_id,
        'match_score': score_result['score'],
        'explanation': build_explanation(combo, score_result),
        'items': [serialize_item(item, is_ai=(item is ai_item)) for item in combo],
    }


def generate_ai_bundles(category, wardrobe_items, ai_candidates, min_bundles=5, max_bundles=8, max_per_category=10):
    complement_categories = COMPLEMENT_CATEGORIES[category]

    def top_items(cat):
        return sorted(
            (item for item in wardrobe_items if item.category == cat),
            key=lambda i: (i.wear_count or 0, i.last_worn or ''),
            reverse=True,
        )[:max_per_category]

    first_items = top_items(complement_categories[0])
    second_items = top_items(complement_categories[1])

    if not first_items or not second_items:
        return None, None, f"User has no {'/'.join(complement_categories)} items in their wardrobe."

    valid_pairs = [
        (first, second)
        for first in first_items
        for second in second_items
        if calculate_compatibility_score([first, second])['is_valid']
    ]
    if not valid_pairs:
        return None, None, "No compatible combinations found in the user's wardrobe."

    candidates_combos = []
    best_ai_item = None
    best_score = -1

    for ai_item in ai_candidates:
        combos = []
        for first, second in valid_pairs:
            combo = [ai_item, first, second]
            score_result = calculate_compatibility_score(combo)
            if not score_result['is_valid']:
                continue
            combos.append((combo, score_result))

        if not combos:
            continue

        combos.sort(key=lambda c: c[1]['score'], reverse=True)
        candidates_combos.append((ai_item, combos))

        if combos[0][1]['score'] > best_score:
            best_score = combos[0][1]['score']
            best_ai_item = ai_item

    if best_ai_item is None:
        return None, None, "No compatible AI item found for the user's wardrobe."

    bundles = []
    seen = set()
    pool = [combos for _, combos in candidates_combos]
    idx = 0
    while len(bundles) < max_bundles:
        added = False
        for combos in pool:
            if idx < len(combos):
                combo, score_result = combos[idx]
                dedupe_key = tuple(sorted(item.item_id for item in combo))
                if dedupe_key not in seen:
                    seen.add(dedupe_key)
                    bundles.append(build_bundle(combo, score_result))
                    added = True
                if len(bundles) >= max_bundles:
                    break
        if not added:
            break
        idx += 1

    if len(bundles) < min_bundles:
        return None, None, "Not enough compatible combinations found in the user's wardrobe."

    bundles.sort(key=lambda b: b['match_score'], reverse=True)
    return bundles[:max_bundles], best_ai_item, None
