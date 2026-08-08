"""
engine/wardrobe_profile.py
==========================
Wardrobe Profile Builder (Personalization Layer — Step 1).

Aggregates every ``WardrobeItem`` belonging to a user into a single
``WardrobeProfile`` dataclass. The profile is computed once per
recommendation run and reused by the personalization engine.

This module is additive and does NOT modify the existing compatibility
engine.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from api.models import WardrobeItem, UserProfile

from engine.compatibility_engine import PRIMARY_COLOR_TO_FAMILY

from engine.compatibility_engine import PRIMARY_COLOR_TO_FAMILY

# Category weights mirror the dominant-color weighting used by the existing
# compatibility engine (Top/Bottom carry more visual weight than Footwear).
_COLOR_WEIGHTS: Dict[str, float] = {
    'Top': 3.0,
    'Bottom': 3.0,
    'Layer': 2.0,
    'Footwear': 1.0,
    'Accessory': 0.5,
}

# Number of possible categories used for balance targets.
NUM_CATEGORIES = 5

# Fields of UserProfile that capture onboarding preferences.
_ONBOARDING_FIELDS = (
    'favorite_colors',
    'avoided_colors',
    'style_vibes',
    'fit_preferences',
    'pattern_preferences',
    'material_sensitivity',
    'occasion_frequency',
)


def _fraction(distribution: Dict[str, Any], key: Any, default: float = 0.0) -> float:
    """Return the relative frequency of ``key`` inside ``distribution``."""
    total = sum(distribution.values()) if distribution else 0
    if not total:
        return default
    return distribution.get(key, 0) / total


def _normalized_list(value: Optional[Any]) -> List[str]:
    """Coerce ``None``/dict/object values into a clean list of lower-case strings."""
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(v).strip().lower() for v in value if str(v).strip()]
    if isinstance(value, str):
        return [value.strip().lower()] if value.strip() else []
    return [str(value).strip().lower()]


def resolve_color_family(item: WardrobeItem) -> str:
    """Resolve an item's color family, preferring the stored value.

    Mirrors the fallback behaviour used by the compatibility engine.
    """
    stored = getattr(item, 'color_family', None)
    if stored:
        return stored
    color = getattr(item, 'primary_color', '')
    return PRIMARY_COLOR_TO_FAMILY.get(color, 'Neutral')


def extract_onboarding_preferences(user_profile: Optional[Any]) -> Dict[str, Any]:
    """Extract a flat dict of onboarding preferences.

    Accepts either a ``UserProfile`` ORM object or a plain dict, which keeps
    the builder easy to unit test without a database.
    """
    if not user_profile:
        return {}
    if isinstance(user_profile, dict):
        return dict(user_profile)

    preferences: Dict[str, Any] = {}
    for field_name in _ONBOARDING_FIELDS:
        value = getattr(user_profile, field_name, None)
        if value is not None:
            preferences[field_name] = value
    return preferences


def preferences_for_user(user: Any) -> Dict[str, Any]:
    """Build the merged preference dict for an authenticated user.

    Combines the structured ``UserProfile`` fields with free-form answers the
    user gave during onboarding (``UserOnboardingResponse``). This is the
    single entry point views should use when running recommendations.
    """
    profile = extract_onboarding_preferences(user) if user is not None else {}

    raw_responses: Dict[str, Any] = {}
    if user is not None:
        onboarding_response = getattr(user, 'onboarding_response', None)
        if onboarding_response is not None:
            raw_responses = dict(onboarding_response.responses or {})
    merged = onboarding_responses_to_preferences(raw_responses)
    merged.update(profile)
    return merged


# Map of onboarding option labels -> personalization-friendly vocabulary.
STYLE_ANSWER_TO_VIBE = {
    'casual': 'Casual',
    'streetwear': 'Streetwear',
    'formal': 'Formal',
    'minimal': 'Minimalist',
    'ethnic': 'Ethnic',
    'sporty': 'Sporty',
    'vintage': 'Vintage',
    'korean fashion': 'Korean Fashion',
    'smart casual': 'Smart Casual',
}


def onboarding_responses_to_preferences(responses: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Translate raw onboarding answers into engine preference keys.

    Frontend answers are keyed either by question *text* or by shorthand keys
    (``styles``, ``clothes``, ``colors``, ``goal``, ``buyingFrequency``).
    This maps the ones the engine understands onto the vocabulary used by the
    personalization engine.
    """
    prefs: Dict[str, Any] = {}
    if not responses:
        return prefs

    # Shorthand keys the frontend uses for each onboarding question.
    shorthand = {
        'styles': 'style',
        'clothes': 'clothes',
        'colors': 'colors',
        'goal': 'goal',
        'buyingFrequency': 'buying_frequency',
    }

    for key, answer in responses.items():
        raw_key = str(key).strip()
        norm_key = raw_key.lower()
        group = shorthand.get(raw_key)
        if group is None:
            if 'style' in norm_key:
                group = 'style'
            elif 'cloth' in norm_key:
                group = 'clothes'
            elif 'color' in norm_key:
                group = 'colors'
            else:
                group = 'other'

        if group == 'style':
            values = _normalized_list(answer)
            prefs['style_vibes'] = [STYLE_ANSWER_TO_VIBE.get(v, v.title()) for v in values]
        elif group == 'clothes':
            prefs['preferred_subcategories'] = _normalized_list(answer)
        elif group == 'colors':
            prefs['favorite_colors'] = _normalized_list(answer)

    return prefs


