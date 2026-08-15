"""
engine/personalization_engine.py
================================
Personalization Engine (Personalization Layer — Steps 2 & 3).

Scores a single ``WardrobeItem`` against the user's aggregated
:class:`WardrobeProfile`. It does NOT generate bundles and does NOT modify
the existing compatibility engine — it answers *"how relevant is this item
for THIS user?"* before compatibility answers *"can these items be worn
together?"*.

Every component scorer returns a tuple ``(score: float, reasons: List[str])``
where ``score`` is normalized to 0–100.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from api.models import OutfitBundle, WardrobeItem

from engine.compatibility_engine import PRIMARY_COLOR_TO_FAMILY
from engine.wardrobe_profile import (
    WardrobeProfile,
    resolve_color_family,
    _fraction,
    _normalized_list,
)

# Default configurable weights (Step 3 of the spec).
DEFAULT_WEIGHTS: Dict[str, float] = {
    'style': 0.15,
    'color': 0.15,
    'preference': 0.20,
    'occasion': 0.10,
    'fit': 0.05,
    'season': 0.05,
    'category': 0.10,
    'novelty': 0.20,
}

# Bundle-level personalization bounds (secondary ranking signal).
# The base bundle score is ~0–100, so each onboarding component adds at most
# +10 and the whole bonus is capped at +30 — personalization can only re-rank
# bundles, never overpower a distinctly better outfit.
BUNDLE_STYLE_MAX = 10.0
BUNDLE_CLOTHING_MAX = 10.0
BUNDLE_COLOR_MAX = 10.0
MAX_BUNDLE_PERSONALIZATION = BUNDLE_STYLE_MAX + BUNDLE_CLOTHING_MAX + BUNDLE_COLOR_MAX

# Color-family aliases for free-form onboarding answers that lean on families
# (e.g. "Pastel Shades" maps to the stored ``Pastel`` family).
COLOR_FAMILY_ALIASES: Dict[str, str] = {
    'pastel shades': 'Pastel',
    'pastel': 'Pastel',
    'earth tones': 'Earth',
    'earthy': 'Earth',
    'neutral shades': 'Neutral',
    'neutrals': 'Neutral',
    'dark colors': 'Dark',
    'bold colors': 'Bold',
    'warm shades': 'Warm',
}

# Valid component keys; used to reject unknown weights.
COMPONENT_KEYS = tuple(DEFAULT_WEIGHTS)

# Items whose pairwise similarity reaches this threshold count as "duplicates".
SIMILARITY_THRESHOLD = 0.6
# Each duplicate subtracts this many novelty points.
NOVELTY_PENALTY_PER_DUPLICATE = 20.0


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    """Clamp ``value`` into the inclusive ``[low, high]`` range."""
    return max(low, min(high, value))


def _matches_subcategory(item_subcategory: str, preferred: set) -> bool:
    """Tolerant subcategory match: handles plural labels from onboarding
    (e.g. 'Hoodies' / 'Jeans') against singular item subcategories
    ('Hoodie' / 'Jean')."""
    if not item_subcategory or not preferred:
        return False
    if item_subcategory in preferred:
        return True
    singular = item_subcategory[:-1] if item_subcategory.endswith('s') else item_subcategory
    if singular and (singular in preferred or item_subcategory in {p for p in preferred if p.endswith('s') and p[:-1] == singular}):
        return True
    return any(singular == (p[:-1] if p.endswith('s') else p) for p in preferred)


def normalize_weights(weights: Optional[Dict[str, float]]) -> Dict[str, float]:
    """Normalize a weight mapping so its values sum to 1.0.

    When ``weights`` is ``None`` the defaults are used. When provided, only
    the supplied components are kept (unknown keys are dropped) and the rest
    effectively receive zero weight — callers pass a full mapping when they
    want to tune every component.
    """
    if weights is None:
        weights = DEFAULT_WEIGHTS
    cleaned = {key: max(0.0, float(value)) for key, value in weights.items() if key in COMPONENT_KEYS}
    if not cleaned:
        cleaned = dict(DEFAULT_WEIGHTS)
    total = sum(cleaned.values())
    if total <= 0:
        n = len(cleaned)
        return {key: 1.0 / n for key in cleaned}
    return {key: value / total for key, value in cleaned.items()}


@dataclass
class PersonalizationResult:
    """Result of scoring a single wardrobe item for a user."""

    score: float
    components: Dict[str, float]
    reasons: List[str] = field(default_factory=list)


@dataclass
class BundlePersonalizationResult:
    """Result of scoring a whole bundle against onboarding preferences.

    ``score`` is the total bounded bonus (max 30) added on top of the base
    bundle score; ``breakdown`` exposes the per-component sub-scores so the
    final ranking can be debugged and tuned.
    """

    score: float
    breakdown: Dict[str, float]
    reasons: List[str] = field(default_factory=list)


class PersonalizationEngine:
    """Scores wardrobe items for user relevance across eight components.

    Small, single-responsibility scorer methods keep the class easy to test.
    """

    def __init__(self, weights: Optional[Dict[str, float]] = None):
        self.weights = normalize_weights(weights)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def score_item(
        self,
        item: WardrobeItem,
        profile: WardrobeProfile,
        all_items: Optional[List[WardrobeItem]] = None,
    ) -> PersonalizationResult:
        """Score a single item; combine the seven components via the weights."""
        all_items = all_items or []

        style_score, style_reasons = self.style_score(item, profile)
        color_score, color_reasons = self.color_score(item, profile)
        preference_score, preference_reasons = self.preference_score(item, profile)
        occasion_score, occasion_reasons = self.occasion_score(item, profile)
        fit_score, fit_reasons = self.fit_score(item, profile)
        season_score, season_reasons = self.season_score(item, profile)
        category_score, category_reasons = self.category_balance_score(item, profile)
        novelty_score, novelty_reasons = self.novelty_score(item, all_items)

        components = {
            'style': style_score,
            'color': color_score,
            'preference': preference_score,
            'occasion': occasion_score,
            'fit': fit_score,
            'season': season_score,
            'category': category_score,
            'novelty': novelty_score,
        }

        total = sum(self.weights[key] * components[key] for key in self.weights)
        reasons = (
            style_reasons + color_reasons + preference_reasons + occasion_reasons
            + fit_reasons + season_reasons + category_reasons + novelty_reasons
        )

        return PersonalizationResult(
            score=round(clamp(total), 2),
            components=components,
            reasons=reasons,
        )

    # ------------------------------------------------------------------
    # Bundle personalization (onboarding preferences only)
    # ------------------------------------------------------------------

    def score_bundle(
        self,
        bundle: OutfitBundle,
        user_preferences: Optional[Dict[str, Any]] = None,
        item_lookup: Optional[Dict[str, WardrobeItem]] = None,
    ) -> BundlePersonalizationResult:
        """Score one whole bundle against the user's onboarding preferences.

        Uses ONLY onboarding data: fashion styles, clothes worn most, and
        preferred colors. No purchases / likes / browsing signals are used.

        Each component is bounded to ``BUNDLE_*_MAX`` points and the total to
        ``MAX_BUNDLE_PERSONALIZATION`` (+30), keeping personalization a
        secondary ranking signal over the 0–100 base bundle score.

        ``user_preferences`` should be the merged onboarding dict built once
        per run (e.g. ``profile.onboarding_preferences`` / the dict produced by
        ``wardrobe_profile.preferences_for_user``). ``item_lookup`` maps the
        bundle's stored item ids to their ``WardrobeItem`` objects so the
        bundle's subcategories / colors / styles can be inspected.
        """
        prefs = user_preferences or {}
        item_ids = bundle.items or []
        items = [
            item for item in (item_lookup or {}).values()
            if str(getattr(item, 'item_id', '')) in {str(i) for i in item_ids}
        ]
        if not items and item_ids:
            items = [
                item_lookup.get(str(i))
                for i in item_ids
                if item_lookup.get(str(i)) is not None
            ]

        bundle_style_tags = _normalized_list(getattr(bundle, 'style_tags', None))

        style_score, style_reasons = self._bundle_style_score(prefs, items, bundle_style_tags)
        clothing_score, clothing_reasons = self._bundle_clothing_score(prefs, items)
        color_score, color_reasons = self._bundle_color_score(prefs, items)

        total = clamp(
            style_score + clothing_score + color_score,
            0.0,
            MAX_BUNDLE_PERSONALIZATION,
        )
        return BundlePersonalizationResult(
            score=round(total, 2),
            breakdown={
                'style_score': round(style_score, 2),
                'clothing_score': round(clothing_score, 2),
                'color_score': round(color_score, 2),
            },
            reasons=style_reasons + clothing_reasons + color_reasons,
        )

    # -- Bundle component 1: style -----------------------------------------

    def _bundle_style_score(
        self,
        prefs: Dict[str, Any],
        items: List[WardrobeItem],
        bundle_style_tags: List[str],
    ) -> Tuple[float, List[str]]:
        preferred = set(_normalized_list(
            prefs.get('style_vibes') or prefs.get('styles')
        ))
        if not preferred:
            return 0.0, ["No style preferences answered"]

        bundle_styles = set(bundle_style_tags)
        for item in items:
            bundle_styles.update(_normalized_list(getattr(item, 'style_tags', None)))

        matched = bundle_styles & preferred
        if not matched:
            return 0.0, ["Bundle style(s) not among preferred"]

        coverage = len(matched) / len(preferred)
        score = BUNDLE_STYLE_MAX * min(coverage, 1.0)
        return round(score, 2), [f"Style match: {', '.join(sorted(matched)[:3])}"]

    # -- Bundle component 2: clothing categories --------------------------

    def _bundle_clothing_score(
        self,
        prefs: Dict[str, Any],
        items: List[WardrobeItem],
    ) -> Tuple[float, List[str]]:
        preferred = set(_normalized_list(
            prefs.get('preferred_subcategories')
            or prefs.get('clothes')
            or prefs.get('preferred_clothes')
        ))
        if not preferred:
            return 0.0, ["No clothing preferences answered"]
        if not items:
            return 0.0, ["Cannot resolve bundle items"]

        matched = [
            item for item in items
            if _matches_subcategory(
                str(getattr(item, 'subcategory', '') or '').strip().lower(),
                preferred,
            )
        ]
        matched_names = {str(getattr(item, 'subcategory', '') or '') for item in matched}
        score = BUNDLE_CLOTHING_MAX * (len(matched) / len(items))
        reasons = (
            [f"Clothing match: {', '.join(sorted(matched_names)[:3])}"]
            if matched else ["No clothing match"]
        )
        return round(score, 2), reasons

    # -- Bundle component 3: colors ----------------------------------------

    def _bundle_color_score(
        self,
        prefs: Dict[str, Any],
        items: List[WardrobeItem],
    ) -> Tuple[float, List[str]]:
        raw = prefs.get('favorite_colors') or prefs.get('colors')
        preferred = set(_normalized_list(raw))
        preferred_families = set()
        for color in preferred:
            family = COLOR_FAMILY_ALIASES.get(color)
            if family:
                preferred_families.add(family.lower())
        if not preferred and not preferred_families:
            return 0.0, ["No color preferences answered"]
        if not items:
            return 0.0, ["Cannot resolve bundle items"]

        matched = []
        for item in items:
            primary = str(getattr(item, 'primary_color', '') or '').strip().lower()
            family = str(getattr(item, 'color_family', '') or '').strip().lower()
            resolved_family = (resolve_color_family(item) or '').strip().lower()
            if primary in preferred or family in preferred:
                matched.append(item)
            elif family in preferred_families or resolved_family in preferred_families:
                matched.append(item)

        matched_colors = {
            str(getattr(item, 'primary_color', '') or '') for item in matched
        }
        score = BUNDLE_COLOR_MAX * (len(matched) / len(items))
        reasons = (
            [f"Color match: {', '.join(sorted(matched_colors)[:3])}"]
            if matched else ["No color match"]
        )
        return round(score, 2), reasons

    # ------------------------------------------------------------------
    # Component 1 — Style similarity (0–100)
    # ------------------------------------------------------------------

    def style_score(
        self,
        item: WardrobeItem,
        profile: WardrobeProfile,
    ) -> Tuple[float, List[str]]:
        item_tags = _normalized_list(getattr(item, 'style_tags', None))
        if not item_tags:
            return 50.0, ["No style tags available for this item"]

        preferred = set(_normalized_list(profile.onboarding_preferences.get('style_vibes')))
        style_dist = profile.style_distribution or {}
        max_count = max(style_dist.values()) if style_dist else 0

        relevance: List[float] = []
        for tag in item_tags:
            if tag in preferred:
                relevance.append(100.0)
            elif style_dist and tag in style_dist:
                # Scale 60–100 by how popular the style is in the wardrobe.
                relevance.append(60.0 + 40.0 * (style_dist[tag] / max_count))
            else:
                relevance.append(0.0)

        score = sum(relevance) / len(relevance)
        matched = [tag for tag in item_tags if tag in preferred or tag in style_dist]
        reasons = []
        if matched:
            reasons.append(f"Fits preferred style(s): {', '.join(matched[:2])}")
        if not any(relevance):
            reasons.append("Style is new to this wardrobe")
        return round(score, 2), reasons

    # ------------------------------------------------------------------
    # Component 2 — Color similarity (0–100)
    # ------------------------------------------------------------------

    def color_score(
        self,
        item: WardrobeItem,
        profile: WardrobeProfile,
    ) -> Tuple[float, List[str]]:
        primary = str(getattr(item, 'primary_color', '') or '').strip().lower()
        family = resolve_color_family(item).lower()

        avoided = set(profile.avoided_colors)
        if primary in avoided or family in avoided:
            return 10.0, ["Color is on the user's avoided list"]

        favorite_colors = set(_normalized_list(profile.onboarding_preferences.get('favorite_colors')))
        dominant_colors = {c.lower() for c in profile.dominant_colors}
        dominant_families = {f.lower() for f in profile.dominant_color_families}

        scores: List[float] = []
        reasons: List[str] = []
        if primary in favorite_colors:
            scores.append(100.0)
            reasons.append("Matches a preferred color")
        if primary in dominant_colors:
            scores.append(85.0)
            reasons.append("Matches dominant wardrobe colors")
        if family in dominant_families:
            scores.append(70.0)
            reasons.append("Matches dominant wardrobe color family")
        if not scores:
            scores.append(45.0)
            reasons.append("Color is a fresh addition to the wardrobe")

        return round(max(scores), 2), reasons

    # ------------------------------------------------------------------
    # Component 3 — Explicit onboarding preferences (0–100)
    # ------------------------------------------------------------------

    def preference_score(
        self,
        item: WardrobeItem,
        profile: WardrobeProfile,
    ) -> Tuple[float, List[str]]:
        """Score how well an item matches the user's explicit onboarding
        answers: preferred clothing/types, fit, material, pattern.

        Unlike style/color/occasion (which lean on wardrobe distributions),
        this uses the user's stated preferences directly so answers to the
        onboarding questionnaire actually steer recommendations.
        """
        prefs = profile.onboarding_preferences or {}

        preferred_clothes = set(_normalized_list(prefs.get('preferred_clothes')))
        preferred_subcategories = set(_normalized_list(prefs.get('preferred_subcategories')))
        preferred_fits = set(_normalized_list(prefs.get('fit_preferences')))
        preferred_patterns = set(_normalized_list(prefs.get('pattern_preferences')))

        item_tags = set(_normalized_list(getattr(item, 'style_tags', None)))
        item_fit = str(getattr(item, 'fit', '') or '').strip().lower()
        item_pattern = str(getattr(item, 'pattern', '') or '').strip().lower()
        item_subcategory = str(getattr(item, 'subcategory', '') or '').strip().lower()
        item_material = str(getattr(item, 'material', '') or '').strip().lower()

        scores: List[float] = []
        reasons: List[str] = []

        if item_tags & preferred_clothes:
            scores.append(100.0)
            reasons.append("Matches a clothing type you prefer")
        if preferred_subcategories and _matches_subcategory(item_subcategory, preferred_subcategories):
            scores.append(100.0)
            reasons.append("Matches a preferred clothing subcategory")
        if preferred_fits and item_fit:
            if item_fit in preferred_fits:
                scores.append(90.0)
                reasons.append("Matches your preferred fit")
        if preferred_patterns and item_pattern in preferred_patterns:
            scores.append(80.0)
            reasons.append("Matches your preferred pattern")
        if item_material and prefs.get('material_sensitivity'):
            preferred_materials = _normalized_list(prefs.get('material_sensitivity'))
            if item_material in preferred_materials:
                scores.append(80.0)
                reasons.append("Matches material you are comfortable with")

        if not scores:
            return 50.0, ["No strong preference signal for this item"]

        return round(sum(scores) / len(scores), 2), reasons

    # ------------------------------------------------------------------
    # Component 4 — Occasion similarity (0–100)
    # ------------------------------------------------------------------

    def occasion_score(
        self,
        item: WardrobeItem,
        profile: WardrobeProfile,
    ) -> Tuple[float, List[str]]:
        item_occasions = _normalized_list(getattr(item, 'occasion_type', None))
        if not item_occasions:
            return 50.0, ["No occasion tags available for this item"]

        dist = profile.occasion_distribution or {}
        max_count = max(dist.values()) if dist else 0

        scores = [
            60.0 + 40.0 * (dist.get(occ, 0) / max_count) if dist and occ in dist else 20.0
            for occ in item_occasions
        ]
        score = sum(scores) / len(scores)
        matched = [occ for occ in item_occasions if dist and occ in dist]
        reasons = (
            [f"Fits a frequent occasion: {matched[0]}"]
            if matched
            else ["Occasion is rarely covered by this user's wardrobe"]
        )
        return round(score, 2), reasons

    # ------------------------------------------------------------------
    # Component 5 — Fit similarity (0–100)
    # ------------------------------------------------------------------

    def fit_score(
        self,
        item: WardrobeItem,
        profile: WardrobeProfile,
    ) -> Tuple[float, List[str]]:
        fit = getattr(item, 'fit', None)
        if not fit:
            return 50.0, ["No fit specified for this item"]

        dist = profile.fit_distribution or {}
        max_count = max(dist.values()) if dist else 0
        if dist and fit in dist:
            score = 60.0 + 40.0 * (dist[fit] / max_count)
            return round(score, 2), [f"Fits preferred silhouette: {fit}"]
        return 40.0, [f"{fit} is a new silhouette for this user"]

    # ------------------------------------------------------------------
    # Component 6 — Season similarity (0–100)
    # ------------------------------------------------------------------

    def season_score(
        self,
        item: WardrobeItem,
        profile: WardrobeProfile,
    ) -> Tuple[float, List[str]]:
        season = getattr(item, 'season', None) or 'All-season'
        if season == 'All-season':
            return 70.0, ["All-season item works year-round"]

        dist = profile.season_distribution or {}
        max_count = max(dist.values()) if dist else 0
        if dist and season in dist:
            score = 60.0 + 40.0 * (dist[season] / max_count)
            return round(score, 2), [f"Matches a wardrobe season: {season}"]
        return 30.0, [f"Season {season} is uncommon in this wardrobe"]

    # ------------------------------------------------------------------
    # Component 7 — Category balance (0–100)
    # ------------------------------------------------------------------

    def category_balance_score(
        self,
        item: WardrobeItem,
        profile: WardrobeProfile,
    ) -> Tuple[float, List[str]]:
        category = getattr(item, 'category', None)
        counts = profile.category_counts or {}
        total = sum(counts.values())
        if not category or not total:
            return 50.0, ["Cannot determine category balance"]

        target = 1.0 / 5.0  # Top, Bottom, Footwear, Layer, Accessory
        fraction = counts.get(category, 0) / total

        if fraction <= target:
            # Underrepresented (or balanced): reward, more when scarcer.
            score = 60.0 + 40.0 * ((target - fraction) / target)
            reason = f"Strengthens underrepresented {category} category"
        else:
            # Overrepresented: penalty proportional to excess.
            score = 100.0 * target / fraction
            reason = f"{category} category is overrepresented in this wardrobe"

        return round(clamp(score), 2), [reason]

    # ------------------------------------------------------------------
    # Component 8 — Novelty (0–100)
    # ------------------------------------------------------------------

    def novelty_score(
        self,
        item: WardrobeItem,
        all_items: List[WardrobeItem],
    ) -> Tuple[float, List[str]]:
        item_id = getattr(item, 'item_id', None)
        similar_count = 0
        for other in all_items:
            other_id = getattr(other, 'item_id', None)
            if item_id is not None and other_id == item_id:
                continue
            if other is item:
                continue
            if self.item_similarity(item, other) >= SIMILARITY_THRESHOLD:
                similar_count += 1

        if similar_count == 0:
            return 100.0, ["Distinct from existing wardrobe items"]

        score = clamp(100.0 - NOVELTY_PENALTY_PER_DUPLICATE * similar_count)
        label = "item" if similar_count == 1 else "items"
        return round(score, 2), [f"{similar_count} very similar {label} already in wardrobe"]

    def item_similarity(self, a: WardrobeItem, b: WardrobeItem) -> float:
        """Pairwise similarity in [0, 1] across the six relevant attributes."""
        score = 0.0

        if getattr(a, 'category', None) == getattr(b, 'category', None):
            score += 0.25
        if self._same_color(a, b):
            score += 0.20
        if getattr(a, 'pattern', None) == getattr(b, 'pattern', None):
            score += 0.15
        if getattr(a, 'fit', None) == getattr(b, 'fit', None):
            score += 0.15
        if set(_normalized_list(getattr(a, 'style_tags', None))) & set(
            _normalized_list(getattr(b, 'style_tags', None))
        ):
            score += 0.15

        fa = getattr(a, 'formality_level', None)
        fb = getattr(b, 'formality_level', None)
        if fa is not None and fb is not None and abs(fa - fb) <= 1:
            score += 0.10

        return score

    @staticmethod
    def _same_color(a: WardrobeItem, b: WardrobeItem) -> bool:
        color_a = str(getattr(a, 'primary_color', '') or '').strip().lower()
        color_b = str(getattr(b, 'primary_color', '') or '').strip().lower()
        if color_a and color_a == color_b:
            return True
        return resolve_color_family(a).lower() == resolve_color_family(b).lower()


def calculate_personalization_score(
    item: WardrobeItem,
    profile: WardrobeProfile,
    all_items: Optional[List[WardrobeItem]] = None,
    weights: Optional[Dict[str, float]] = None,
) -> PersonalizationResult:
    """Module-level convenience wrapper (Step 3 of the spec).

    Example result::

        {
            "score": 87,
            "components": {
                "style": 92, "color": 84, "occasion": 91, "fit": 88,
                "season": 70, "category": 94, "novelty": 81,
            },
            "reasons": [
                "Matches dominant wardrobe colors",
                "Fits preferred style(s): minimalist",
                "Strengthens underrepresented Footwear category",
            ],
        }
    """
    return PersonalizationEngine(weights=weights).score_item(item, profile, all_items)


def calculate_bundle_personalization(
    bundle: OutfitBundle,
    user_preferences: Optional[Dict[str, Any]] = None,
    item_lookup: Optional[Dict[str, WardrobeItem]] = None,
    weights: Optional[Dict[str, float]] = None,
) -> BundlePersonalizationResult:
    """Module-level convenience wrapper for :meth:`PersonalizationEngine.score_bundle`.

    Example result::

        {
            "personalization_score": 28.0,
            "breakdown": {
                "style_score": 10.0,
                "clothing_score": 10.0,
                "color_score": 8.0,
            },
            "reasons": ["Style match: Streetwear", ...],
        }
    """
    return PersonalizationEngine(weights=weights).score_bundle(
        bundle=bundle,
        user_preferences=user_preferences,
        item_lookup=item_lookup,
    )
