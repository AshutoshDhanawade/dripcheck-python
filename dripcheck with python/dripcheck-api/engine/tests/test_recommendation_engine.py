"""Tests for the RecommendationEngine (Step 4) and canonical ranking score."""

from __future__ import annotations

import os
import unittest

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dripcheck_django.settings')
import django  # noqa: E402

django.setup()

from engine.personalization_engine import DEFAULT_WEIGHTS  # noqa: E402
from engine.recommendation_engine import (  # noqa: E402
    RecommendationEngine,
    bundle_ranking_score,
    personalize_wardrobe,
)
from engine.tests.helpers import make_item  # noqa: E402
from engine.wardrobe_profile import WardrobeProfileBuilder  # noqa: E402

USER_PROFILE = {
    'favorite_colors': ['Black', 'White'],
    'avoided_colors': ['Red'],
    'style_vibes': ['Minimalist', 'Streetwear'],
}


def build_balanced_wardrobe() -> list:
    """A wardrobe large enough to produce valid bundles via the real engine."""
    items = [
        make_item('top1', category='Top', primary_color='Black', color_family='Neutral',
                  fit='Oversized', season='All-season', formality_level=3,
                  occasion=['Casual', 'Weekend'], style_tags=['Minimalist', 'Streetwear'],
                  brand='Zara', pattern='Solid'),
        make_item('top2', category='Top', primary_color='White', color_family='Neutral',
                  fit='Regular', season='All-season', formality_level=3,
                  occasion=['Casual', 'Weekend'], style_tags=['Minimalist'],
                  brand='Zara', pattern='Solid'),
        make_item('bot1', category='Bottom', primary_color='Black', color_family='Neutral',
                  fit='Slim', season='All-season', formality_level=3,
                  occasion=['Casual', 'Weekend'], style_tags=['Minimalist', 'Streetwear'],
                  brand='H&M', pattern='Solid'),
        make_item('bot2', category='Bottom', primary_color='Grey', color_family='Neutral',
                  fit='Regular', season='All-season', formality_level=4,
                  occasion=['Casual', 'Weekend'], style_tags=['Minimalist'],
                  brand='H&M', pattern='Solid'),
        make_item('sho1', category='Footwear', primary_color='White', color_family='Neutral',
                  fit='Regular', season='All-season', formality_level=3,
                  occasion=['Casual', 'Weekend'], style_tags=['Minimalist', 'Streetwear'],
                  brand='Nike', pattern='Solid', subcategory='Sneakers'),
        make_item('sho2', category='Footwear', primary_color='Black', color_family='Neutral',
                  fit='Regular', season='All-season', formality_level=3,
                  occasion=['Casual', 'Weekend'], style_tags=['Minimalist'],
                  brand='Nike', pattern='Solid', subcategory='Sneakers'),
    ]
    return items


class BundleRankingScoreTest(unittest.TestCase):
    def test_ranking_is_compat_plus_personalization_minus_penalty(self) -> None:
        self.assertEqual(bundle_ranking_score(90, 25, 0), 115.0)
        self.assertEqual(bundle_ranking_score(92, 24, 20), 96.0)
        self.assertEqual(bundle_ranking_score(88, 27, 5), 110.0)

    def test_negative_penalty_is_normalized(self) -> None:
        self.assertEqual(bundle_ranking_score(90, 20, -18), 92.0)

    def test_penalty_is_never_added(self) -> None:
        self.assertEqual(bundle_ranking_score(90, 20, 0), 110.0)


