"""
engine/recommendation_engine.py
===============================
Recommendation Engine (Personalization Layer — Step 4).

Orchestrates the full personalized flow WITHOUT touching the existing
compatibility engine:

    User Wardrobe
        -> WardrobeProfileBuilder.build()          (profile)
        -> PersonalizationEngine.score_item()       (per-item scores)
        -> rank items, keep top-K
        -> generate_bundles()                       (EXISTING engine, untouched)
        -> existing blended score (compat + item pers)
        -> PersonalizationEngine.score_bundle()     (onboarding bonus, 0–30)
        -> final_score = base_score + personalization_score

The compatibility engine remains the source of truth for *can these items be
worn together*; this layer only re-ranks which items/bundles surface for a
specific user.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from api.models import OutfitBundle, UserProfile, WardrobeItem

from engine.compatibility_engine import generate_bundles, re_rank_bundles_for_diversity
from engine.personalization_engine import (
    BundlePersonalizationResult,
    PersonalizationEngine,
    PersonalizationResult,
    clamp,
    normalize_weights,
)
from engine.wardrobe_profile import WardrobeProfile, WardrobeProfileBuilder

# Default blend used when ranking final bundles (configurable).
DEFAULT_COMPAT_WEIGHT = 0.6
DEFAULT_PERS_WEIGHT = 0.4


def combine_scores(
    compatibility_score: float,
    personalization_score: float,
    compat_weight: float = DEFAULT_COMPAT_WEIGHT,
    pers_weight: float = DEFAULT_PERS_WEIGHT,
) -> float:
    """Weighted blend of compatibility and personalization into 0–100.

    Weights are normalized so they do not need to sum to exactly 1.
    """
    total = max(compat_weight + pers_weight, 1e-9)
    blended = (compat_weight * compatibility_score + pers_weight * personalization_score) / total
    return round(clamp(blended), 2)


@dataclass
class ItemRanking:
    """A wardrobe item together with its personalization result."""

    item: WardrobeItem
    item_id: str
    personalization_score: float
    components: Dict[str, float] = field(default_factory=dict)
    reasons: List[str] = field(default_factory=list)


@dataclass
class ScoredBundle:
    """A generated bundle enriched with its blended final score.

    ``base_score`` is the existing blended bundle score (compatibility +
    item-level personalization) and stays unchanged. ``personalization_score``
    is the bounded onboarding bonus (0–30) computed by
    :meth:`PersonalizationEngine.score_bundle`. The final score is the sum:
    ``final_score = base_score + personalization_score``.
    """

    bundle: OutfitBundle
    compatibility_score: float
    base_score: float
    personalization_score: float
    final_score: float
    breakdown: Dict[str, float] = field(default_factory=dict)
    reasons: List[str] = field(default_factory=list)


@dataclass
class RecommendationResult:
    """Everything produced by one personalized recommendation run."""

    profile: WardrobeProfile
    ranked_items: List[ItemRanking]
    bundles: List[ScoredBundle]
    selected_item_ids: List[str] = field(default_factory=list)


class RecommendationEngine:
    """Runs the personalized recommendation pipeline end-to-end."""

    def __init__(
        self,
        weights: Optional[Dict[str, float]] = None,
        compat_weight: float = DEFAULT_COMPAT_WEIGHT,
        pers_weight: float = DEFAULT_PERS_WEIGHT,
        top_k: Optional[int] = None,
        max_bundles: int = 10,
    ):
        self.personalizer = PersonalizationEngine(weights=weights)
        self.profile_builder = WardrobeProfileBuilder()
        self.compat_weight = compat_weight
        self.pers_weight = pers_weight
        self.top_k = top_k
        self.max_bundles = max_bundles

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def recommend(
        self,
        items: List[WardrobeItem],
        user_profile: Optional[Any] = None,
        user_id: str = "",
        occasion_filter: Optional[str] = None,
        avoided_colors: Optional[List[str]] = None,
        top_k: Optional[int] = None,
        must_keep_ids: Optional[Any] = None,
        diversify: bool = False,
        diversity_top_n: Optional[int] = None,
    ) -> RecommendationResult:
        """Run the full personalized pipeline.

        Args:
            items: The user's wardrobe items.
            user_profile: Optional ``UserProfile`` ORM object or plain dict.
            user_id: Identifier passed through to the compatibility engine.
            occasion_filter: Optional occasion to filter generated bundles by.
            avoided_colors: Explicit avoided colors (fallback when no profile).
            top_k: If set, only the top-K ranked items feed the engine. Defaults
                to the engine's configured ``top_k`` (no truncation when unset).
            must_keep_ids: Item ids that are always included in the pool, even
                if they rank below the ``top_k`` cutoff (e.g. an anchor item).
            diversify: Optional POST-ranking diversity re-ranking layer (see
                ``engine.compatibility_engine.re_rank_bundles_for_diversity``).
                When False (the default) the FULL ranked bundle list is returned
                — every valid combination is scored and ranked by final score,
                and the old "max N repeats" rule is not applied during
                generation. When True, greedy diversity-aware selection re-orders
                the ranked list after scoring.
            diversity_top_n: Number of bundles to return after diversity
                re-ranking. Defaults to the engine's configured ``max_bundles``
                (and to the full pool size when ``max_bundles`` caps exceeded).
        """
        profile = self.profile_builder.build(items, user_profile)

        ranked = self.rank_items(items, profile)
        limit = top_k if top_k is not None else self.top_k
        pool = ranked
        if limit and limit > 0:
            keep = {str(item_id) for item_id in (must_keep_ids or [])}
            forced = [ranking for ranking in ranked if ranking.item_id in keep]
            rest = [ranking for ranking in ranked if ranking.item_id not in keep]
            pool = forced[:limit] + rest[:max(0, limit - len(forced))]

        effective_avoided = list(profile.avoided_colors) or list(avoided_colors or [])
        pool_items = [ranking.item for ranking in pool]

        # Existing, untouched compatibility/bundle engine.
        raw_bundles = generate_bundles(
            user_id=user_id,
            wardrobe_items=pool_items,
            occasion_filter=occasion_filter,
            avoided_colors=effective_avoided,
        )

        item_scores = {ranking.item_id: ranking.personalization_score for ranking in ranked}
        default_score = self._default_item_score(ranked)
        item_lookup = {str(getattr(item, 'item_id', '')): item for item in items}
        onboarding_preferences = profile.onboarding_preferences

        bundles = [
            self._score_bundle(
                bundle,
                item_scores,
                default_score,
                item_lookup,
                onboarding_preferences,
            )
            for bundle in raw_bundles
        ]
        bundles.sort(key=lambda scored: scored.final_score, reverse=True)

        # Diversity / similarity re-ranking is a POST-ranking selection layer:
        # it only re-orders which bundles surface for the UI and never removes
        # anything from the candidate pool permanently.
        if diversify:
            bundles = re_rank_bundles_for_diversity(
                bundles,
                top_n=diversity_top_n if diversity_top_n is not None else self.max_bundles,
                item_lookup=item_lookup,
            )

        return RecommendationResult(
            profile=profile,
            ranked_items=ranked,
            bundles=bundles,
            selected_item_ids=[ranking.item_id for ranking in pool],
        )

    def rank_items(
        self,
        items: List[WardrobeItem],
        profile: Optional[WardrobeProfile] = None,
    ) -> List[ItemRanking]:
        """Score every item and return them ranked by personalization (desc)."""
        if profile is None:
            profile = self.profile_builder.build(items)

        rankings = [
            self._rank_item(item, profile, items)
            for item in items
        ]
        rankings.sort(key=lambda ranking: ranking.personalization_score, reverse=True)
        return rankings

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _rank_item(
        self,
        item: WardrobeItem,
        profile: WardrobeProfile,
        all_items: List[WardrobeItem],
    ) -> ItemRanking:
        result: PersonalizationResult = self.personalizer.score_item(item, profile, all_items)
        return ItemRanking(
            item=item,
            item_id=str(getattr(item, 'item_id', '')),
            personalization_score=result.score,
            components=result.components,
            reasons=result.reasons,
        )

    def _score_bundle(
        self,
        bundle: OutfitBundle,
        item_scores: Dict[str, float],
        default_score: float,
        item_lookup: Optional[Dict[str, WardrobeItem]] = None,
        user_preferences: Optional[Dict[str, Any]] = None,
    ) -> ScoredBundle:
        bundle_items = bundle.items or []
        scores = [item_scores.get(str(item_id)) for item_id in bundle_items]
        present = [score for score in scores if score is not None]
        item_personalization = (
            sum(present) / len(present) if present else default_score
        )

        # Existing blended bundle score — unchanged.
        base_score = combine_scores(
            bundle.compatibility_score,
            item_personalization,
            self.compat_weight,
            self.pers_weight,
        )

        # Onboarding personalization bonus (0–30), added on top.
        pers: BundlePersonalizationResult = self.personalizer.score_bundle(
            bundle=bundle,
            user_preferences=user_preferences,
            item_lookup=item_lookup,
        )
        personalization_score = round(pers.score, 2)

        return ScoredBundle(
            bundle=bundle,
            compatibility_score=bundle.compatibility_score,
            base_score=base_score,
            personalization_score=personalization_score,
            final_score=round(base_score + personalization_score, 2),
            breakdown=pers.breakdown,
            reasons=pers.reasons,
        )

    @staticmethod
    def _default_item_score(ranked: List[ItemRanking]) -> float:
        """Fallback bundle personalization = mean item score across the wardrobe."""
        if not ranked:
            return 50.0
        return sum(r.personalization_score for r in ranked) / len(ranked)


def personalize_wardrobe(
    items: List[WardrobeItem],
    user_profile: Optional[Any] = None,
    weights: Optional[Dict[str, float]] = None,
) -> List[ItemRanking]:
    """Convenience wrapper: build the profile and rank items only."""
    engine = RecommendationEngine(weights=weights)
    profile = engine.profile_builder.build(items, user_profile)
    return engine.rank_items(items, profile)
