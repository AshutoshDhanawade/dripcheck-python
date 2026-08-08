"""
AI Drip — Bundle Unlock Engine
=================================

Single source of truth for the "Unlocks X bundles" feature.

Pipeline (mirrors the product spec):

    1. generate      — build every (recommended + wardrobe) combination
    2. score         — reuse calculate_compatibility_score from the engine
    3. filter        — drop invalid / low-score combinations
    4. deduplicate   — remove identical outfits
    5. diversity     — remove near-duplicate outfits (same family + subcategory)
    6. rank          — best → worst by compatibility score
    7. count         — bundle_count is ALWAYS len(final bundles)

Every pipeline step is a separate, configurable function so the behavior can
be tuned in isolation.
"""

from collections import Counter

from api.models import Category
from engine.compatibility_engine import (
    calculate_compatibility_score,
    PRIMARY_COLOR_TO_FAMILY,
)

# ---------------------------------------------------------------------------
# Configuration knobs (kept module-level so they can be tuned per deployment)
# ---------------------------------------------------------------------------

# Minimum compatibility score for a bundle to count as "unlockable".
MIN_COMPATIBILITY_SCORE = 60

# Cap on how many wardrobe items per category are considered, bounding the
# combinatorial explosion.
MAX_ITEMS_PER_CATEGORY = 10

# A single wardrobe item may anchor at most N of the final bundles.
# Prevents degenerate lists like 8 near-identical outfits built on one top.
MAX_BUNDLES_PER_ITEM = 3

# Unlock-potential boost used when ranking candidate recommendations.
UNLOCK_SCORE_CAP = 12       # bundle counts above this add no extra boost
UNLOCK_SCORE_BOOST = 0.8    # per-bundle points added to the match score


def _color_family_of(item):
    return item.color_family or PRIMARY_COLOR_TO_FAMILY.get(item.primary_color, "Neutral")


def _near_duplicate(combo, selected):
    """Two combos are near-duplicates when they share the recommended item plus
    one wardrobe item, and the remaining wardrobe item is practically the same
    (same subcategory + same color family). E.g.:

        Black T-shirt + Black Jeans + AI Shoes
        Black T-shirt + Dark Black Jeans + AI Shoes

    Both are "Black T-shirt + (dark jeans)" — one counts, not two.
    """
    combo_ids = {item.item_id for item in combo}
    for other in selected:
        other_ids = {item.item_id for item in other}
        shared = combo_ids & other_ids
        if len(shared) != len(combo) - 1:
            continue

        diff_combo = next(item for item in combo if item.item_id not in other_ids)
        diff_other = next(item for item in other if item.item_id not in combo_ids)

        if (
            _color_family_of(diff_combo) == _color_family_of(diff_other)
            and diff_combo.subcategory == diff_other.subcategory
        ):
            return True
    return False


def apply_diversity_filter(combos, max_per_item=MAX_BUNDLES_PER_ITEM):
    """Given valid (score, combo) pairs sorted best → worst, return a diverse
    subset: drop near-duplicates and cap how often any wardrobe item repeats.

    Intent is COMPATIBILITY + QUALITY + DIVERSITY — not the raw count of
    every mathematically possible combination.
    """
    usage = Counter()
    selected = []
    for score, combo in combos:
        if any(usage[item.item_id] >= max_per_item for item in combo):
            continue
        if _near_duplicate(combo, [c for _, c in selected]):
            continue
        usage.update(item.item_id for item in combo)
        selected.append((score, combo))
    return selected


def generate_bundles_for_product(
    recommended_item,
    wardrobe_items,
    min_score=MIN_COMPATIBILITY_SCORE,
    max_per_category=MAX_ITEMS_PER_CATEGORY,
    max_bundles=None,
    max_per_item=MAX_BUNDLES_PER_ITEM,
):
    """Build every high-quality bundle that a recommended product unlocks.

    `recommended_item` is always included in every returned bundle; the other
    slots vary across the user's existing wardrobe only. Returns the final
    ranked bundle list; `len(bundles)` IS the unlock count (single source of
    truth — never computed separately).
    """
    complement_categories = {
        Category.TOP: [Category.BOTTOM, Category.FOOTWEAR],
        Category.BOTTOM: [Category.TOP, Category.FOOTWEAR],
        Category.FOOTWEAR: [Category.TOP, Category.BOTTOM],
    }.get(recommended_item.category, [])

    if not complement_categories:
        return []

    def top_items(category):
        return sorted(
            (item for item in wardrobe_items if item.category == category),
            key=lambda i: (i.wear_count or 0, i.last_worn or ''),
            reverse=True,
        )[:max_per_category]

    first_items = top_items(complement_categories[0])
    second_items = top_items(complement_categories[1])

    if not first_items or not second_items:
        return []

    # 1–3. Generate, score, filter.
    combos = []
    for first in first_items:
        for second in second_items:
            combo = [recommended_item, first, second]
            result = calculate_compatibility_score(combo)
            if not result['is_valid'] or result['score'] < min_score:
                continue
            combos.append((result['score'], combo))

    if not combos:
        return []

    # 4. Remove identical outfits.
    combos.sort(key=lambda c: c[0], reverse=True)
    seen = set()
    unique = []
    for score, combo in combos:
        key = tuple(sorted(item.item_id for item in combo))
        if key in seen:
            continue
        seen.add(key)
        unique.append((score, combo))

# 5. Diversity filtering, aka final bundle list.
    ranked = apply_diversity_filter(unique, max_per_item=max_per_item)

    if max_bundles:
        ranked = ranked[:max_bundles]

    return [combo for _, combo in ranked]


def blend_unlock_boost(match_score, bundle_count):
    """Ranking signal = match score + bounded unlock potential. Products that
    unlock many outfits get a small bonus but never replace compatibility as
    the primary driver.
    """
    boost = min(bundle_count, UNLOCK_SCORE_CAP) * UNLOCK_SCORE_BOOST
    return match_score + boost
