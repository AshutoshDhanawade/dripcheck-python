"""Tests for onboarding-based bundle personalization (score_bundle + ranking)."""

from __future__ import annotations

import os
import unittest
from types import SimpleNamespace

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dripcheck_django.settings')
import django  # noqa: E402

django.setup()

from engine.personalization_engine import (  # noqa: E402
    MAX_BUNDLE_PERSONALIZATION,
    PersonalizationEngine,
    calculate_bundle_personalization,
)
from engine.recommendation_engine import RecommendationEngine  # noqa: E402
from engine.tests.helpers import make_item  # noqa: E402


def make_bundle(bundle_id, item_ids, style_tags=None, compatibility_score=85.0):
    return SimpleNamespace(
        bundle_id=bundle_id,
        items=item_ids,
        style_tags=style_tags or [],
        compatibility_score=compatibility_score,
    )


def build_lookup(items):
    return {str(getattr(item, 'item_id', '')): item for item in items}


class BundleStyleScoringTest(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = PersonalizationEngine()

    def test_bundle_matching_a_preferred_style_gets_positive_score(self) -> None:
        items = [make_item('t1', style_tags=['Streetwear', 'Casual'])]
        bundle = make_bundle('b1', ['t1'])
        prefs = {'style_vibes': ['Streetwear', 'Minimal', 'Casual']}
        result = self.engine.score_bundle(bundle, prefs, build_lookup(items))
        self.assertGreater(result.breakdown['style_score'], 0.0)

    def test_fully_matching_styles_get_max_style_score(self) -> None:
        items = [make_item('t1', style_tags=['Streetwear'])]
        bundle = make_bundle('b1', ['t1'])
        prefs = {'style_vibes': ['Streetwear']}
        result = self.engine.score_bundle(bundle, prefs, build_lookup(items))
        self.assertEqual(result.breakdown['style_score'], 10.0)

    def test_no_matching_styles_get_zero(self) -> None:
        items = [make_item('t1', style_tags=['Formal'])]
        bundle = make_bundle('b1', ['t1'])
        prefs = {'style_vibes': ['Streetwear', 'Casual']}
        result = self.engine.score_bundle(bundle, prefs, build_lookup(items))
        self.assertEqual(result.breakdown['style_score'], 0.0)

    def test_style_not_double_counted_across_items(self) -> None:
        items = [
            make_item('t1', style_tags=['Streetwear']),
            make_item('b1', style_tags=['Streetwear']),
        ]
        bundle = make_bundle('b1', ['t1', 'b1'])
        prefs = {'style_vibes': ['Streetwear']}
        result = self.engine.score_bundle(bundle, prefs, build_lookup(items))
        self.assertEqual(result.breakdown['style_score'], 10.0)


class BundleClothingScoringTest(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = PersonalizationEngine()

    def test_all_items_match_preferred_clothes_get_max(self) -> None:
        items = [
            make_item('t1', category='Top', subcategory='T-Shirt'),
            make_item('b1', category='Bottom', subcategory='Cargo Pants'),
            make_item('s1', category='Footwear', subcategory='Sneakers'),
        ]
        bundle = make_bundle('b1', ['t1', 'b1', 's1'])
        prefs = {'preferred_subcategories': ['T-Shirts', 'Cargo Pants', 'Sneakers']}
        result = self.engine.score_bundle(bundle, prefs, build_lookup(items))
        self.assertEqual(result.breakdown['clothing_score'], 10.0)

    def test_partial_clothing_match_gives_smaller_score(self) -> None:
        items = [
            make_item('t1', category='Top', subcategory='Shirt'),
            make_item('b1', category='Bottom', subcategory='Jeans'),
            make_item('s1', category='Footwear', subcategory='Sneakers'),
        ]
        bundle = make_bundle('b1', ['t1', 'b1', 's1'])
        prefs = {'preferred_subcategories': ['T-Shirts', 'Cargo Pants', 'Sneakers']}
        result = self.engine.score_bundle(bundle, prefs, build_lookup(items))
        score = result.breakdown['clothing_score']
        self.assertGreater(score, 0.0)
        self.assertLess(score, 10.0)

    def test_no_clothing_match_get_zero(self) -> None:
        items = [make_item('t1', category='Top', subcategory='Hoodie')]
        bundle = make_bundle('b1', ['t1'])
        prefs = {'preferred_subcategories': ['Sneakers']}
        result = self.engine.score_bundle(bundle, prefs, build_lookup(items))
        self.assertEqual(result.breakdown['clothing_score'], 0.0)


class BundleColorScoringTest(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = PersonalizationEngine()

    def test_all_items_match_preferred_colors_get_max(self) -> None:
        items = [
            make_item('t1', primary_color='Black', color_family='Neutral'),
            make_item('b1', primary_color='Grey', color_family='Neutral'),
            make_item('s1', primary_color='White', color_family='Neutral'),
        ]
        bundle = make_bundle('b1', ['t1', 'b1', 's1'])
        prefs = {'favorite_colors': ['Black', 'White', 'Grey']}
        result = self.engine.score_bundle(bundle, prefs, build_lookup(items))
        self.assertEqual(result.breakdown['color_score'], 10.0)

    def test_partial_color_match_gives_smaller_score(self) -> None:
        items = [
            make_item('t1', primary_color='Red', color_family='Bold'),
            make_item('b1', primary_color='Blue', color_family='Bold'),
            make_item('s1', primary_color='Green', color_family='Earth'),
        ]
        bundle = make_bundle('b1', ['t1', 'b1', 's1'])
        prefs = {'favorite_colors': ['Black', 'White', 'Grey']}
        result = self.engine.score_bundle(bundle, prefs, build_lookup(items))
        self.assertEqual(result.breakdown['color_score'], 0.0)

    def test_pastel_shades_aliases_to_family(self) -> None:
        items = [make_item('t1', primary_color='Baby Pink', color_family='Pastel')]
        bundle = make_bundle('b1', ['t1'])
        prefs = {'favorite_colors': ['Pastel Shades']}
        result = self.engine.score_bundle(bundle, prefs, build_lookup(items))
        self.assertGreater(result.breakdown['color_score'], 0.0)


class BundleCombinedScoringTest(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = PersonalizationEngine()

    def test_combined_preferences_sum_into_bounded_total(self) -> None:
        items = [
            make_item('t1', category='Top', subcategory='T-Shirt',
                      primary_color='Black', style_tags=['Streetwear']),
            make_item('b1', category='Bottom', subcategory='Cargo Pants',
                      primary_color='Grey', style_tags=['Streetwear']),
            make_item('s1', category='Footwear', subcategory='Sneakers',
                      primary_color='White', style_tags=['Casual']),
        ]
        bundle = make_bundle('b1', ['t1', 'b1', 's1'])
        prefs = {
            'style_vibes': ['Streetwear', 'Casual'],
            'preferred_subcategories': ['T-Shirts', 'Cargo Pants', 'Sneakers'],
            'favorite_colors': ['Black', 'White', 'Grey'],
        }
        result = self.engine.score_bundle(bundle, prefs, build_lookup(items))
        self.assertEqual(result.breakdown['style_score'], 10.0)
        self.assertEqual(result.breakdown['clothing_score'], 10.0)
        self.assertEqual(result.breakdown['color_score'], 10.0)
        self.assertEqual(result.score, min(30.0, MAX_BUNDLE_PERSONALIZATION))

    def test_combined_result_has_three_breakdown_keys(self) -> None:
        items = [make_item('t1', subcategory='T-Shirt')]
        bundle = make_bundle('b1', ['t1'])
        prefs = {
            'style_vibes': ['Streetwear'],
            'preferred_subcategories': ['T-Shirts'],
            'favorite_colors': ['Black'],
        }
        result = self.engine.score_bundle(bundle, prefs, build_lookup(items))
        self.assertEqual(
            set(result.breakdown),
            {'style_score', 'clothing_score', 'color_score'},
        )

    def test_wrapper_matches_engine_result(self) -> None:
        items = [make_item('t1', style_tags=['Streetwear'])]
        bundle = make_bundle('b1', ['t1'])
        prefs = {'style_vibes': ['Streetwear']}
        direct = self.engine.score_bundle(bundle, prefs, build_lookup(items))
        wrapped = calculate_bundle_personalization(bundle, prefs, build_lookup(items))
        self.assertEqual(wrapped.score, direct.score)
        self.assertEqual(wrapped.breakdown, direct.breakdown)


class MissingPreferencesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = PersonalizationEngine()

    def test_no_preferences_means_zero_personalization(self) -> None:
        items = [
            make_item('t1', subcategory='T-Shirt', style_tags=['Streetwear'],
                      primary_color='Black'),
        ]
        bundle = make_bundle('b1', ['t1'])
        result = self.engine.score_bundle(bundle, {}, build_lookup(items))
        self.assertEqual(result.score, 0.0)
        self.assertEqual(result.breakdown['style_score'], 0.0)
        self.assertEqual(result.breakdown['clothing_score'], 0.0)
        self.assertEqual(result.breakdown['color_score'], 0.0)

    def test_missing_single_component_contributes_zero(self) -> None:
        items = [make_item('t1', subcategory='T-Shirt')]
        bundle = make_bundle('b1', ['t1'])
        prefs = {'preferred_subcategories': ['T-Shirts']}
        result = self.engine.score_bundle(bundle, prefs, build_lookup(items))
        self.assertEqual(result.breakdown['style_score'], 0.0)
        self.assertEqual(result.breakdown['color_score'], 0.0)
        self.assertGreater(result.breakdown['clothing_score'], 0.0)


class FinalRankingTest(unittest.TestCase):
    def test_sort_orders_by_final_score_descending(self) -> None:
        prefs = {
            'style_vibes': ['Streetwear', 'Casual'],
            'preferred_subcategories': ['T-Shirts', 'Cargo Pants', 'Sneakers'],
            'favorite_colors': ['Black', 'White', 'Grey'],
        }
        strong_items = [
            make_item('t1', category='Top', subcategory='T-Shirt',
                      primary_color='Black', style_tags=['Streetwear']),
            make_item('b1', category='Bottom', subcategory='Cargo Pants',
                      primary_color='Grey', style_tags=['Streetwear']),
            make_item('s1', category='Footwear', subcategory='Sneakers',
                      primary_color='White', style_tags=['Casual']),
        ]
        weak_items = [
            make_item('t2', category='Top', subcategory='Shirt',
                      primary_color='Red', style_tags=['Formal']),
            make_item('b2', category='Bottom', subcategory='Jeans',
                      primary_color='Red', style_tags=['Formal']),
            make_item('s2', category='Footwear', subcategory='Boots',
                      primary_color='Red', style_tags=['Formal']),
        ]
        combined = strong_items + weak_items

        pers = PersonalizationEngine()
        strong_bundle = make_bundle('strong', ['t1', 'b1', 's1'], compatibility_score=60.0)
        weak_bundle = make_bundle('weak', ['t2', 'b2', 's2'], compatibility_score=60.0)
        strong_score = pers.score_bundle(strong_bundle, prefs, build_lookup(combined)).score
        weak_score = pers.score_bundle(weak_bundle, prefs, build_lookup(combined)).score
        self.assertGreater(strong_score, weak_score)

        engine = RecommendationEngine()
        result = engine.recommend(combined, prefs, user_id='u1')
        finals = [b.final_score for b in result.bundles]
        self.assertEqual(finals, sorted(finals, reverse=True))
        for scored in result.bundles:
            self.assertEqual(
                scored.final_score,
                round(scored.base_score + scored.personalization_score, 2),
            )

        strong_ids = {'t1', 'b1', 's1'}
        weak_ids = {'t2', 'b2', 's2'}
        strong_scored = next(
            b for b in result.bundles if set(b.bundle.items) == strong_ids
        )
        weak_scored = next(
            b for b in result.bundles if set(b.bundle.items) == weak_ids
        )
        self.assertGreaterEqual(
            strong_scored.personalization_score, weak_scored.personalization_score
        )

    def test_scores_are_secondary_ranking_signal(self) -> None:
        prefs = {
            'style_vibes': ['Streetwear'],
            'preferred_subcategories': ['Sneakers'],
            'favorite_colors': ['Black'],
        }
        items = [
            make_item('t1', category='Top', subcategory='T-Shirt',
                      primary_color='Black', style_tags=['Streetwear']),
            make_item('b1', category='Bottom', subcategory='Cargo Pants',
                      primary_color='Black', style_tags=['Streetwear']),
            make_item('s1', category='Footwear', subcategory='Sneakers',
                      primary_color='Black', style_tags=['Streetwear']),
        ]
        engine = RecommendationEngine()
        result = engine.recommend(items, prefs, user_id='u1')
        for scored in result.bundles:
            self.assertLessEqual(scored.personalization_score, MAX_BUNDLE_PERSONALIZATION)
            self.assertEqual(scored.base_score, round(scored.base_score, 2))


if __name__ == '__main__':
    unittest.main()