@dataclass
class WardrobeProfile:
    """Aggregated view of a user's wardrobe."""

    total_items: int = 0
    dominant_colors: List[str] = field(default_factory=list)
    dominant_color_families: List[str] = field(default_factory=list)
    color_distribution: Dict[str, int] = field(default_factory=dict)
    color_family_distribution: Dict[str, int] = field(default_factory=dict)
    style_distribution: Dict[str, int] = field(default_factory=dict)
    occasion_distribution: Dict[str, int] = field(default_factory=dict)
    category_counts: Dict[str, int] = field(default_factory=dict)
    fit_distribution: Dict[str, int] = field(default_factory=dict)
    season_distribution: Dict[str, int] = field(default_factory=dict)
    formality_distribution: Dict[str, int] = field(default_factory=dict)
    pattern_distribution: Dict[str, int] = field(default_factory=dict)
    favorite_brands: List[str] = field(default_factory=list)
    onboarding_preferences: Dict[str, Any] = field(default_factory=dict)
    avoided_colors: List[str] = field(default_factory=list)

    # -- Convenience helpers ------------------------------------------------

    def category_fraction(self, category: str, default: float = 0.0) -> float:
        return _fraction(self.category_counts, category, default)

    def color_family_fraction(self, family: str, default: float = 0.0) -> float:
        return _fraction(self.color_family_distribution, family, default)


