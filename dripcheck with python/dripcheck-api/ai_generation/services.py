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
from .bundle_unlock import generate_bundles_for_product, blend_unlock_boost

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


def evaluate_product_candidates(category, wardrobe_items, ai_candidates, max_per_category=10, max_bundles=None):
    """Score every AI candidate against the user's wardrobe.

    Returns (scores, error). `scores` is a best-first list of
    (rank_score, ai_item, combos, score_results) — one entry per product that
    unlocks at least one valid bundle. Each rank blends the product's best
    single match with a bounded unlock bonus (see bundle_unlock.blend_unlock_boost):

        rank = best_match_score + unlock boost

    The unlock boost never overrides compatibility — it only breaks ties in
    favour of products that unlock more outfits.
    """
    scores = []

    for ai_item in ai_candidates:
        combos = generate_bundles_for_product(
            ai_item,
            wardrobe_items,
            max_per_category=max_per_category,
            max_bundles=max_bundles,
        )
        if not combos:
            continue  # No valid bundle → do not recommend this product.

        score_results = [calculate_compatibility_score(combo) for combo in combos]
        best_match_score = max(result['score'] for result in score_results)
        rank_score = blend_unlock_boost(best_match_score, len(combos))
        scores.append((rank_score, ai_item, combos, score_results))

    if not scores:
        return None, "No compatible AI product unlocks bundles for the user's wardrobe."

    scores.sort(key=lambda entry: entry[0], reverse=True)
    return scores, None


def generate_ai_suggestions(category, wardrobe_items, ai_candidates, top_k=4, max_bundles=8, max_per_category=10):
    """Rank AI products and return per-product bundles, best product first.

    Each entry in the returned list is

        {"product": ai_item, "bundle_count": n, "bundles": [...]}

    where "bundles" is the single source of truth for both that product's
    unlock count and its 'Show all bundles' exploration view. `top_k` limits
    how many products are surfaced to the client.
    """
    complement_categories = COMPLEMENT_CATEGORIES[category]

    first_cat_items = [i for i in wardrobe_items if i.category == complement_categories[0]]
    second_cat_items = [i for i in wardrobe_items if i.category == complement_categories[1]]

    if not first_cat_items or not second_cat_items:
        return None, f"User has no {'/'.join(complement_categories)} items in their wardrobe."

    scores, error = evaluate_product_candidates(
        category,
        wardrobe_items,
        ai_candidates,
        max_per_category=max_per_category,
        max_bundles=max_bundles,
    )
    if error:
        return None, error

    suggestions = []
    for _, ai_item, combos, score_results in scores[:top_k]:
        ordered = sorted(
            zip(combos, score_results),
            key=lambda pair: pair[1]['score'],
            reverse=True,
        )
        bundles = [build_bundle(combo, result) for combo, result in ordered]
        suggestions.append({
            'product': ai_item,
            'bundle_count': len(bundles),
            'bundles': bundles,
        })

    return suggestions, None


def generate_ai_bundles(category, wardrobe_items, ai_candidates, min_bundles=1, max_bundles=8, max_per_category=10):
    """Backward-compatible wrapper returning only the best product's bundles.

    Keeps the original call signature so external callers (and tests) still
    work — the best suggestion from generate_ai_suggestions() is returned.
    """
    suggestions, error = generate_ai_suggestions(
        category,
        wardrobe_items,
        ai_candidates,
        top_k=1,
        max_bundles=max_bundles,
        max_per_category=max_per_category,
    )
    if error:
        return None, None, error

    best = suggestions[0]
    if len(best['bundles']) < min_bundles:
        return None, None, "Not enough compatible combinations found in the user's wardrobe."

    return best['bundles'], best['product'], None

