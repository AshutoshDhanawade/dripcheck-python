"""Tests for the diversity / similarity re-ranking layer."""

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
    re_rank_bundles_for_diversity,
    similarity_penalty_between,
)
from engine.tests.helpers import make_item  # noqa: E402


def make_scored(bundle_id, item_ids, final_score, style_tags=None, item_lookup=None):
    return SimpleNamespace(
        bundle=SimpleNamespace(
            bundle_id=bundle_id,
            items=item_ids,
            style_tags=style_tags or [],
            dominant_palette='Neutral',
            dominant_color='Black',
            occasion_tags=['Casual'],
        ),
        final_score=final_score,
    )


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


class ReRankTest(unittest.TestCase):
    def _make_wardrobe(self):
        return [
            make_item('t1', category='Top', subcategory='T-Shirt', style_tags=['Streetwear']),
            make_item('t2', category='Top', subcategory='Shirt', style_tags=['Formal']),
            make_item('t3', category='Top', subcategory='Hoodie', style_tags=['Casual']),
            make_item('b1', category='Bottom', subcategory='Jeans'),
            make_item('b2', category='Bottom', subcategory='Chinos'),
            make_item('b3', category='Bottom', subcategory='Cargo Pants'),
            make_item('s1', category='Footwear', subcategory='Sneakers'),
            make_item('s2', category='Footwear', subcategory='Boots'),
            make_item('s3', category='Footwear', subcategory='Loafers'),
        ]

    def test_first_selected_is_highest_score(self) -> None:
        bundles = [
            make_scored('A', ['t1', 'b1', 's1'], 100),
            make_scored('B', ['t2', 'b2', 's2'], 90),
        ]
        ordered = re_rank_bundles_for_diversity(bundles, item_lookup=build_lookup(self._make_wardrobe()))
        self.assertEqual(ordered[0].bundle.bundle_id, 'A')

    def test_similar_bundle_demoted(self) -> None:
        lookup = build_lookup(self._make_wardrobe())
        bundles = [
            make_scored('A', ['t1', 'b1', 's1'], 100),
            make_scored('B', ['t1', 'b1', 's2'], 98),  # same top+bottom
            make_scored('C', ['t3', 'b3', 's3'], 93),  # fully different
            make_scored('D', ['t2', 'b2', 's1'], 95),  # different top+bottom, same shoe
        ]
        ordered = re_rank_bundles_for_diversity(bundles, item_lookup=lookup)
        ids = [o.bundle.bundle_id for o in ordered]
        self.assertEqual(ids[0], 'A')
        self.assertNotEqual(ids[1], 'B')  # 98 does not beat the similar-penalized spot

    def test_penalized_bundle_can_still_appear_when_enough_requested(self) -> None:
        lookup = build_lookup(self._make_wardrobe())
        bundles = [
            make_scored('A', ['t1', 'b1', 's1'], 100),
            make_scored('B', ['t1', 'b1', 's2'], 98),
        ]
        # Requesting both bundles returns both (nothing deleted permanently).
        ordered = re_rank_bundles_for_diversity(bundles, top_n=2, item_lookup=lookup)
        self.assertEqual([o.bundle.bundle_id for o in ordered], ['A', 'B'])

    def test_top_n_is_configurable(self) -> None:
        lookup = build_lookup(self._make_wardrobe())
        bundles = [
            make_scored('A', ['t1', 'b1', 's1'], 100),
            make_scored('B', ['t2', 'b2', 's2'], 90),
            make_scored('C', ['t3', 'b3', 's3'], 80),
        ]
        ordered = re_rank_bundles_for_diversity(bundles, top_n=2, item_lookup=lookup)
        self.assertEqual(len(ordered), 2)

    def test_metadata_attached_for_debugging(self) -> None:
        lookup = build_lookup(self._make_wardrobe())
        bundles = [
            make_scored('A', ['t1', 'b1', 's1'], 100),
            make_scored('B', ['t1', 'b1', 's2'], 98),
        ]
        ordered = re_rank_bundles_for_diversity(bundles, item_lookup=lookup)
        first = ordered[0]
        self.assertEqual(first.diversity_penalty, 0)
        self.assertEqual(first.adjusted_score, 100)
        second = ordered[1]
        self.assertGreater(second.diversity_penalty, 0)
        self.assertEqual(second.adjusted_score, round(second.final_score - second.diversity_penalty, 2))
        self.assertTrue(second.similarity_breakdown['same_top'])
        self.assertTrue(second.similarity_breakdown['same_bottom'])
        self.assertEqual(second.similar_to, 'A')

    def test_original_final_score_is_preserved(self) -> None:
        lookup = build_lookup(self._make_wardrobe())
        bundles = [
            make_scored('A', ['t1', 'b1', 's1'], 100),
            make_scored('B', ['t1', 'b1', 's2'], 98),
        ]
        ordered = re_rank_bundles_for_diversity(bundles, item_lookup=lookup)
        self.assertEqual(ordered[0].final_score, 100)
        self.assertEqual(ordered[1].final_score, 98)

    def test_insufficient_candidate_diversity_returns_all(self) -> None:
        lookup = build_lookup(self._make_wardrobe())
        bundles = [
            make_scored('A', ['t1', 'b1', 's1'], 100),
            make_scored('B', ['t1', 'b1', 's2'], 98),
            make_scored('C', ['t1', 'b1', 's3'], 97),
        ]
        ordered = re_rank_bundles_for_diversity(bundles, item_lookup=lookup)
        ids = [o.bundle.bundle_id for o in ordered]
        self.assertEqual(set(ids), {'A', 'B', 'C'})
        self.assertEqual(len(ordered), 3)

    def test_slightly_lower_unique_outfit_can_outrank_similar_high_score(self) -> None:
        lookup = build_lookup(self._make_wardrobe())
        bundles = [
            make_scored('A', ['t1', 'b1', 's1'], 100),
            make_scored('B', ['t1', 'b1', 's2'], 98),   # same top+bottom as A
            make_scored('D', ['t2', 'b2', 's1'], 95),   # different top+bottom, same shoe only
        ]
        ordered = re_rank_bundles_for_diversity(bundles, item_lookup=lookup)
        ids = [o.bundle.bundle_id for o in ordered]
        self.assertEqual(ids[0], 'A')
        # D (only same-shoe) beats B (same top+bottom) despite lower final score.
        self.assertEqual(ids[1], 'D')
        self.assertEqual(ids[2], 'B')

    def test_multiple_selected_bundles_evaluated(self) -> None:
        lookup = build_lookup(self._make_wardrobe())
        bundles = [
            make_scored('A', ['t1', 'b1', 's1'], 100),
            make_scored('B', ['t2', 'b2', 's2'], 95),
            make_scored('C', ['t1', 'b1', 's3'], 97),  # similar to A
            make_scored('D', ['t3', 'b3', 's1'], 94),
        ]
        ordered = re_rank_bundles_for_diversity(bundles, item_lookup=lookup)
        ids = [o.bundle.bundle_id for o in ordered]
        # C is similar to the already-selected A, so it should be pushed back.
        self.assertNotEqual(ids[0], 'C')
        self.assertIn('C', ids)


if __name__ == '__main__':
    unittest.main()