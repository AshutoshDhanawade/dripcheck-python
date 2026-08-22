"""Tests for the scoring breakdown attachment.

Verifies that bundles carry the real scoring values (compatibility /
personalization / diversity penalty / ranking score) as metadata and that
diversity is computed BEFORE ranking so it genuinely affects ordering.
"""

from __future__ import annotations

import os
import unittest
from types import SimpleNamespace

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dripcheck_django.settings')
import django  # noqa: E402

django.setup()

from engine.compatibility_engine import (  # noqa: E402
    DIVERSITY_PENALTIES,
    bundle_diversity_profile,
    diversity_breakdown_penalties,
    similarity_penalty_between,
)
from engine.recommendation_engine import (  # noqa: E402
    RecommendationEngine,
    bundle_ranking_score,
    compute_diversity_penalties,
)
from engine.tests.helpers import make_item  # noqa: E402

USER_PROFILE = {
    'favorite_colors': ['Black', 'White'],
    'avoided_colors': ['Red'],
    'style_vibes': ['Minimalist', 'Streetwear'],
}


def make_scored(bundle_id, item_ids, compatibility_score, personalization_score=0.0):
    return SimpleNamespace(
        bundle=SimpleNamespace(
            bundle_id=bundle_id,
            items=item_ids,
            style_tags=[],
            compatibility_score=compatibility_score,
        ),
        compatibility_score=compatibility_score,
        personalization_score=personalization_score,
    )


def build_lookup(items):
    return {str(getattr(item, 'item_id', '')): item for item in items}


def make_item_exact(item_id, category, primary_color='X', fit='X'):
    return make_item(
        item_id,
        category=category,
        primary_color=primary_color,
        color_family='Neutral',
        fit=fit,
        style_tags=[],
        occasion=[],
    )


def _penalty_sum(breakdown):
    return round(sum((breakdown or {}).values()), 2)


class DiversityBreakdownPenaltiesTest(unittest.TestCase):
    def test_boolean_breakdown_maps_to_configured_numbers(self) -> None:
        breakdown = {'same_top': True, 'same_bottom': False, 'same_footwear': True}
        numeric = diversity_breakdown_penalties(breakdown)
        self.assertEqual(numeric['same_top'], DIVERSITY_PENALTIES['same_top'])
        self.assertEqual(numeric['same_bottom'], 0)
        self.assertEqual(numeric['same_footwear'], DIVERSITY_PENALTIES['same_footwear'])

    def test_numeric_breakdown_sums_to_similarity_penalty(self) -> None:
        items = [
            make_item_exact('t1', 'Top', primary_color='Blue', fit='Slim'),
            make_item_exact('t2', 'Top', primary_color='Green', fit='Relaxed'),
            make_item_exact('b1', 'Bottom', primary_color='Yellow', fit='Regular'),
            make_item_exact('b2', 'Bottom', primary_color='Purple', fit='Oversized'),
            make_item_exact('s1', 'Footwear', primary_color='Red', fit='Baggy'),
            make_item_exact('s2', 'Footwear', primary_color='White', fit='Tapered'),
        ]
        lookup = build_lookup(items)
        pf = lambda ids: bundle_diversity_profile(SimpleNamespace(items=ids), lookup)
        a = pf(['t1', 'b1', 's1'])
        b = pf(['t1', 'b2', 's1'])  # same top + same shoe
        penalty, breakdown = similarity_penalty_between(a, b)
        numeric = diversity_breakdown_penalties(breakdown)
        self.assertEqual(_penalty_sum(numeric), penalty)
        self.assertEqual(numeric['same_top'], DIVERSITY_PENALTIES['same_top'])
        self.assertEqual(numeric['same_footwear'], DIVERSITY_PENALTIES['same_footwear'])

    def test_empty_breakdown_yields_all_zeroes(self) -> None:
        self.assertEqual(diversity_breakdown_penalties({}), {})


