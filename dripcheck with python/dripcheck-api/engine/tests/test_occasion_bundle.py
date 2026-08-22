"""Tests for hierarchy-aware bundle generation and occasion derivation."""

from __future__ import annotations

import os
import unittest

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dripcheck_django.settings')
import django  # noqa: E402

django.setup()

from engine.compatibility_engine import generate_bundles  # noqa: E402
from engine.tests.helpers import make_item  # noqa: E402
from services.occasion_taxonomy import occasion_relevance  # noqa: E402


def _wardrobe():
    """Every combination shares Formal+Business except shoe-2 (Casual-only)."""
    return [
        make_item('top-1', category='Top', occasion=['Formal', 'Business', 'Casual']),
        make_item('bottom-1', category='Bottom', occasion=['Formal', 'Business']),
        make_item('shoe-1', category='Footwear', occasion=['Formal', 'Business']),
        make_item('shoe-2', category='Footwear', occasion=['Casual']),
    ]


def _wardrobe_shared():
    """Every item (and therefore every combination) shares Formal+Business."""
    return [
        make_item('top-1', category='Top', occasion=['Formal', 'Business', 'Casual']),
        make_item('bottom-1', category='Bottom', occasion=['Formal', 'Business']),
        make_item('shoe-1', category='Footwear', occasion=['Formal', 'Business']),
        make_item('shoe-2', category='Footwear', occasion=['Formal', 'Business', 'Casual']),
    ]


class OccasionBundleGenerationTests(unittest.TestCase):

    def test_derived_occasions_use_intersection_not_union(self):
        bundles = generate_bundles('user-1', _wardrobe_shared())
        self.assertTrue(bundles)
        for bundle in bundles:
            self.assertEqual(bundle.occasion_tags, ['Formal', 'Business'])
            self.assertNotIn('Casual', bundle.occasion_tags)

    def test_parent_filter_expands_to_descendants(self):
        bundles = generate_bundles('user-1', _wardrobe(), occasion_filter='Formal')
        self.assertTrue(bundles)
        for bundle in bundles:
            item_ids = {str(iid) for iid in bundle.items}
            self.assertIn('top-1', item_ids)
            self.assertIn('bottom-1', item_ids)
            # The Casual-only shoe must not enter a Formal-filtered pool.
            self.assertNotIn('shoe-2', item_ids)
            self.assertEqual(bundle.occasion_tags, ['Formal', 'Business'])

    def test_child_filter_keeps_only_child_matches(self):
        bundles = generate_bundles('user-1', _wardrobe(), occasion_filter='Business')
        self.assertTrue(bundles)
        for bundle in bundles:
            self.assertNotIn('shoe-2', {str(iid) for iid in bundle.items})

    def test_child_filter_excludes_generic_parent_only_items(self):
        # top-1 is generic Formal (parent only): it must NOT auto-qualify for
        # a Business request, even though Formal bundles are Business-adjacent.
        wardrobe = [
            make_item('top-1', category='Top', occasion=['Formal']),
            make_item('top-2', category='Top', occasion=['Formal', 'Business']),
            make_item('bottom-1', category='Bottom', occasion=['Formal', 'Business']),
            make_item('shoe-1', category='Footwear', occasion=['Formal', 'Business']),
        ]
        bundles = generate_bundles('user-1', wardrobe, occasion_filter='Business')
        self.assertTrue(bundles)
        for bundle in bundles:
            ids = {str(iid) for iid in bundle.items}
            self.assertIn('top-2', ids)
            self.assertNotIn('top-1', ids)
            self.assertEqual(bundle.occasion_tags, ['Business'])

    def test_unrelated_occasion_filter_produces_no_bundles(self):
        bundles = generate_bundles('user-1', _wardrobe(), occasion_filter='Wedding')
        self.assertEqual(bundles, [])


class OccasionRelevanceTests(unittest.TestCase):

    def test_focused_bundle_maps_full_relevance(self):
        relevance = occasion_relevance(['Formal', 'Business'])
        self.assertEqual(relevance, {'Formal': 1.0, 'Business': 1.0})

    def test_broad_bundle_maps_weaker_relevance(self):
        relevance = occasion_relevance(['Formal', 'Business', 'Casual'])
        self.assertEqual(relevance, {'Formal': 0.5, 'Business': 0.5, 'Casual': 0.5})

    def test_unknown_tags_are_dropped(self):
        self.assertEqual(occasion_relevance(['Formal', 'NotARealTag']), {'Formal': 1.0})


if __name__ == '__main__':
    unittest.main()