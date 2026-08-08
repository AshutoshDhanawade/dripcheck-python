"""Tests for the PersonalizationEngine (Steps 2 & 3)."""

from __future__ import annotations

import os
import unittest

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dripcheck_django.settings')
import django  # noqa: E402

django.setup()

from engine.personalization_engine import (  # noqa: E402
    DEFAULT_WEIGHTS,
    PersonalizationEngine,
    calculate_personalization_score,
    normalize_weights,
)
from engine.tests.helpers import make_item  # noqa: E402
from engine.wardrobe_profile import WardrobeProfile, WardrobeProfileBuilder  # noqa: E402

PROFILE = WardrobeProfile(
    total_items=20,
    dominant_colors=['Black', 'Grey'],
    dominant_color_families=['Neutral', 'Dark'],
    color_distribution={'Black': 10, 'Grey': 5, 'Navy': 5},
    color_family_distribution={'Neutral': 15, 'Dark': 5},
    style_distribution={'minimalist': 10, 'streetwear': 5},
    occasion_distribution={'casual': 12, 'weekend': 6},
    category_counts={'Top': 18, 'Bottom': 5, 'Footwear': 2, 'Layer': 0, 'Accessory': 0},
    fit_distribution={'Oversized': 10, 'Regular': 6},
    season_distribution={'All-season': 15, 'Winter': 5},
    formality_distribution={3: 14, 5: 6},
    pattern_distribution={'Solid': 16, 'Stripes': 4},
    favorite_brands=['Zara'],
    onboarding_preferences={
        'favorite_colors': ['Black'],
        'avoided_colors': ['Red'],
        'style_vibes': ['Minimalist'],
    },
    avoided_colors=['red'],
)


