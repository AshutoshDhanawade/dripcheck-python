"""Tests for the diversity / similarity penalty primitives."""

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
    similarity_penalty_between,
)
from engine.tests.helpers import make_item  # noqa: E402


def build_lookup(items):
    return {str(getattr(item, 'item_id', '')): item for item in items}


def make_item_exact(item_id, category, subcategory='', primary_color='X', fit='X'):
    return make_item(
        item_id,
        category=category,
        subcategory=subcategory,
        primary_color=primary_color,
        color_family='Neutral',
        fit=fit,
        style_tags=[],
        occasion=[],
    )


def _expected_penalty(breakdown):
    return sum(DIVERSITY_PENALTIES[k] for k, matched in breakdown.items() if matched)


class SimilarityPenaltyTest(unittest.TestCase):
    def test_same_top_and_bottom_is_strongest(self) -> None:
        items = [
            make_item_exact('t1', 'Top', subcategory='T-Shirt', primary_color='Blue', fit='Slim'),
            make_item_exact('b1', 'Bottom', subcategory='Jeans', primary_color='Green', fit='Relaxed'),
            make_item_exact('s1', 'Footwear', subcategory='Sneakers', primary_color='Yellow', fit='Regular'),
            make_item_exact('s2', 'Footwear', subcategory='Running Shoes', primary_color='Purple', fit='Oversized'),
        ]
        lookup = build_lookup(items)
        pf = lambda ids: bundle_diversity_profile(
            SimpleNamespace(items=ids), lookup,
        )
        a = pf(['t1', 'b1', 's1'])
        b = pf(['t1', 'b1', 's2'])
        c = pf(['t1', 'b1', 's1'])
        penalty_b, breakdown_b = similarity_penalty_between(a, b)
        self.assertTrue(breakdown_b['same_top'])
        self.assertTrue(breakdown_b['same_bottom'])
        self.assertFalse(breakdown_b['same_footwear'])
        self.assertEqual(penalty_b, _expected_penalty(breakdown_b))
        self.assertEqual(
            penalty_b,
            DIVERSITY_PENALTIES['same_top']
            + DIVERSITY_PENALTIES['same_bottom']
            + DIVERSITY_PENALTIES['same_color']
            + DIVERSITY_PENALTIES['same_fit'],
        )
        # Identical bundles add the footwear match on top.
        penalty_c, _ = similarity_penalty_between(a, c)
        self.assertGreater(penalty_c, penalty_b)
        self.assertEqual(
            penalty_c,
            penalty_b + DIVERSITY_PENALTIES['same_footwear'],
        )

    def test_same_shoe_alone_is_smaller_than_same_top(self) -> None:
        items = [
            make_item_exact('t1', 'Top', primary_color='Blue', fit='Slim'),
            make_item_exact('t2', 'Top', primary_color='Green', fit='Relaxed'),
            make_item_exact('b1', 'Bottom', primary_color='Yellow', fit='Regular'),
            make_item_exact('b2', 'Bottom', primary_color='Purple', fit='Oversized'),
            make_item_exact('s1', 'Footwear', primary_color='Red', fit='Baggy'),
        ]
        lookup = build_lookup(items)
        pf = lambda ids: bundle_diversity_profile(SimpleNamespace(items=ids), lookup)
        top_pen, top_br = similarity_penalty_between(
            pf(['t1', 'b1', 's1']), pf(['t1', 'b2', 's1']),
        )
        shoe_pen, shoe_br = similarity_penalty_between(
            pf(['t1', 'b1', 's1']), pf(['t2', 'b2', 's1']),
        )
        self.assertGreater(top_pen, shoe_pen)
        self.assertEqual(top_pen, _expected_penalty(top_br))
        self.assertEqual(shoe_pen, _expected_penalty(shoe_br))
        self.assertTrue(top_br['same_top'])
        self.assertTrue(shoe_br['same_footwear'])
        self.assertFalse(shoe_br['same_top'])
        self.assertFalse(shoe_br['same_bottom'])

    def test_different_outfits_have_no_penalty(self) -> None:
        items = [
            make_item_exact('t1', 'Top', primary_color='Blue', fit='Slim'), make_item_exact('t2', 'Top', primary_color='Green', fit='Relaxed'),
            make_item_exact('b1', 'Bottom', primary_color='Yellow', fit='Regular'), make_item_exact('b2', 'Bottom', primary_color='Purple', fit='Oversized'),
            make_item_exact('s1', 'Footwear', primary_color='Red', fit='Baggy'), make_item_exact('s2', 'Footwear', primary_color='White', fit='Tapered'),
        ]
        lookup = build_lookup(items)
        pf = lambda ids: bundle_diversity_profile(SimpleNamespace(items=ids), lookup)
        penalty, _ = similarity_penalty_between(
            pf(['t1', 'b1', 's1']), pf(['t2', 'b2', 's2']),
        )
        self.assertEqual(penalty, 0)

    def test_color_style_fit_occasion_contribute(self) -> None:
        items = [
            make_item('t1', category='Top', primary_color='Black', style_tags=['Streetwear'],
                      fit='Oversized', occasion=['Casual']),
            make_item('t2', category='Top', primary_color='Black', style_tags=['Streetwear'],
                      fit='Oversized', occasion=['Casual']),
            make_item('s1', category='Footwear', primary_color='White'),
        ]
        lookup = build_lookup(items)
        pf = lambda ids: bundle_diversity_profile(SimpleNamespace(items=ids), lookup)
        a = pf(['t1', 's1'])
        b = pf(['t2', 's1'])
        penalty, _ = similarity_penalty_between(a, b)
        self.assertEqual(
            penalty,
            DIVERSITY_PENALTIES['same_footwear']
            + DIVERSITY_PENALTIES['same_color']
            + DIVERSITY_PENALTIES['same_style']
            + DIVERSITY_PENALTIES['same_fit']
            + DIVERSITY_PENALTIES['same_occasion'],
        )

    def test_custom_penalties_override(self) -> None:
        items = [
            make_item_exact('t1', 'Top', primary_color='Blue', fit='Slim'),
            make_item_exact('t2', 'Top', primary_color='Green', fit='Relaxed'),
            make_item_exact('b1', 'Bottom', primary_color='Yellow', fit='Regular'),
            make_item_exact('b2', 'Bottom', primary_color='Purple', fit='Oversized'),
            make_item_exact('s1', 'Footwear', primary_color='Red', fit='Baggy'),
        ]
        lookup = build_lookup(items)
        pf = lambda ids: bundle_diversity_profile(SimpleNamespace(items=ids), lookup)
        penalty, breakdown = similarity_penalty_between(
            pf(['t1', 'b1', 's1']), pf(['t1', 'b2', 's1']),
            penalties={'same_top': 50, 'same_footwear': 0},
        )
        self.assertEqual(breakdown['same_top'], True)
        # same_top(50) + shared colors/fits(10) + overridden same_footwear(0).
        self.assertEqual(penalty, 60)


if __name__ == '__main__':
    unittest.main()