class WardrobeProfileBuilder:
    """Builds a :class:`WardrobeProfile` from wardrobe items and preferences."""

    def build(
        self,
        items: List[WardrobeItem],
        user_profile: Optional[Any] = None,
    ) -> WardrobeProfile:
        onboarding = self._collect_preferences(user_profile)
        avoided = _normalized_list(onboarding.get('avoided_colors'))

        if not items:
            return WardrobeProfile(
                total_items=0,
                onboarding_preferences=onboarding,
                avoided_colors=avoided,
            )

        category_counts: Counter = Counter()
        fit_distribution: Counter = Counter()
        season_distribution: Counter = Counter()
        formality_distribution: Counter = Counter()
        pattern_distribution: Counter = Counter()
        color_distribution: Counter = Counter()
        color_family_distribution: Counter = Counter()
        style_distribution: Counter = Counter()
        occasion_distribution: Counter = Counter()
        brand_counts: Counter = Counter()

        for item in items:
            category_counts[item.category] += 1
            fit_distribution[getattr(item, 'fit', None) or 'Regular'] += 1
            season_distribution[getattr(item, 'season', None) or 'All-season'] += 1
            formality_distribution[getattr(item, 'formality_level', None) or 0] += 1
            pattern_distribution[getattr(item, 'pattern', None) or 'Solid'] += 1

            color = getattr(item, 'primary_color', '') or ''
            color_distribution[color] += 1
            family = resolve_color_family(item)
            color_family_distribution[family] += 1

            for tag in getattr(item, 'style_tags', None) or []:
                style_distribution[str(tag).strip().lower()] += 1
            for occ in getattr(item, 'occasion_type', None) or []:
                occasion_distribution[str(occ).strip().lower()] += 1

            brand = getattr(item, 'brand', None)
            if brand:
                brand_counts[str(brand).strip()] += 1

        return WardrobeProfile(
            total_items=len(items),
            dominant_colors=self._dominant_colors(items),
            dominant_color_families=self._dominant_color_families(color_family_distribution),
            color_distribution=dict(color_distribution),
            color_family_distribution=dict(color_family_distribution),
            style_distribution=dict(style_distribution),
            occasion_distribution=dict(occasion_distribution),
            category_counts=dict(category_counts),
            fit_distribution=dict(fit_distribution),
            season_distribution=dict(season_distribution),
            formality_distribution=dict(formality_distribution),
            pattern_distribution=dict(pattern_distribution),
            favorite_brands=self._favorite_brands(brand_counts),
            onboarding_preferences=onboarding,
            avoided_colors=avoided,
        )

    # -- Private helpers ----------------------------------------------------

    @staticmethod
    def _collect_preferences(user_profile: Optional[Any]) -> Dict[str, Any]:
        """Merge explicit profile fields with free-form onboarding answers.

        ``user_profile`` may be a ``UserProfile`` ORM object, a plain dict,
        or a ``User`` (whose onboarding answers will be pulled from
        ``UserOnboardingResponse``). Explicit profile fields win over the
        free-form answer mapping.
        """
        combined: Dict[str, Any] = {}

        # Free-form onboarding answers (questionnaire responses).
        raw_responses = {}
        if user_profile is not None and not isinstance(user_profile, dict):
            onboarding_response = getattr(user_profile, 'onboarding_response', None)
            if onboarding_response is not None:
                raw_responses = dict(onboarding_response.responses or {})
        combined.update(onboarding_responses_to_preferences(raw_responses))

        # Explicit UserProfile fields override.
        combined.update(extract_onboarding_preferences(user_profile))

        return combined

    # -- Private helpers ----------------------------------------------------

    def _dominant_colors(self, items: List[WardrobeItem]) -> List[str]:
        """Top colors using category-weighted voting (consistent with the engine)."""
        scores: Dict[str, float] = {}
        for item in items:
            color = getattr(item, 'primary_color', '') or ''
            if not color:
                continue
            weight = _COLOR_WEIGHTS.get(getattr(item, 'category', None), 1.0)
            scores[color] = scores.get(color, 0.0) + weight

        if not scores:
            return []
        return self._top_above_threshold(scores, factor=0.8, limit=3)

    def _dominant_color_families(self, family_distribution: Counter) -> List[str]:
        if not family_distribution:
            return []
        return self._top_above_threshold(dict(family_distribution), factor=0.6, limit=3)

    def _favorite_brands(self, brand_counts: Counter) -> List[str]:
        """Brands worn at least twice, most frequent first."""
        favorites = [brand for brand, count in brand_counts.most_common() if count >= 2]
        return favorites[:3]

    @staticmethod
    def _top_above_threshold(
        scores: Dict[str, float],
        factor: float,
        limit: int,
    ) -> List[str]:
        max_score = max(scores.values())
        if max_score <= 0:
            return []
        threshold = max_score * factor
        ranked = [key for key, value in sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
                  if value >= threshold]
        return ranked[:limit]
