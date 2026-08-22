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
        -> PersonalizationEngine.score_bundle()     (onboarding bonus, 0–30)
        -> compute_diversity_penalties()            (BEFORE ranking)
        -> ranking_score = compatibility + personalization − diversity penalty

The compatibility engine remains the source of truth for *can these items be
worn together*; this layer only re-ranks which bundles surface for a
specific user. There is exactly ONE ranking formula:

    ranking_score = compatibility_score + personalization_score
                    − diversity_penalty

No other score layers exist (no weighted blend, no occasion dimension, no
item-level personalization in the bundle ranking).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from api.models import OutfitBundle, UserProfile, WardrobeItem

from engine.compatibility_engine import (
    bundle_diversity_profile,
    diversity_breakdown_penalties,
    generate_bundles,
    similarity_penalty_between,
)
from engine.personalization_engine import (
    BundlePersonalizationResult,
    PersonalizationEngine,
    PersonalizationResult,
)
from engine.wardrobe_profile import WardrobeProfile, WardrobeProfileBuilder


def bundle_ranking_score(
    compatibility_score: float,
    personalization_score: float,
    diversity_penalty: float = 0.0,
) -> float:
    """Canonical bundle ranking score: compatibility + personalization − diversity.

    The diversity penalty is always SUBTRACTED regardless of its sign, so a
    penalty stored as ``20`` or ``-20`` never double-counts.
    """
    return round(
        float(compatibility_score)
        + float(personalization_score)
        - abs(float(diversity_penalty or 0.0)),
        2,
    )


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
    """A generated bundle enriched with its canonical ranking score.

    ``ranking_score = compatibility_score + personalization_score −
    diversity_penalty`` — the single formula that drives ordering everywhere
    (see :func:`bundle_ranking_score`). ``personalization_score`` is the
    bounded onboarding bonus (0–30) computed by
    :meth:`PersonalizationEngine.score_bundle`. ``diversity_penalty`` /
    ``diversity_breakdown`` are computed by :func:`compute_diversity_penalties`
    BEFORE the bundles are ranked, so diversity genuinely affects ordering.
    """

    bundle: OutfitBundle
    compatibility_score: float
    personalization_score: float
    ranking_score: float = 0.0
    diversity_penalty: float = 0.0
    diversity_breakdown: Dict[str, float] = field(default_factory=dict)
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
        top_k: Optional[int] = None,
    ):
        self.personalizer = PersonalizationEngine(weights=weights)
        self.profile_builder = WardrobeProfileBuilder()
        self.top_k = top_k

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

        The FULL ranked bundle list is returned: every valid combination is
        scored and ranked by ``ranking_score`` (compatibility + onboarding
        personalization − diversity penalty). Diversity is computed BEFORE the
        sort so it genuinely affects the order.
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

        item_lookup = {str(getattr(item, 'item_id', '')): item for item in items}
        onboarding_preferences = profile.onboarding_preferences

        bundles = [
            self._score_bundle(
                bundle,
                item_lookup,
                onboarding_preferences,
            )
            for bundle in raw_bundles
        ]

        # Diversity is part of the canonical ranking score, so it must be
        # computed BEFORE ordering:
        #   ranking_score = compatibility + personalization − diversity penalty
        compute_diversity_penalties(bundles, item_lookup=item_lookup)
        for scored in bundles:
            bundle = scored.bundle
            scored.ranking_score = bundle_ranking_score(
                scored.compatibility_score,
                scored.personalization_score,
                scored.diversity_penalty,
            )
            bundle.ranking_score = scored.ranking_score
            bundle.personalization_score = scored.personalization_score

        bundles.sort(key=lambda scored: scored.ranking_score, reverse=True)

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
        item_lookup: Optional[Dict[str, WardrobeItem]] = None,
        user_preferences: Optional[Dict[str, Any]] = None,
    ) -> ScoredBundle:
        # Onboarding personalization bonus (0–30): the only personalization
        # signal that feeds the canonical ranking score.
        pers: BundlePersonalizationResult = self.personalizer.score_bundle(
            bundle=bundle,
            user_preferences=user_preferences,
            item_lookup=item_lookup,
        )

        return ScoredBundle(
            bundle=bundle,
            compatibility_score=bundle.compatibility_score,
            personalization_score=round(pers.score, 2),
            breakdown=pers.breakdown,
            reasons=pers.reasons,
        )


def compute_diversity_penalties(
    bundles: List,
    item_lookup: Optional[Dict[str, WardrobeItem]] = None,
) -> List:
    """Compute the diversity penalty for every bundle in a result set.

    For each bundle this computes the worst ``similarity_penalty_between``
    score against the OTHER bundles in the same set and stores:

      * ``diversity_penalty`` — points to subtract (always positive),
      * ``diversity_breakdown`` — numeric per-component penalty map
        (sums back to ``diversity_penalty``).

    The penalty is attached to both the wrapper (``ScoredBundle``) and the
    underlying bundle object so serializers can expose it. This runs BEFORE
    ranking so the penalty is part of the canonical
    ``ranking_score = compatibility + personalization − diversity penalty``.
    """
    if not bundles:
        return bundles

    def _bundle_obj(obj):
        return getattr(obj, 'bundle', obj)

    profiles = [
        bundle_diversity_profile(_bundle_obj(scored), item_lookup)
        for scored in bundles
    ]

    for i, scored in enumerate(bundles):
        worst_penalty = 0.0
        worst_breakdown: Dict[str, bool] = {}
        for j, other in enumerate(bundles):
            if i == j:
                continue
            penalty, breakdown = similarity_penalty_between(profiles[i], profiles[j])
            if penalty > worst_penalty:
                worst_penalty = penalty
                worst_breakdown = breakdown

        penalty = round(worst_penalty, 2)
        breakdown = diversity_breakdown_penalties(worst_breakdown)
        setattr(scored, 'diversity_penalty', penalty)
        setattr(scored, 'diversity_breakdown', breakdown)
        bundle = _bundle_obj(scored)
        bundle.diversity_penalty = penalty
        bundle.diversity_breakdown = breakdown

    return bundles


def personalize_wardrobe(
    items: List[WardrobeItem],
    user_profile: Optional[Any] = None,
    weights: Optional[Dict[str, float]] = None,
) -> List[ItemRanking]:
    """Convenience wrapper: build the profile and rank items only."""
    engine = RecommendationEngine(weights=weights)
    profile = engine.profile_builder.build(items, user_profile)
    return engine.rank_items(items, profile)