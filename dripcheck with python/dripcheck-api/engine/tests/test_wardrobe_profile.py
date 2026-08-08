"""Tests for the WardrobeProfileBuilder (Step 1)."""

from __future__ import annotations

import os
import unittest

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dripcheck_django.settings')
import django  # noqa: E402

django.setup()

from engine.tests.helpers import make_item  # noqa: E402
from engine.wardrobe_profile import WardrobeProfileBuilder  # noqa: E402

DEFAULT_PROFILE = {
    'favorite_colors': ['Black', 'Grey'],
    'avoided_colors': ['Red'],
    'style_vibes': ['Minimalist', 'Streetwear'],
    'fit_preferences': ['Oversized'],
    'pattern_preferences': ['Solid'],
    'material_sensitivity': ['Wool'],
    'occasion_frequency': {'Casual': 5, 'Weekend': 3},
}


class WardrobeProfileBuilderTest(unittest.TestCase):
    def setUp(self) -> None:
        self.builder = WardrobeProfileBuilder()

    def test_empty_wardrobe_yields_empty_profile(self) -> None:
        profile = self.builder.build([])
        self.assertEqual(profile.total_items, 0)
        self.assertEqual(profile.category_counts, {})
        self.assertEqual(profile.dominant_colors, [])
        self.assertEqual(profile.favorite_brands, [])

    def test_distributions_are_aggregated(self) -> None:
        items = [
            make_item('t1', category='Top', primary_color='Black', color_family='Neutral',
                      fit='Oversized', season='Winter', formality_level=3, pattern='Solid',
                      occasion=['Casual', 'Weekend'], style_tags=['Minimalist'], brand='Zara'),
            make_item('t2', category='Top', primary_color='Black', color_family='Neutral',
                      fit='Regular', season='All-season', formality_level=5, pattern='Stripes',
                      occasion=['Casual'], style_tags=['Streetwear'], brand='Zara'),
            make_item('b1', category='Bottom', primary_color='Grey', color_family='Neutral',
                      fit='Slim', season='All-season', formality_level=4, pattern='Solid',
                      occasion=['Casual', 'Weekend'], style_tags=['Minimalist'], brand='H&M'),
        ]
        profile = self.builder.build(items, DEFAULT_PROFILE)

        self.assertEqual(profile.total_items, 3)
        self.assertEqual(profile.category_counts, {'Top': 2, 'Bottom': 1})
        self.assertEqual(profile.fit_distribution, {'Oversized': 1, 'Regular': 1, 'Slim': 1})
        self.assertEqual(profile.season_distribution, {'Winter': 1, 'All-season': 2})
        self.assertEqual(profile.formality_distribution, {3: 1, 5: 1, 4: 1})
        self.assertEqual(profile.pattern_distribution, {'Solid': 2, 'Stripes': 1})
        self.assertEqual(profile.occasion_distribution, {'casual': 3, 'weekend': 2})
        self.assertEqual(profile.style_distribution, {'minimalist': 2, 'streetwear': 1})

    def test_dominant_colors_and_families(self) -> None:
        items = [
            make_item('t1', category='Top', primary_color='Black', color_family='Neutral'),
            make_item('t2', category='Top', primary_color='Black', color_family='Neutral'),
            make_item('b1', category='Bottom', primary_color='Navy', color_family='Dark'),
        ]
        profile = self.builder.build(items)

        self.assertEqual(profile.dominant_colors, ['Black'])
        self.assertIn('Neutral', profile.dominant_color_families)

    def test_favorite_brands_require_repeat_usage(self) -> None:
        items = [
            make_item('t1', brand='Zara'),
            make_item('t2', brand='Zara'),
            make_item('b1', brand='H&M'),
        ]
        profile = self.builder.build(items)
        self.assertEqual(profile.favorite_brands, ['Zara'])

    def test_onboarding_preferences_and_avoided_colors(self) -> None:
        profile = self.builder.build([], DEFAULT_PROFILE)
        self.assertEqual(profile.avoided_colors, ['red'])
        self.assertEqual(profile.onboarding_preferences['style_vibes'], ['Minimalist', 'Streetwear'])
        self.assertEqual(profile.onboarding_preferences['favorite_colors'], ['Black', 'Grey'])

    def test_accepts_orm_style_object(self) -> None:
        class FakeUserProfile:
            favorite_colors = ['Black']
            avoided_colors = ['Red']
            style_vibes = ['Minimalist']

        profile = self.builder.build([], FakeUserProfile())
        self.assertEqual(profile.avoided_colors, ['red'])
        self.assertEqual(profile.onboarding_preferences['favorite_colors'], ['Black'])

    def test_fraction_helpers(self) -> None:
        items = [
            make_item('t1', category='Top'),
            make_item('b1', category='Bottom'),
        ]
        profile = self.builder.build(items)
        self.assertAlmostEqual(profile.category_fraction('Top'), 0.5)
        self.assertEqual(profile.category_fraction('Footwear'), 0.0)


if __name__ == '__main__':
    unittest.main()