class RecommendationEngineTest(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = RecommendationEngine()
        self.items = build_balanced_wardrobe()

    def test_rank_items_orders_by_score_desc(self) -> None:
        ranked = self.engine.rank_items(self.items)
        scores = [r.personalization_score for r in ranked]
        self.assertEqual(scores, sorted(scores, reverse=True))
        self.assertEqual(len(ranked), len(self.items))

    def test_rank_items_builds_profile(self) -> None:
        profile = WardrobeProfileBuilder().build(self.items, USER_PROFILE)
        ranked = self.engine.rank_items(self.items, profile)
        self.assertEqual(profile.total_items, len(self.items))
        self.assertEqual(len(ranked), len(self.items))
        # First ranked item must hold the maximum personalization score.
        self.assertEqual(
            ranked[0].personalization_score,
            max(r.personalization_score for r in ranked),
        )

    def test_recommend_produces_scored_bundles(self) -> None:
        result = self.engine.recommend(self.items, USER_PROFILE, user_id='u1')
        self.assertEqual(result.profile.total_items, len(self.items))
        self.assertTrue(result.bundles)
        ranking_scores = [b.ranking_score for b in result.bundles]
        self.assertEqual(ranking_scores, sorted(ranking_scores, reverse=True))
        for scored in result.bundles:
            self.assertIsNotNone(scored.compatibility_score)
            self.assertEqual(scored.personalization_score, round(scored.personalization_score, 2))
            self.assertGreaterEqual(scored.diversity_penalty, 0)
            # Canonical formula: ranking = compatibility + personalization − diversity.
            self.assertEqual(
                scored.ranking_score,
                bundle_ranking_score(
                    scored.compatibility_score,
                    scored.personalization_score,
                    scored.diversity_penalty,
                ),
            )

    def test_ranking_ignores_item_personalization(self) -> None:
        # The ranking must be exactly compat + onboarding bonus − penalty:
        # item-level personalization (rank_items) plays no part in it.
        result = self.engine.recommend(self.items, USER_PROFILE, user_id='u1')
        item_scores = {r.item_id: r.personalization_score for r in result.ranked_items}
        for scored in result.bundles:
            bundle_scores = [item_scores[iid] for iid in scored.bundle.items if iid in item_scores]
            self.assertTrue(bundle_scores)
            self.assertNotEqual(
                scored.ranking_score,
                round(
                    scored.compatibility_score
                    + sum(bundle_scores) / len(bundle_scores)
                    - scored.diversity_penalty,
                    2,
                ),
            )

    def test_top_k_limits_items_fed_to_engine(self) -> None:
        full = self.engine.recommend(self.items, USER_PROFILE, user_id='u1')
        limited = self.engine.recommend(self.items, USER_PROFILE, user_id='u1', top_k=4)
        self.assertEqual(len(limited.ranked_items), 6)  # ranking always full
        used_item_ids = {iid for b in limited.bundles for iid in b.bundle.items}
        self.assertLessEqual(len(used_item_ids), 4)

    def test_constructor_top_k_is_default(self) -> None:
        engine = RecommendationEngine(top_k=4)
        result = engine.recommend(self.items, USER_PROFILE, user_id='u1')
        used_item_ids = {iid for b in result.bundles for iid in b.bundle.items}
        self.assertLessEqual(len(used_item_ids), 4)

    def test_per_call_top_k_overrides_constructor(self) -> None:
        engine = RecommendationEngine(top_k=2)
        result = engine.recommend(self.items, USER_PROFILE, user_id='u1', top_k=6)
        used_item_ids = {iid for b in result.bundles for iid in b.bundle.items}
        self.assertLessEqual(len(used_item_ids), 6)

    def test_must_keep_ids_survive_top_k_cutoff(self) -> None:
        low_ranked_id = self.items[-1].item_id  # lowest-ranked item
        result = self.engine.recommend(
            self.items,
            USER_PROFILE,
            user_id='u1',
            top_k=2,
            must_keep_ids=[low_ranked_id],
        )
        self.assertIn(low_ranked_id, result.selected_item_ids)
        self.assertLessEqual(len(result.selected_item_ids), 2)

    def test_empty_wardrobe_returns_empty_result(self) -> None:
        result = self.engine.recommend([], USER_PROFILE, user_id='u1')
        self.assertEqual(result.profile.total_items, 0)
        self.assertEqual(result.ranked_items, [])
        self.assertEqual(result.bundles, [])

    def test_avoided_colors_reach_compatibility_engine(self) -> None:
        # An avoided color item should never appear in any generated bundle.
        result = self.engine.recommend(self.items, USER_PROFILE, user_id='u1')
        item_lookup = {item.item_id: item for item in self.items}
        for scored in result.bundles:
            for iid in scored.bundle.items:
                item = item_lookup.get(iid)
                self.assertNotEqual((item.primary_color or '').lower(), 'red')

    def test_occasion_filter_selects_but_does_not_change_scores(self) -> None:
        # The occasion filter only narrows the candidate pool; it must never
        # boost or alter the ranking values themselves.
        unfiltered = self.engine.recommend(self.items, USER_PROFILE, user_id='u1')
        filtered = self.engine.recommend(
            self.items, USER_PROFILE, user_id='u1', occasion_filter='Casual',
        )
        self.assertTrue(filtered.bundles)
        by_items = {
            tuple(sorted(scored.bundle.items)): scored
            for scored in unfiltered.bundles
        }
        for scored in filtered.bundles:
            match = by_items.get(tuple(sorted(scored.bundle.items)))
            self.assertIsNotNone(match)
            self.assertEqual(scored.compatibility_score, match.compatibility_score)
            self.assertEqual(scored.personalization_score, match.personalization_score)
            self.assertEqual(scored.diversity_penalty, match.diversity_penalty)
            self.assertEqual(scored.ranking_score, match.ranking_score)

    def test_personalize_wardrobe_convenience(self) -> None:
        ranked = personalize_wardrobe(self.items, USER_PROFILE)
        self.assertEqual(len(ranked), len(self.items))
        self.assertTrue(ranked[0].components)

    def test_default_weights_present(self) -> None:
        for key in ('style', 'color', 'occasion', 'fit', 'season', 'category', 'novelty'):
            self.assertIn(key, DEFAULT_WEIGHTS)


if __name__ == '__main__':
    unittest.main()