class ComputeDiversityPenaltiesTest(unittest.TestCase):
    def _make_wardrobe(self):
        return [
            make_item('t1', category='Top', primary_color='Blue', fit='Slim'),
            make_item('t2', category='Top', primary_color='Green', fit='Relaxed'),
            make_item('b1', category='Bottom', primary_color='Yellow', fit='Regular'),
            make_item('b2', category='Bottom', primary_color='Purple', fit='Oversized'),
            make_item('s1', category='Footwear', primary_color='Red', fit='Baggy'),
            make_item('s2', category='Footwear', primary_color='White', fit='Tapered'),
        ]

    def test_repeated_top_is_detected(self) -> None:
        lookup = build_lookup(self._make_wardrobe())
        bundles = [
            make_scored('A', ['t1', 'b1', 's1'], 100),
            make_scored('B', ['t1', 'b2', 's2'], 98),  # shares top t1
        ]
        compute_diversity_penalties(bundles, item_lookup=lookup)
        by_id = {b.bundle.bundle_id: b for b in bundles}
        # Both bundles are penalized for sharing t1; the shared top's own
        # color/fit also match, exactly like the existing similarity engine.
        expected = (
            DIVERSITY_PENALTIES['same_top']
            + DIVERSITY_PENALTIES['same_color']
            + DIVERSITY_PENALTIES['same_fit']
        )
        for scored in by_id.values():
            self.assertEqual(scored.diversity_penalty, expected)
            self.assertGreaterEqual(
                scored.diversity_breakdown.get('same_top', 0),
                DIVERSITY_PENALTIES['same_top'],
            )
            self.assertEqual(
                scored.diversity_penalty,
                _penalty_sum(scored.diversity_breakdown),
            )

    def test_fully_different_bundles_have_zero_penalty(self) -> None:
        lookup = build_lookup(self._make_wardrobe())
        bundles = [
            make_scored('A', ['t1', 'b1', 's1'], 100),
            make_scored('B', ['t2', 'b2', 's2'], 90),
        ]
        compute_diversity_penalties(bundles, item_lookup=lookup)
        for scored in bundles:
            self.assertEqual(scored.diversity_penalty, 0)
            self.assertEqual(scored.diversity_breakdown, {})

    def test_same_top_and_bottom_penalty_is_stronger(self) -> None:
        lookup = build_lookup(self._make_wardrobe())
        bundles = [
            make_scored('A', ['t1', 'b1', 's1'], 100),
            make_scored('B', ['t1', 'b1', 's2'], 98),  # same top + bottom
            make_scored('C', ['t1', 'b2', 's2'], 97),  # same top only
        ]
        compute_diversity_penalties(bundles, item_lookup=lookup)
        by_id = {b.bundle.bundle_id: b for b in bundles}
        self.assertGreater(
            by_id['B'].diversity_penalty,
            by_id['C'].diversity_penalty,
        )
        self.assertGreaterEqual(
            by_id['B'].diversity_breakdown.get('same_bottom', 0),
            DIVERSITY_PENALTIES['same_bottom'],
        )
        self.assertEqual(
            by_id['B'].diversity_penalty,
            _penalty_sum(by_id['B'].diversity_breakdown),
        )

    def test_penalty_attached_to_wrapper_and_bundle(self) -> None:
        lookup = build_lookup(self._make_wardrobe())
        bundles = [
            make_scored('A', ['t1', 'b1', 's1'], 100),
            make_scored('B', ['t1', 'b2', 's2'], 98),
        ]
        compute_diversity_penalties(bundles, item_lookup=lookup)
        for scored in bundles:
            self.assertEqual(scored.bundle.diversity_penalty, scored.diversity_penalty)
            self.assertEqual(scored.bundle.diversity_breakdown, scored.diversity_breakdown)

    def test_single_bundle_has_no_penalty(self) -> None:
        lookup = build_lookup(self._make_wardrobe())
        bundles = [make_scored('A', ['t1', 'b1', 's1'], 100)]
        compute_diversity_penalties(bundles, item_lookup=lookup)
        self.assertEqual(bundles[0].diversity_penalty, 0)
        self.assertEqual(bundles[0].diversity_breakdown, {})


class BundleRankingScoreTest(unittest.TestCase):
    def test_ranking_is_compat_plus_personalization_minus_penalty(self) -> None:
        self.assertEqual(bundle_ranking_score(90, 25, 0), 115.0)
        self.assertEqual(bundle_ranking_score(92, 24, 20), 96.0)
        self.assertEqual(bundle_ranking_score(88, 27, 5), 110.0)

    def test_negative_penalty_is_normalized(self) -> None:
        # A penalty stored as -18 must not be double-subtracted (or added).
        self.assertEqual(bundle_ranking_score(90, 20, -18), 92.0)

    def test_ranking_orders_the_example_triple(self) -> None:
        a = bundle_ranking_score(90, 25, 0)   # 115
        b = bundle_ranking_score(92, 24, 20)  # 96
        c = bundle_ranking_score(88, 27, 5)   # 110
        self.assertEqual(sorted([a, b, c], reverse=True), [a, c, b])

    def test_rounding(self) -> None:
        self.assertEqual(bundle_ranking_score(70.0, 16.67, 58), 28.67)


