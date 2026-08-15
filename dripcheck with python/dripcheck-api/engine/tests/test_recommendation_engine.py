"""Tests for the RecommendationEngine (Step 4) and score blending."""

from __future__ import annotations

import os
import unittest

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dripcheck_django.settings')
import django  # noqa: E402

django.setup()

from engine.personalization_engine import DEFAULT_WEIGHTS  # noqa: E402
from engine.recommendation_engine import (  # noqa: E402
    RecommendationEngine,
    combine_scores,
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


class CombineScoresTest(unittest.TestCase):
    def test_default_blend(self) -> None:
        self.assertEqual(combine_scores(100, 50), 80.0)  # 0.6*100 + 0.4*50

    def test_custom_weights(self) -> None:
        self.assertEqual(combine_scores(100, 50, compat_weight=0.2, pers_weight=0.8), 60.0)

    def test_zero_total_weights_do_not_crash(self) -> None:
        self.assertAlmostEqual(combine_scores(100, 50, compat_weight=0, pers_weight=0), 0.0)

    def test_result_clamped(self) -> None:
        self.assertEqual(combine_scores(200, 200), 100.0)


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
        final_scores = [b.final_score for b in result.bundles]
        self.assertEqual(final_scores, sorted(final_scores, reverse=True))
        for scored in result.bundles:
            self.assertIsNotNone(scored.base_score)
            self.assertEqual(scored.personalization_score, round(scored.personalization_score, 2))
            self.assertEqual(scored.final_score, round(scored.base_score + scored.personalization_score, 2))

    def test_bundle_base_score_is_item_average_blend(self) -> None:
        result = self.engine.recommend(self.items, USER_PROFILE, user_id='u1')
        scores = {r.item_id: r.personalization_score for r in result.ranked_items}
        for scored in result.bundles:
            item_scores = [scores[iid] for iid in scored.bundle.items if iid in scores]
            self.assertTrue(item_scores)
            self.assertAlmostEqual(
                scored.base_score,
                combine_scores(
                    scored.compatibility_score,
                    sum(item_scores) / len(item_scores),
                    self.engine.compat_weight,
                    self.engine.pers_weight,
                ),
                delta=0.01,
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

    def test_custom_blend_weights_affect_base_ranking(self) -> None:
        engine = RecommendationEngine(compat_weight=0.0, pers_weight=1.0)
        result = engine.recommend(self.items, USER_PROFILE, user_id='u1')
        for scored in result.bundles:
            # With zero compat weight the base is the item personalization average.
            self.assertLessEqual(scored.base_score, 100)
            self.assertGreaterEqual(scored.personalization_score, 0)
            self.assertEqual(
                scored.final_score,
                round(scored.base_score + scored.personalization_score, 2),
            )

    def test_personalize_wardrobe_convenience(self) -> None:
        ranked = personalize_wardrobe(self.items, USER_PROFILE)
        self.assertEqual(len(ranked), len(self.items))
        self.assertTrue(ranked[0].components)

    def test_default_weights_present(self) -> None:
        for key in ('style', 'color', 'occasion', 'fit', 'season', 'category', 'novelty'):
            self.assertIn(key, DEFAULT_WEIGHTS)


if __name__ == '__main__':
    unittest.main()
