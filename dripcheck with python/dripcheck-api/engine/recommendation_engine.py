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
        -> combine compatibility + personalization   (final bundle ranking)

The compatibility engine remains the source of truth for *can these items be
worn together*; this layer only re-ranks which items/bundles surface for a
specific user.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from api.models import OutfitBundle, UserProfile, WardrobeItem

from engine.compatibility_engine import generate_bundles
from engine.personalization_engine import (
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
    """A generated bundle enriched with its blended final score."""

    bundle: OutfitBundle
    compatibility_score: float
    personalization_score: float
    final_score: float


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
        max_item_repeats: int = 2,
    ):
        self.personalizer = PersonalizationEngine(weights=weights)
        self.profile_builder = WardrobeProfileBuilder()
        self.compat_weight = compat_weight
        self.pers_weight = pers_weight
        self.top_k = top_k
        self.max_bundles = max_bundles
        self.max_item_repeats = max_item_repeats

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

        bundles = [
            self._score_bundle(bundle, item_scores, default_score)
            for bundle in raw_bundles
        ]
        bundles.sort(key=lambda scored: scored.final_score, reverse=True)

        bundles = self._diversify_bundles(bundles, max_repeats=self.max_item_repeats)

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
    ) -> ScoredBundle:
        bundle_items = bundle.items or []
        scores = [item_scores.get(str(item_id)) for item_id in bundle_items]
        present = [score for score in scores if score is not None]
        personalization_score = (
            sum(present) / len(present) if present else default_score
        )
        final_score = combine_scores(
            bundle.compatibility_score,
            personalization_score,
            self.compat_weight,
            self.pers_weight,
        )
        return ScoredBundle(
            bundle=bundle,
            compatibility_score=bundle.compatibility_score,
            personalization_score=round(personalization_score, 2),
            final_score=final_score,
        )

    def _diversify_bundles(
        self,
        bundles: List[ScoredBundle],
        max_repeats: Optional[int] = None,
    ) -> List[ScoredBundle]:
        """Limit how many times an item repeats across returned bundles.

        Prevents the same few items from dominating every recommendation on the
        homepage. Keeps the highest-scored bundles while enforcing (unless the
        pool is too small) that a single item appears in at most ``max_repeats``
        bundles.
        """
        if max_repeats is None:
            max_repeats = self.max_item_repeats

        buckets: Dict[str, int] = {}
        diverse: List[ScoredBundle] = []
        for scored in bundles:
            item_ids = scored.bundle.items or []
            new_counts = [buckets.get(str(i), 0) for i in item_ids]
            if new_counts and max(new_counts) >= max_repeats:
                continue
            for i in item_ids:
                key = str(i)
                buckets[key] = buckets.get(key, 0) + 1
            diverse.append(scored)
            if len(diverse) >= self.max_bundles:
                break

        # If diversity was too aggressive (small wardrobes), fall back to
        # filling the rest with remaining bundles in score order.
        if len(diverse) < min(len(buckets) // 2 + 1, len(bundles)):
            return bundles[: self.max_bundles]
        return diverse

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