class StyleScoringTest(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = PersonalizationEngine()

    def test_matches_preferred_style(self) -> None:
        item = make_item('t1', style_tags=['Minimalist'])
        score, reasons = self.engine.style_score(item, PROFILE)
        self.assertEqual(score, 100.0)
        self.assertTrue(any('preferred style' in r for r in reasons))

    def test_matches_popular_wardrobe_style(self) -> None:
        item = make_item('t1', style_tags=['Streetwear'])
        score, _ = self.engine.style_score(item, PROFILE)
        self.assertGreater(score, 50.0)

    def test_unknown_style_scores_zero(self) -> None:
        item = make_item('t1', style_tags=['Grunge'])
        score, reasons = self.engine.style_score(item, PROFILE)
        self.assertEqual(score, 0.0)
        self.assertTrue(any('new to this wardrobe' in r for r in reasons))

    def test_no_style_tags_returns_neutral(self) -> None:
        item = make_item('t1', style_tags=[])
        score, _ = self.engine.style_score(item, PROFILE)
        self.assertEqual(score, 50.0)


class ColorScoringTest(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = PersonalizationEngine()

    def test_favorite_color_scores_highest(self) -> None:
        item = make_item('t1', primary_color='Black', color_family='Neutral')
        score, _ = self.engine.color_score(item, PROFILE)
        self.assertEqual(score, 100.0)

    def test_dominant_wardrobe_color_high(self) -> None:
        item = make_item('t1', primary_color='Grey', color_family='Neutral')
        score, _ = self.engine.color_score(item, PROFILE)
        self.assertEqual(score, 85.0)

    def test_dominant_family_medium(self) -> None:
        item = make_item('t1', primary_color='White', color_family='Neutral')
        score, _ = self.engine.color_score(item, PROFILE)
        self.assertEqual(score, 70.0)

    def test_fresh_color_neutral(self) -> None:
        item = make_item('t1', primary_color='Purple', color_family='Bold')
        score, _ = self.engine.color_score(item, PROFILE)
        self.assertEqual(score, 45.0)

    def test_avoided_color_strongly_penalized(self) -> None:
        item = make_item('t1', primary_color='Red', color_family='Bold')
        score, reasons = self.engine.color_score(item, PROFILE)
        self.assertEqual(score, 10.0)
        self.assertTrue(any('avoided' in r for r in reasons))

    def test_avoided_family_strongly_penalized(self) -> None:
        item = make_item('t1', primary_color='Crimson', color_family='Neutral')
        profile = WardrobeProfile(**{**PROFILE.__dict__, 'avoided_colors': ['neutral']})
        score, _ = self.engine.color_score(item, profile)
        self.assertEqual(score, 10.0)


class OccasionFitSeasonTest(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = PersonalizationEngine()

    def test_frequent_occasion_scores_high(self) -> None:
        item = make_item('t1', occasion=['Casual'])
        score, reasons = self.engine.occasion_score(item, PROFILE)
        self.assertGreaterEqual(score, 60.0)
        self.assertTrue(any('frequent occasion' in r for r in reasons))

    def test_rare_occasion_scores_low(self) -> None:
        item = make_item('t1', occasion=['Formal'])
        score, reasons = self.engine.occasion_score(item, PROFILE)
        self.assertEqual(score, 20.0)
        self.assertTrue(any('rarely covered' in r for r in reasons))

    def test_common_fit_scores_high(self) -> None:
        item = make_item('t1', fit='Oversized')
        score, reasons = self.engine.fit_score(item, PROFILE)
        self.assertGreaterEqual(score, 60.0)
        self.assertTrue(any('preferred silhouette' in r for r in reasons))

    def test_new_fit_scores_low(self) -> None:
        item = make_item('t1', fit='Tapered')
        score, reasons = self.engine.fit_score(item, PROFILE)
        self.assertEqual(score, 40.0)
        self.assertTrue(any('new silhouette' in r for r in reasons))

    def test_all_season_is_safe(self) -> None:
        item = make_item('t1', season='All-season')
        score, _ = self.engine.season_score(item, PROFILE)
        self.assertEqual(score, 70.0)

    def test_wardrobe_season_scores_high(self) -> None:
        item = make_item('t1', season='Winter')
        score, _ = self.engine.season_score(item, PROFILE)
        self.assertGreaterEqual(score, 60.0)

    def test_uncommon_season_scores_low(self) -> None:
        item = make_item('t1', season='Summer')
        score, _ = self.engine.season_score(item, PROFILE)
        self.assertEqual(score, 30.0)


class CategoryBalanceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = PersonalizationEngine()

    def test_overrepresented_category_penalized(self) -> None:
        item = make_item('t1', category='Top')
        score, reasons = self.engine.category_balance_score(item, PROFILE)
        self.assertLess(score, 60.0)
        self.assertTrue(any('overrepresented' in r for r in reasons))

    def test_underrepresented_category_rewarded(self) -> None:
        item = make_item('s1', category='Footwear')
        score, reasons = self.engine.category_balance_score(item, PROFILE)
        self.assertGreater(score, 60.0)
        self.assertTrue(any('underrepresented' in r for r in reasons))

    def test_missing_category_counts_rewards_strongly(self) -> None:
        item = make_item('l1', category='Layer')
        score, _ = self.engine.category_balance_score(item, PROFILE)
        self.assertEqual(score, 100.0)

    def test_balanced_category_mid_range(self) -> None:
        item = make_item('b1', category='Bottom')
        score, _ = self.engine.category_balance_score(item, PROFILE)
        self.assertGreaterEqual(score, 60.0)
        self.assertLess(score, 100.0)

    def test_empty_wardrobe_neutral(self) -> None:
        empty = WardrobeProfile()
        item = make_item('t1', category='Top')
        score, _ = self.engine.category_balance_score(item, empty)
        self.assertEqual(score, 50.0)


class NoveltyScoringTest(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = PersonalizationEngine()

    def test_no_similar_items_scores_full(self) -> None:
        item = make_item('t1', category='Top', primary_color='Black', pattern='Solid', fit='Regular')
        others = [
            make_item('b1', category='Bottom', primary_color='Navy', color_family='Dark',
                      pattern='Stripes', fit='Baggy', formality_level=7, style_tags=['Grunge']),
            make_item('s1', category='Footwear', primary_color='Brown', color_family='Earth',
                      pattern='Abstract', fit='Tapered', formality_level=6, style_tags=['Techwear']),
        ]
        score, reasons = self.engine.novelty_score(item, others)
        self.assertEqual(score, 100.0)
        self.assertTrue(any('Distinct' in r for r in reasons))

    def test_duplicate_item_penalized(self) -> None:
        item = make_item('t1', category='Top', primary_color='Black', color_family='Neutral',
                         pattern='Solid', fit='Regular', style_tags=['Minimalist'], formality_level=3)
        clone = make_item('t2', category='Top', primary_color='Black', color_family='Neutral',
                          pattern='Solid', fit='Regular', style_tags=['Minimalist'], formality_level=3)
        score, reasons = self.engine.novelty_score(item, [clone])
        self.assertEqual(score, 80.0)
        self.assertTrue(any('1 very similar item' in r for r in reasons))

    def test_five_duplicates_cap_at_zero(self) -> None:
        item = make_item('t1', category='Top', primary_color='Black', color_family='Neutral',
                         pattern='Solid', fit='Regular', style_tags=['Minimalist'], formality_level=3)
        clones = [make_item(f'c{i}', category='Top', primary_color='Black', color_family='Neutral',
                            pattern='Solid', fit='Regular', style_tags=['Minimalist'], formality_level=3)
                  for i in range(5)]
        score, _ = self.engine.novelty_score(item, clones)
        self.assertEqual(score, 0.0)

    def test_self_is_ignored(self) -> None:
        item = make_item('t1', category='Top', primary_color='Black', color_family='Neutral',
                         pattern='Solid', fit='Regular', style_tags=['Minimalist'], formality_level=3)
        score, _ = self.engine.novelty_score(item, [item])
        self.assertEqual(score, 100.0)


class WeightedScoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = PersonalizationEngine()

    def test_weights_normalize_to_one(self) -> None:
        weights = normalize_weights(None)
        self.assertAlmostEqual(sum(weights.values()), 1.0)
        for key, value in DEFAULT_WEIGHTS.items():
            self.assertIn(key, weights)

    def test_custom_weights_are_honoured(self) -> None:
        weights = normalize_weights({'style': 1.0, 'color': 1.0})
        self.assertEqual(weights['style'], 0.5)
        self.assertEqual(weights['color'], 0.5)

    def test_negative_weights_clamped(self) -> None:
        weights = normalize_weights({'style': -5.0})
        self.assertGreaterEqual(weights['style'], 0.0)

    def test_weighted_total_within_range(self) -> None:
        item = make_item('t1', category='Footwear', primary_color='Black', color_family='Neutral',
                         fit='Oversized', season='All-season', occasion=['Casual'],
                         style_tags=['Minimalist'])
        result = self.engine.score_item(item, PROFILE, [])
        self.assertGreaterEqual(result.score, 0.0)
        self.assertLessEqual(result.score, 100.0)
        self.assertEqual(set(result.components.keys()), set(DEFAULT_WEIGHTS.keys()))
        self.assertTrue(result.reasons)

    def test_calculate_personalization_score_wrapper(self) -> None:
        item = make_item('t1', category='Footwear', primary_color='Black', color_family='Neutral',
                         style_tags=['Minimalist'])
        result = calculate_personalization_score(item, PROFILE, [], weights={'style': 1.0})
        self.assertEqual(result.components['style'], 100.0)
        self.assertEqual(result.score, 100.0)


if __name__ == '__main__':
    unittest.main()