class RecommendationEngineDebugMetadataTest(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = RecommendationEngine()
        self.items = [
            make_item('top1', category='Top', primary_color='Black', color_family='Neutral',
                      fit='Oversized', season='All-season', formality_level=3,
                      occasion=['Casual', 'Weekend'], style_tags=['Minimalist'],
                      brand='Zara', pattern='Solid'),
            make_item('top2', category='Top', primary_color='White', color_family='Neutral',
                      fit='Regular', season='All-season', formality_level=3,
                      occasion=['Casual', 'Weekend'], style_tags=['Minimalist'],
                      brand='Zara', pattern='Solid'),
            make_item('bot1', category='Bottom', primary_color='Black', color_family='Neutral',
                      fit='Slim', season='All-season', formality_level=3,
                      occasion=['Casual', 'Weekend'], style_tags=['Minimalist'],
                      brand='H&M', pattern='Solid'),
            make_item('bot2', category='Bottom', primary_color='Grey', color_family='Neutral',
                      fit='Regular', season='All-season', formality_level=4,
                      occasion=['Casual', 'Weekend'], style_tags=['Minimalist'],
                      brand='H&M', pattern='Solid'),
            make_item('sho1', category='Footwear', primary_color='White', color_family='Neutral',
                      fit='Regular', season='All-season', formality_level=3,
                      occasion=['Casual', 'Weekend'], style_tags=['Minimalist'],
                      brand='Nike', pattern='Solid', subcategory='Sneakers'),
            make_item('sho2', category='Footwear', primary_color='Black', color_family='Neutral',
                      fit='Regular', season='All-season', formality_level=3,
                      occasion=['Casual', 'Weekend'], style_tags=['Minimalist'],
                      brand='Nike', pattern='Solid', subcategory='Sneakers'),
        ]

    def test_every_bundle_carries_real_scoring_values(self) -> None:
        result = self.engine.recommend(self.items, USER_PROFILE, user_id='u1')
        self.assertTrue(result.bundles)
        for scored in result.bundles:
            bundle = scored.bundle
            self.assertEqual(bundle.compatibility_score, scored.compatibility_score)
            self.assertEqual(bundle.personalization_score, scored.personalization_score)
            self.assertEqual(bundle.ranking_score, scored.ranking_score)
            # Backend math: ranking = compatibility + personalization − diversity.
            self.assertEqual(
                scored.ranking_score,
                bundle_ranking_score(
                    scored.compatibility_score,
                    scored.personalization_score,
                    scored.diversity_penalty,
                ),
            )
            # Diversity metadata is consistent (penalty == sum of components).
            self.assertGreaterEqual(scored.diversity_penalty, 0)
            self.assertEqual(
                scored.diversity_penalty,
                _penalty_sum(scored.diversity_breakdown),
            )
            self.assertEqual(bundle.diversity_penalty, scored.diversity_penalty)
            self.assertEqual(bundle.diversity_breakdown, scored.diversity_breakdown)

    def test_same_top_bundle_reports_diversity_penalty(self) -> None:
        result = self.engine.recommend(self.items, USER_PROFILE, user_id='u1')
        shared_tops = {}
        for scored in result.bundles:
            for other in result.bundles:
                if other is scored:
                    continue
                shared = set(scored.bundle.items) & set(other.bundle.items)
                if shared and scored.bundle.items[0] == other.bundle.items[0]:
                    shared_tops[scored.bundle.bundle_id] = scored
                    break
        self.assertTrue(shared_tops, 'expected at least one bundle sharing a top')
        for scored in shared_tops.values():
            self.assertGreater(scored.diversity_penalty, 0)
            self.assertGreaterEqual(
                scored.diversity_breakdown.get('same_top', 0),
                DIVERSITY_PENALTIES['same_top'],
            )

    def test_bundles_sorted_by_ranking_score_desc(self) -> None:
        result = self.engine.recommend(self.items, USER_PROFILE, user_id='u1')
        ranking_scores = [scored.ranking_score for scored in result.bundles]
        self.assertEqual(ranking_scores, sorted(ranking_scores, reverse=True))


if __name__ == '__main__':
    unittest.main()