import io
import json
import unittest
from unittest import mock

from django.test import TestCase
from PIL import Image
from rest_framework.test import APIClient

from accounts.models import User
from api.models import OutfitBundle, WardrobeItem
from services import gemini_service, product_metadata
from services.occasion_taxonomy import (
    derive_bundle_occasions,
    expand_occasion,
    expand_occasion_list,
    normalize_occasion_list,
    normalize_tag,
    occasion_match_strength,
    parent_of,
)
from services.product_link_scraper import (
    infer_category,
    infer_subcategory,
    scrape_clothing_product,
)

from engine.compatibility_engine import DIVERSITY_PENALTIES


# -- Test fixtures ------------------------------------------------------------

def make_png():
    buf = io.BytesIO()
    Image.new('RGB', (1, 1), color='black').save(buf, format='PNG')
    return buf.getvalue()


def make_jpeg():
    buf = io.BytesIO()
    Image.new('RGB', (1, 1), color='black').save(buf, format='JPEG')
    return buf.getvalue()


def make_evidence(**overrides):
    evidence = {
        'name': 'Black Slim Fit Shirt',
        'description': '',
        'brand': '',
        'structured_color': '',
        'structured_category': '',
        'structured_material': '',
        'structured_attributes': {},
        'variant_data': [],
        'title': '',
        'meta': {},
        'specs_text': '',
        'image_url': 'https://example.com/img.jpg',
        'source_url': 'https://example.com/product/1',
    }
    evidence.update(overrides)
    return evidence


def make_vision(**overrides):
    vision = {
        'garment_type': 'shirt',
        'category': 'Top',
        'subcategory': 'Shirt',
        'primary_color': 'Black',
        'secondary_colors': [],
        'secondary_color': None,
        'color_family': 'Dark',
        'pattern': 'Solid',
        'fit': 'Slim',
        'material': 'Cotton',
        'sleeve': 'Long Sleeve',
        'occasion_type': ['Casual'],
        'season': 'All-season',
        'formality_level': 5,
        'brand': None,
        'style_tags': ['Classic'],
        'mood_tags': ['Smart'],
        'aesthetic_tone': '',
        'confidence': {
            'garment_type': 0.99, 'category': 0.99, 'subcategory': 0.99,
            'primary_color': 0.98, 'pattern': 0.9, 'fit': 0.9,
            'material': 0.75, 'occasion_type': 0.8, 'season': 0.65,
            'formality_level': 0.8,
        },
    }
    vision.update(overrides)
    return vision


SAMPLE_HTML = """<!DOCTYPE html>
<html><head>
<title>Black Slim Fit Shirt | Example Store</title>
<meta property="og:title" content="Black Slim Fit Shirt">
<meta property="og:description" content="Made from 100% cotton with a slim fit and breathable fabric.">
<meta property="product:category" content="Shirts">
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "Product",
  "name": "Black Slim Fit Shirt",
  "description": "Made from 100% cotton with a slim fit and breathable fabric.",
  "brand": {"@type": "Brand", "name": "ACME"},
  "color": "Maroon",
  "material": "100% Cotton",
  "category": "Men's Shirts",
  "image": "https://cdn.example.com/img/black-shirt.jpg",
  "additionalProperty": [
    {"@type": "PropertyValue", "name": "pattern", "value": "Solid"},
    {"@type": "PropertyValue", "name": "fit", "value": "Slim Fit"},
    {"@type": "PropertyValue", "name": "sleeve_length", "value": "Long Sleeve"}
  ],
  "offers": {
    "@type": "Offer",
    "itemOffered": {"@type": "Product", "name": "Black Slim Fit Shirt - M", "color": "Black"}
  }
}
</script>
</head><body></body></html>
"""


# -- Metadata reconciliation tests ---------------------------------------------

class ResolveMetadataTests(unittest.TestCase):

    def test_current_bug_black_slim_fit_shirt_maroon_structured(self):
        """TEST 1 - title Black, JSON-LD Maroon, image Black -> Black / Slim / Shirt."""
        evidence = make_evidence(name='Black Slim Fit Shirt', structured_color='Maroon')
        vision = make_vision(primary_color='Black', fit='Slim', confidence={'primary_color': 0.98, 'fit': 0.9})
        metadata, provenance = product_metadata.resolve_metadata(evidence, vision)
        self.assertEqual(metadata['primary_color'], 'Black')
        self.assertEqual(metadata['fit'], 'Slim')
        self.assertEqual(metadata['subcategory'], 'Shirt')
        self.assertEqual(metadata['category'], 'Top')
        conflicts = provenance['conflicts']
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0]['field'], 'primary_color')
        self.assertEqual(conflicts[0]['resolved'], 'Black')
        self.assertIn('structured', conflicts[0]['values'])

    def test_no_structured_color_vision_black(self):
        """TEST 2 - no JSON-LD color, image black -> Black / Slim."""
        evidence = make_evidence(name='Black Slim Fit Shirt')
        vision = make_vision(primary_color='Black', fit='Slim')
        metadata, provenance = product_metadata.resolve_metadata(evidence, vision)
        self.assertEqual(metadata['primary_color'], 'Black')
        self.assertEqual(metadata['fit'], 'Slim')
        self.assertFalse(provenance['conflicts'])

    def test_material_from_description_linen(self):
        """TEST 3 - '100% Linen' in description -> material Linen."""
        evidence = make_evidence(name='Shirt', description='100% Linen')
        metadata, provenance = product_metadata.resolve_metadata(evidence, None)
        self.assertEqual(metadata['material'], 'Linen')
        self.assertEqual(provenance['sources']['material']['source'], 'product_description')

    def test_formal_dress_shirt_no_blanket_occasion(self):
        """TEST 4 - no automatic Casual + Business + Date Night for a formal dress shirt."""
        evidence = make_evidence(name='Formal White Dress Shirt')
        metadata, _ = product_metadata.resolve_metadata(evidence, None)
        self.assertNotIn('Date Night', metadata['occasion_type'])
        self.assertNotEqual(
            sorted(metadata['occasion_type']),
            sorted(['Casual', 'Business', 'Date Night']),
        )

    def test_hawaiian_beach_shirt_no_business(self):
        """TEST 5 - Hawaiian beach shirt must not get Business."""
        evidence = make_evidence(name='Hawaiian Beach Shirt')
        metadata, _ = product_metadata.resolve_metadata(evidence, None)
        self.assertNotIn('Business', metadata['occasion_type'])

    def test_overshirt_layer_overshirt(self):
        """TEST 6 - Overshirt -> Layer / Overshirt."""
        evidence = make_evidence(name='Black Overshirt')
        metadata, _ = product_metadata.resolve_metadata(evidence, None)
        self.assertEqual(metadata['category'], 'Layer')
        self.assertEqual(metadata['subcategory'], 'Overshirt')

    def test_polo_top_polo(self):
        """TEST 7 - Polo Shirt -> Top / Polo."""
        evidence = make_evidence(name='Polo Shirt')
        metadata, _ = product_metadata.resolve_metadata(evidence, None)
        self.assertEqual(metadata['category'], 'Top')
        self.assertEqual(metadata['subcategory'], 'Polo')

    def test_cotton_from_description_uses_product_evidence(self):
        """TEST 8 - '100% cotton' -> Cotton, sourced from product evidence, not garment default."""
        evidence = make_evidence(name='Shirt', description='100% cotton')
        metadata, provenance = product_metadata.resolve_metadata(evidence, None)
        self.assertEqual(metadata['material'], 'Cotton')
        source = provenance['sources']['material']['source']
        self.assertIn(source, ('product_specs', 'product_description'))

    def test_wool_not_cotton(self):
        """TEST 9 - '100% wool' -> Wool, NOT Cotton."""
        evidence = make_evidence(name='Shirt', description='100% wool')
        metadata, _ = product_metadata.resolve_metadata(evidence, None)
        self.assertEqual(metadata['material'], 'Wool')

    def test_gemini_failure_conservative_fallback(self):
        """TEST 10 - Gemini unavailable: import still possible with reliable scraped data."""
        evidence = make_evidence(
            name='Black Slim Fit Shirt',
            description='Made from 100% cotton with a slim fit and breathable fabric.',
            brand='ACME',
        )
        metadata, provenance = product_metadata.resolve_metadata(evidence, None)
        self.assertEqual(metadata['primary_color'], 'Black')
        self.assertEqual(metadata['fit'], 'Slim')
        self.assertEqual(metadata['material'], 'Cotton')
        self.assertEqual(metadata['brand'], 'ACME')
        self.assertNotIn('Date Night', metadata['occasion_type'])
        self.assertIn('product_text', provenance['sources']['fit']['source'])

    def test_fit_and_material_from_description(self):
        """Fit + material both derivable from description evidence."""
        evidence = make_evidence(
            name='Casual Shirt',
            description='Made from 100% cotton with a slim fit and breathable fabric.',
        )
        metadata, _ = product_metadata.resolve_metadata(evidence, None)
        self.assertEqual(metadata['fit'], 'Slim')
        self.assertEqual(metadata['material'], 'Cotton')

    def test_material_compositions(self):
        evidence = make_evidence(name='Shirt', description='70% Linen / 30% Cotton')
        metadata, _ = product_metadata.resolve_metadata(evidence, None)
        self.assertEqual(metadata['material'], 'Linen/Cotton')

        evidence = make_evidence(name='Shirt', description='98% Cotton / 2% Elastane')
        metadata, _ = product_metadata.resolve_metadata(evidence, None)
        self.assertEqual(metadata['material'], 'Cotton/Elastane')

    def test_material_unknown_is_null_not_fabricated(self):
        """No fabric evidence -> material null instead of inventing Cotton."""
        evidence = make_evidence(name='Cozy Oversized Hoodie')
        metadata, provenance = product_metadata.resolve_metadata(evidence, None)
        self.assertIsNone(metadata['material'])
        self.assertEqual(provenance['sources']['material']['source'], 'unknown')

    def test_season_not_blind_all_season(self):
        evidence = make_evidence(name='Wool Sweater')
        metadata, _ = product_metadata.resolve_metadata(evidence, None)
        self.assertEqual(metadata['season'], 'Winter')

        evidence = make_evidence(name='Breathable Linen Shirt', description='Perfect for hot weather')
        metadata, _ = product_metadata.resolve_metadata(evidence, None)
        self.assertEqual(metadata['season'], 'Summer')

    def test_brand_never_invented_by_vision(self):
        evidence = make_evidence(name='Sneaker', brand='Nike')
        vision = make_vision(brand='Puma', primary_color='White')
        metadata, _ = product_metadata.resolve_metadata(evidence, vision)
        self.assertEqual(metadata['brand'], 'Nike')

        evidence = make_evidence(name='Sneaker', brand='')
        metadata, _ = product_metadata.resolve_metadata(evidence, vision)
        self.assertIsNone(metadata['brand'])

    def test_color_structured_wins_when_no_other_evidence(self):
        evidence = make_evidence(name='Shirt', structured_color='Maroon')
        metadata, _ = product_metadata.resolve_metadata(evidence, None)
        self.assertEqual(metadata['primary_color'], 'Maroon')

    def test_color_title_beats_structured_without_vision(self):
        """Without vision, title evidence beats JSON-LD color (the original bug case)."""
        evidence = make_evidence(name='Black Slim Fit Shirt', structured_color='Maroon')
        metadata, provenance = product_metadata.resolve_metadata(evidence, None)
        self.assertEqual(metadata['primary_color'], 'Black')
        self.assertTrue(provenance['conflicts'])

    def test_structured_category_priority(self):
        evidence = make_evidence(
            name='Men Casual Overshirt',
            structured_category="Men's Sweaters",
        )
        metadata, _ = product_metadata.resolve_metadata(evidence, None)
        self.assertEqual(metadata['category'], 'Layer')
        self.assertEqual(metadata['subcategory'], 'Sweater')

    def test_vision_category_used_when_no_text_evidence(self):
        evidence = make_evidence(name='Wardrobe Essential')
        vision = make_vision(
            garment_type='sneaker', category='Footwear', subcategory='Sneaker',
            primary_color='White', confidence={'category': 0.95, 'subcategory': 0.9, 'primary_color': 0.9},
        )
        metadata, _ = product_metadata.resolve_metadata(evidence, vision)
        self.assertEqual(metadata['category'], 'Footwear')
        self.assertEqual(metadata['subcategory'], 'Sneaker')

    def test_vision_overbroad_occasion_not_adopted_for_plain_shirt(self):
        """Vision suggesting Business/Date Night must not override conservative garment evidence."""
        evidence = make_evidence(name='Black Slim Fit Shirt', structured_color='Maroon')
        vision = make_vision(
            primary_color='Black', fit='Slim',
            occasion_type=['Casual', 'Business', 'Date Night'],
            confidence={'primary_color': 0.95, 'occasion_type': 0.8},
        )
        metadata, provenance = product_metadata.resolve_metadata(evidence, vision)
        self.assertEqual(metadata['primary_color'], 'Black')
        self.assertEqual(metadata['fit'], 'Slim')
        self.assertEqual(metadata['occasion_type'], ['Casual'])
        self.assertEqual(provenance['sources']['occasion_type']['source'], 'garment_type')


# -- Scraper tests --------------------------------------------------------------

class ScraperTests(unittest.TestCase):

    @mock.patch('services.product_link_scraper.fetch_text', return_value=SAMPLE_HTML)
    @mock.patch('services.product_link_scraper.download_product_image',
                return_value=('/media/wardrobe/link_x.jpg', b'fake-image-bytes'))
    def test_scrape_preserves_raw_evidence(self, mock_download, mock_fetch):
        scraped = scrape_clothing_product('https://example.com/product/1')
        evidence = scraped['evidence']

        self.assertEqual(scraped['name'], 'Black Slim Fit Shirt')
        self.assertIn('100% cotton', scraped['description'])
        self.assertEqual(scraped['brand'], 'ACME')
        self.assertEqual(scraped['image_bytes'], b'fake-image-bytes')

        # Raw evidence must not be discarded.
        self.assertEqual(evidence['name'], 'Black Slim Fit Shirt')
        self.assertIn('slim fit', evidence['description'])
        self.assertEqual(evidence['brand'], 'ACME')
        self.assertEqual(evidence['structured_color'], 'Maroon')
        self.assertEqual(evidence['structured_material'], '100% Cotton')
        self.assertEqual(evidence['structured_attributes']['pattern'], 'Solid')
        self.assertEqual(evidence['structured_attributes']['sleeve_length'], 'Long Sleeve')
        self.assertTrue(evidence['variant_data'])
        self.assertIn('cotton', evidence['specs_text'])
        self.assertEqual(evidence['title'], 'Black Slim Fit Shirt | Example Store')
        self.assertEqual(evidence['source_url'], 'https://example.com/product/1')
        mock_download.assert_called_once()

    def test_subcategory_rules(self):
        self.assertEqual(infer_subcategory('Black Overshirt'), 'Overshirt')
        self.assertEqual(infer_category('Black Overshirt'), 'Layer')
        self.assertEqual(infer_subcategory('Polo Shirt'), 'Polo')
        self.assertEqual(infer_category('Polo Shirt'), 'Top')
        self.assertEqual(infer_subcategory('Black Slim Fit Shirt'), 'Shirt')
        self.assertEqual(infer_category('Black Slim Fit Shirt'), 'Top')
        self.assertEqual(infer_subcategory('Running Sneaker'), 'Sneaker')
        self.assertEqual(infer_category('Running Sneaker'), 'Footwear')
        self.assertEqual(infer_subcategory('Formal White Dress Shirt'), 'Shirt')
        self.assertEqual(infer_subcategory('Wool Sweater'), 'Sweater')
        self.assertEqual(infer_category('Wool Sweater'), 'Layer')
        self.assertEqual(infer_subcategory('Short Sleeve Shirt'), 'Shirt')
        self.assertEqual(infer_category('Short Sleeve Shirt'), 'Top')
        self.assertEqual(infer_subcategory('Casual Shorts'), 'Shorts')


# -- Gemini service tests --------------------------------------------------------

class GeminiServiceTests(unittest.TestCase):

    def test_detect_image_mime(self):
        self.assertEqual(gemini_service.detect_image_mime(make_png()), 'image/png')
        self.assertEqual(gemini_service.detect_image_mime(make_jpeg()), 'image/jpeg')

    @mock.patch.object(gemini_service, '_post_generate_content')
    def test_vision_sends_image_and_evidence(self, mock_post):
        mock_post.return_value = {
            'candidates': [{'content': {'parts': [{'text': json.dumps({
                'garment_type': 'shirt', 'category': 'Top', 'subcategory': 'Shirt',
                'primary_color': 'Black', 'secondary_colors': [], 'pattern': 'Solid',
                'fit': 'Slim', 'material': 'Cotton', 'sleeve': 'Long Sleeve',
                'occasion_type': ['Casual'], 'season': 'All-season',
                'formality_level': 5, 'style_tags': ['Classic'], 'mood_tags': ['Smart'],
                'confidence': {'primary_color': 0.98, 'fit': 0.9},
            })}]}}]}
        evidence = make_evidence(description='Made from 100% cotton', structured_color='Maroon')
        result = gemini_service.extract_product_metadata_from_evidence(make_png(), evidence)

        model_name, parts, generation_config = mock_post.call_args.args
        self.assertEqual(model_name, gemini_service._get_vision_model())
        self.assertIn('Black Slim Fit Shirt', parts[0]['text'])
        self.assertIn('Maroon', parts[0]['text'])
        self.assertIn('100% cotton', parts[0]['text'])
        self.assertEqual(parts[1]['inlineData']['mimeType'], 'image/png')
        self.assertEqual(generation_config['responseMimeType'], 'application/json')
        self.assertIn('responseSchema', generation_config)

        self.assertEqual(result['primary_color'], 'Black')
        self.assertEqual(result['fit'], 'Slim')
        self.assertEqual(result['secondary_color'], None)
        self.assertEqual(result['color_family'], 'Dark')

    @mock.patch.object(gemini_service, '_post_generate_content')
    def test_legacy_extract_product_metadata_still_works(self, mock_post):
        mock_post.return_value = {
            'candidates': [{'content': {'parts': [{'text': '{"fit": "Slim", "material": "Cotton"}'}]}}]
        }
        result = gemini_service.extract_product_metadata(make_png(), 'Shirt', 'Black', 'Shirt', 'Top')
        self.assertEqual(result['fit'], 'Slim')
        self.assertEqual(result['material'], 'Cotton')
        model_name, _parts, _config = mock_post.call_args.args
        self.assertEqual(model_name, gemini_service._get_vision_model())

    def test_normalize_vision_result(self):
        raw = {
            'garment_type': 'Shirt', 'category': 'top', 'subcategory': 'casual shirt for men',
            'primary_color': 'black', 'secondary_colors': ['White'], 'pattern': 'stripes',
            'fit': 'Skinny', 'material': 'Cotton', 'sleeve': 'short sleeve',
            'occasion_type': ['casual', 'Invented'], 'season': 'winter', 'formality_level': 7,
            'style_tags': ['classic', 'Nope'], 'mood_tags': ['Chill', 'Smart'],
            'confidence': {'primary_color': 0.9, 'fit': 0.7},
        }
        result = gemini_service.normalize_vision_result(raw)
        self.assertEqual(result['category'], 'Top')
        self.assertEqual(result['pattern'], 'Stripes')
        self.assertIsNone(result['fit'])  # 'Skinny' is not in the Fit enum
        self.assertEqual(result['occasion_type'], ['Casual'])
        self.assertEqual(result['season'], 'Winter')
        self.assertEqual(result['style_tags'], ['Classic'])
        self.assertEqual(result['secondary_color'], 'White')

    def test_parse_json_with_markdown_fences(self):
        parsed = gemini_service._parse_json_text('```json\n{"fit": "Slim"}\n```')
        self.assertEqual(parsed, {'fit': 'Slim'})
        parsed = gemini_service._parse_json_text('Here you go: {"fit": "Slim"} done')
        self.assertEqual(parsed, {'fit': 'Slim'})


# -- Occasion taxonomy tests ----------------------------------------------------

class OccasionTaxonomyTests(unittest.TestCase):

    def test_legacy_values_map_to_parent_child_pairs(self):
        self.assertEqual(normalize_occasion_list(['Business']), ['Formal', 'Business'])
        self.assertEqual(normalize_occasion_list(['Weekend']), ['Casual', 'Weekend'])
        self.assertEqual(normalize_occasion_list(['Party']), ['Party & Nightlife', 'Party'])
        self.assertEqual(normalize_occasion_list(['Gym']), ['Sports & Active', 'Gym'])
        self.assertEqual(normalize_occasion_list(['Date Night']), ['Date & Social', 'Date Night'])
        self.assertEqual(normalize_occasion_list(['Casual']), ['Casual'])
        self.assertEqual(normalize_occasion_list(['Formal']), ['Formal'])

    def test_parent_does_not_imply_children(self):
        # A parent-only tag stays a parent: filtering for Business must NOT
        # match an item tagged only with Formal.
        self.assertEqual(normalize_occasion_list(['Formal']), ['Formal'])
        self.assertEqual(occasion_match_strength(['Formal'], 'Business'), 0.0)

    def test_child_implies_parent(self):
        # A Business item is also Formal-eligible.
        self.assertIn('Formal', normalize_occasion_list(['Business']))
        self.assertEqual(occasion_match_strength(['Formal', 'Business'], 'Formal'), 1.0)
        self.assertEqual(occasion_match_strength(['Formal', 'Business'], 'Business'), 1.0)

    def test_unknown_and_duplicate_tags_dropped(self):
        self.assertEqual(normalize_occasion_list(['casual', 'Invented', 'Casual']), ['Casual'])
        self.assertIsNone(normalize_tag('Invented Occasion'))

    def test_expand_parent_includes_descendants(self):
        expanded = expand_occasion('Formal')
        self.assertIn('Formal', expanded)
        self.assertIn('Business', expanded)
        self.assertIn('Interview', expanded)
        self.assertNotIn('Casual', expanded)

    def test_expand_child_is_strict(self):
        # A child request expands to exactly that child: bundles already carry
        # their parent tag, so a generic parent-only bundle must NOT
        # auto-qualify for a child request (Business-only bundles still match
        # through their own Business tag).
        expanded = expand_occasion('Gym')
        self.assertEqual(expanded, {'Gym'})
        expanded = expand_occasion('Business')
        self.assertEqual(expanded, {'Business'})
        self.assertEqual(occasion_match_strength(['Formal', 'Business'], 'Business'), 1.0)
        self.assertEqual(occasion_match_strength(['Formal'], 'Business'), 0.0)

    def test_bundle_derivation_intersection(self):
        occasions = [
            ['Formal', 'Business', 'Casual'],
            ['Formal', 'Business'],
            ['Formal', 'Business'],
        ]
        self.assertEqual(derive_bundle_occasions(occasions), ['Formal', 'Business'])

    def test_bundle_derivation_majority_fallback(self):
        occasions = [
            ['Casual'],
            ['Formal', 'Business'],
            ['Formal', 'Business'],
        ]
        derived = derive_bundle_occasions(occasions)
        self.assertEqual(sorted(derived), ['Business', 'Formal'])

    def test_bundle_derivation_union_last_resort(self):
        occasions = [['Casual'], ['Gym']]
        derived = derive_bundle_occasions(occasions)
        self.assertEqual(sorted(derived), ['Casual', 'Gym', 'Sports & Active'])

    def test_occasion_match_strength_hierarchy(self):
        # Exact family matches are strong.
        self.assertEqual(occasion_match_strength(['Formal', 'Business'], 'Business'), 1.0)
        self.assertEqual(occasion_match_strength(['Formal', 'Business'], 'Formal'), 1.0)
        self.assertEqual(occasion_match_strength(['Casual', 'Weekend'], 'Casual'), 1.0)
        self.assertEqual(occasion_match_strength(['Casual', 'Weekend'], 'Weekend'), 1.0)
        # Broad bundles (occasions from other families) match more weakly.
        self.assertEqual(
            occasion_match_strength(['Formal', 'Business', 'Casual'], 'Formal'), 0.5
        )
        # A parent does NOT imply its children.
        self.assertEqual(occasion_match_strength(['Formal'], 'Business'), 0.0)
        self.assertEqual(occasion_match_strength(['Casual'], 'Weekend'), 0.0)
        # Unrelated family -> not eligible.
        self.assertEqual(occasion_match_strength(['Casual', 'Weekend'], 'Party & Nightlife'), 0.0)


class HierarchicalOccasionResolutionTests(unittest.TestCase):

    def test_text_business_expands_to_parent_child(self):
        evidence = make_evidence(name='Business Shirt')
        metadata, provenance = product_metadata.resolve_metadata(evidence, None)
        self.assertEqual(metadata['occasion_type'], ['Formal', 'Business'])
        self.assertEqual(provenance['sources']['occasion_type']['source'], 'product_text')

    def test_vision_candidates_are_evidence(self):
        evidence = make_evidence(name='Sneaker')
        vision = make_vision(
            garment_type='sneaker',
            occasion_candidates=[
                {'tag': 'Business', 'confidence': 0.9},
                {'tag': 'Running', 'confidence': 0.7},
            ],
            confidence={'occasion_type': 0.8},
        )
        metadata, provenance = product_metadata.resolve_metadata(evidence, vision)
        self.assertEqual(metadata['occasion_type'], ['Formal', 'Business', 'Sports & Active', 'Running'])
        self.assertEqual(provenance['sources']['occasion_type']['source'], 'vision')

    def test_low_confidence_vision_candidates_dropped(self):
        evidence = make_evidence(name='Sneaker')
        vision = make_vision(
            garment_type='sneaker',
            occasion_candidates=[
                {'tag': 'Business', 'confidence': 0.9},
                {'tag': 'Wedding', 'confidence': 0.1},
            ],
            confidence={'occasion_type': 0.8},
        )
        metadata, _ = product_metadata.resolve_metadata(evidence, vision)
        self.assertEqual(metadata['occasion_type'], ['Formal', 'Business'])
        self.assertNotIn('Wedding', metadata['occasion_type'])

    def test_legacy_flat_vision_occasion_type_still_supported(self):
        evidence = make_evidence(name='Sneaker')
        vision = make_vision(garment_type='sneaker', occasion_type=['Business', 'Casual'])
        metadata, _ = product_metadata.resolve_metadata(evidence, vision)
        self.assertEqual(metadata['occasion_type'], ['Formal', 'Business', 'Casual'])

    def test_garment_joggers_imply_gym(self):
        evidence = make_evidence(name='Joggers')
        metadata, provenance = product_metadata.resolve_metadata(evidence, None)
        self.assertEqual(metadata['occasion_type'], ['Sports & Active', 'Gym', 'Casual'])
        self.assertEqual(provenance['sources']['occasion_type']['source'], 'garment_type')

    def test_business_casual_phrase_not_expanded_to_business(self):
        # "business casual" must yield only Smart Casual/Business Casual,
        # not Formal/Business or plain Casual (no blanket implications).
        evidence = make_evidence(name='Business Casual Chinos')
        metadata, _ = product_metadata.resolve_metadata(evidence, None)
        self.assertEqual(metadata['occasion_type'], ['Smart Casual', 'Business Casual'])

    def test_parent_of(self):
        self.assertEqual(parent_of('Business'), 'Formal')
        self.assertIsNone(parent_of('Formal'))


# -- API-level tests (Django TestCase, sqlite test DB) ---------------------------

class AddProductLinkViewTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(mobile_no='9999999999')
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.url = '/api/wardrobe/add-product-link'

    def test_occasion_taxonomy_endpoint_is_source_of_truth(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.get('/api/occasions/taxonomy')
        self.assertEqual(response.status_code, 200)
        parents = response.data['parents']
        self.assertEqual(len(parents), 11)
        by_name = {p['name']: p['children'] for p in parents}
        self.assertEqual(
            by_name['Formal'],
            ['Business', 'Corporate', 'Work / Office', 'Interview', 'Meeting',
             'Presentation', 'Conference', 'Professional', 'Business Formal',
             'Smart Formal'],
        )
        self.assertIn('Business', by_name['Formal'])
        self.assertIn('Gym', by_name['Sports & Active'])
        self.assertIn('Date Night', by_name['Date & Social'])
        self.assertIn('legacy_mapping', response.data)
        self.assertEqual(response.data['legacy_mapping']['Business'], ['Formal', 'Business'])

    def _canned_scrape(self, evidence=None):
        evidence = evidence or make_evidence()
        return {
            'source_url': evidence['source_url'],
            'name': evidence['name'],
            'description': evidence['description'],
            'brand': evidence['brand'],
            'color': evidence['structured_color'] or 'Black',
            'type': 'Shirt',
            'category': 'Top',
            'image_url': '/media/wardrobe/link_test.jpg',
            'image_bytes': b'fake-image-bytes',
            'evidence': evidence,
        }

    @mock.patch('api.views_upload.scrape_clothing_product')
    @mock.patch.object(
        gemini_service, 'extract_product_metadata_from_evidence',
        side_effect=Exception('Gemini unavailable'),
    )
    def test_gemini_failure_still_imports_product(self, mock_vision, mock_scrape):
        """TEST 10 (API level) - Gemini failure does not fail the import."""
        evidence = make_evidence(
            name='Black Slim Fit Shirt',
            structured_color='Maroon',
            description='100% Cotton fabric.',
            brand='ACME',
        )
        mock_scrape.return_value = self._canned_scrape(evidence)

        response = self.client.post(self.url, {'url': 'https://example.com/p/1'}, format='json')
        self.assertEqual(response.status_code, 201)
        item = WardrobeItem.objects.get(item_id=response.data['product']['item_id'])
        self.assertEqual(item.primary_color, 'Black')
        self.assertEqual(item.fit, 'Slim')
        self.assertEqual(item.material, 'Cotton')
        self.assertEqual(item.brand, 'ACME')
        self.assertTrue(item.fallback_used)
        mock_vision.assert_called_once()

    @mock.patch('api.views_upload.scrape_clothing_product')
    @mock.patch.object(gemini_service, 'extract_product_metadata_from_evidence')
    def test_vision_conflict_resolution_end_to_end(self, mock_vision, mock_scrape):
        """TEST 1 (API level) - image Black beats JSON-LD Maroon; fit Slim preserved."""
        evidence = make_evidence(name='Black Slim Fit Shirt', structured_color='Maroon')
        mock_scrape.return_value = self._canned_scrape(evidence)
        mock_vision.return_value = make_vision(
            primary_color='Black', fit='Slim', subcategory='Shirt',
            confidence={'primary_color': 0.98, 'fit': 0.9, 'category': 0.99, 'subcategory': 0.99},
        )

        response = self.client.post(self.url, {'url': 'https://example.com/p/1'}, format='json')
        self.assertEqual(response.status_code, 201)
        item = WardrobeItem.objects.get(item_id=response.data['product']['item_id'])
        self.assertEqual(item.primary_color, 'Black')
        self.assertEqual(item.fit, 'Slim')
        self.assertEqual(item.subcategory, 'Shirt')
        self.assertFalse(item.fallback_used)
        mock_vision.assert_called_once_with(b'fake-image-bytes', evidence)

    @mock.patch('api.views_upload.scrape_clothing_product')
    @mock.patch.object(gemini_service, 'extract_product_metadata_from_evidence')
    def test_api_contract_preserved(self, mock_vision, mock_scrape):
        evidence = make_evidence(name='Black Slim Fit Shirt')
        mock_scrape.return_value = self._canned_scrape(evidence)
        mock_vision.return_value = make_vision()

        response = self.client.post(self.url, {'url': 'https://example.com/p/1'}, format='json')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['success'], True)
        self.assertIn('message', response.data)
        self.assertIn('product', response.data)
        self.assertIn('source_url', response.data)
        self.assertEqual(response.data['source_url'], evidence['source_url'])
        self.assertEqual(response.data['product']['primary_color'], 'Black')
        self.assertEqual(response.data['product']['fit'], 'Slim')
        self.assertEqual(response.data['product']['category'], 'Top')


class BundleOccasionFilterViewTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(mobile_no='9999999998')
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.base = {
            'user': self.user,
            'pattern': 'Solid',
            'fit': 'Regular',
            'season': 'All-season',
            'formality_level': 5,
            'color_family': 'Neutral',
            'added_at': '2026-08-19T00:00:00Z',
        }
        self.business_top = WardrobeItem.objects.create(
            item_id='bt1', name='Business Top', category='Top',
            subcategory='Shirt', primary_color='White',
            occasion_type=['Formal', 'Business'], **self.base,
        )
        WardrobeItem.objects.create(
            item_id='bb1', name='Business Bottom', category='Bottom',
            subcategory='Trousers', primary_color='Black',
            occasion_type=['Formal', 'Business'], **self.base,
        )
        WardrobeItem.objects.create(
            item_id='bs1', name='Business Shoe', category='Footwear',
            subcategory='Loafers', primary_color='Black',
            occasion_type=['Formal', 'Business'], **self.base,
        )
        WardrobeItem.objects.create(
            item_id='cs1', name='Casual Shoe', category='Footwear',
            subcategory='Sneakers', primary_color='White',
            occasion_type=['Casual'], **self.base,
        )

    def _stored_bundle(self, bundle_id, occasion_tags, item_ids, style_tags=None):
        return OutfitBundle.objects.create(
            bundle_id=bundle_id,
            user=self.user,
            items=item_ids,
            compatibility_score=70.0,
            dominant_color='Black',
            dominant_palette='Neutral',
            occasion_tags=occasion_tags,
            style_tags=style_tags if style_tags is not None else ['Classic'],
            mood_tags=['Elegant'],
            is_saved=True,
            wear_count=0,
            source='user_generated',
            created_at='2026-08-19T00:00:00Z',
        )

    def _bundle_ids(self, response):
        return {b['bundle_id'] for b in response.data}

    def test_bundle_list_without_filter_returns_all_stored(self):
        self._stored_bundle('bundle-formal', ['Formal', 'Business'], ['bt1', 'bb1', 'bs1'])
        self._stored_bundle('bundle-casual', ['Casual'], ['bt1', 'bb1', 'cs1'])
        response = self.client.get('/api/bundles/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('bundle-formal', self._bundle_ids(response))
        self.assertIn('bundle-casual', self._bundle_ids(response))

    def test_bundle_list_occasion_filter_excludes_other_families(self):
        self._stored_bundle('bundle-formal', ['Formal', 'Business'], ['bt1', 'bb1', 'bs1'])
        self._stored_bundle('bundle-casual', ['Casual'], ['bt1', 'bb1', 'cs1'])
        response = self.client.get('/api/bundles/', {'occasion': 'Formal'})
        self.assertEqual(response.status_code, 200)
        ids = self._bundle_ids(response)
        self.assertIn('bundle-formal', ids)
        self.assertNotIn('bundle-casual', ids)

    def test_bundle_list_child_filter_matches_stored_parent_bundle(self):
        self._stored_bundle('bundle-formal', ['Formal', 'Business'], ['bt1', 'bb1', 'bs1'])
        response = self.client.get('/api/bundles/', {'occasion': 'Business'})
        self.assertEqual(response.status_code, 200)
        self.assertIn('bundle-formal', self._bundle_ids(response))

    def test_bundle_list_exposes_occasion_relevance(self):
        self._stored_bundle('bundle-formal', ['Formal', 'Business'], ['bt1', 'bb1', 'bs1'])
        response = self.client.get('/api/bundles/')
        self.assertEqual(response.status_code, 200)
        formal_payload = next(
            b for b in response.data if b['bundle_id'] == 'bundle-formal'
        )
        self.assertEqual(
            formal_payload['occasion_relevance'],
            {'Formal': 1.0, 'Business': 1.0},
        )
        for bundle in response.data:
            self.assertIn('occasion_relevance', bundle)
            self.assertGreaterEqual(
                set(bundle['occasion_relevance']),
                set(normalize_occasion_list(bundle['occasion_tags'])),
            )

    def test_broad_stored_bundle_reports_weaker_relevance(self):
        self._stored_bundle(
            'bundle-broad', ['Formal', 'Business', 'Casual'], ['bt1', 'bb1', 'bs1'],
        )
        response = self.client.get('/api/bundles/')
        broad_payload = next(
            b for b in response.data if b['bundle_id'] == 'bundle-broad'
        )
        self.assertEqual(
            broad_payload['occasion_relevance'],
            {'Formal': 0.5, 'Business': 0.5, 'Casual': 0.5},
        )

    def test_occasion_parent_filter_ranks_formal_first(self):
        self._stored_bundle('bundle-formal', ['Formal', 'Business'], ['bt1', 'bb1', 'bs1'])
        self._stored_bundle('bundle-casual', ['Casual'], ['bt1', 'bb1', 'cs1'])
        response = self.client.get('/api/bundles/', {'occasion': 'Formal'})
        self.assertEqual(response.status_code, 200)
        ids = self._bundle_ids(response)
        self.assertIn('bundle-formal', ids)
        self.assertNotIn('bundle-casual', ids)
        self.assertIn('Formal', response.data[0]['occasion_relevance'])

    def test_occasion_casual_filter_ranks_casual_first(self):
        self._stored_bundle('bundle-formal', ['Formal', 'Business'], ['bt1', 'bb1', 'bs1'])
        self._stored_bundle('bundle-casual', ['Casual'], ['bt1', 'bb1', 'cs1'])
        response = self.client.get('/api/bundles/', {'occasion': 'Casual'})
        self.assertEqual(response.status_code, 200)
        ids = self._bundle_ids(response)
        self.assertIn('bundle-casual', ids)
        self.assertNotIn('bundle-formal', ids)
        self.assertIn('Casual', response.data[0]['occasion_relevance'])

    def test_occasion_child_filter_excludes_generic_parent_only_bundle(self):
        # Case 3: a generic Formal-only bundle must NOT auto-qualify for a
        # Business request, even though Business bundles qualify for Formal.
        self._stored_bundle('bundle-formal', ['Formal', 'Business'], ['bt1', 'bb1', 'bs1'])
        self._stored_bundle('bundle-generic-formal', ['Formal'], ['bt1', 'bb1', 'bs1'])
        response = self.client.get('/api/bundles/', {'occasion': 'Business'})
        self.assertEqual(response.status_code, 200)
        ids = self._bundle_ids(response)
        self.assertIn('bundle-formal', ids)
        self.assertNotIn('bundle-generic-formal', ids)
        self.assertIn('Business', response.data[0]['occasion_relevance'])

    def test_style_filter_uses_existing_style_tags(self):
        # Case 4: style=minimalist filters stored + generated bundles by their
        # existing style_tags, case-insensitively.
        self._stored_bundle(
            'bundle-minimal', ['Formal', 'Business'], ['bt1', 'bb1', 'bs1'],
            style_tags=['Minimalist', 'Classic'],
        )
        self._stored_bundle(
            'bundle-street', ['Casual'], ['bt1', 'bb1', 'cs1'],
            style_tags=['Streetwear'],
        )
        response = self.client.get('/api/bundles/', {'style': 'minimalist'})
        self.assertEqual(response.status_code, 200)
        ids = self._bundle_ids(response)
        self.assertIn('bundle-minimal', ids)
        self.assertNotIn('bundle-street', ids)

        mixed_case = self.client.get('/api/bundles/', {'style': 'MINIMALIST'})
        self.assertIn('bundle-minimal', self._bundle_ids(mixed_case))

    def test_occasion_and_style_filters_combine(self):
        # Case 5: occasion=formal&style=minimalist must satisfy BOTH
        # constraints — neither filter resets the other.
        self._stored_bundle(
            'bundle-minimal', ['Formal', 'Business'], ['bt1', 'bb1', 'bs1'],
            style_tags=['Minimalist'],
        )
        self._stored_bundle(
            'bundle-street-formal', ['Formal', 'Business'], ['bt1', 'bb1', 'bs1'],
            style_tags=['Streetwear'],
        )
        self._stored_bundle(
            'bundle-casual-minimal', ['Casual'], ['bt1', 'bb1', 'cs1'],
            style_tags=['Minimalist'],
        )
        response = self.client.get(
            '/api/bundles/',
            {'occasion': 'Formal', 'style': 'minimalist'},
        )
        self.assertEqual(response.status_code, 200)
        ids = self._bundle_ids(response)
        self.assertIn('bundle-minimal', ids)
        self.assertNotIn('bundle-street-formal', ids)
        self.assertNotIn('bundle-casual-minimal', ids)

    def test_unknown_occasion_returns_validation_error(self):
        # Case 7: unknown occasions are rejected safely — the taxonomy is
        # never extended from user input.
        response = self.client.get('/api/bundles/', {'occasion': 'not-a-real-occasion'})
        self.assertEqual(response.status_code, 400)
        self.assertIn('detail', response.data)

    def test_occasion_all_returns_default_ordering(self):
        # Case 6: occasion=all behaves exactly like no filter.
        self._stored_bundle('bundle-formal', ['Formal', 'Business'], ['bt1', 'bb1', 'bs1'])
        self._stored_bundle('bundle-casual', ['Casual'], ['bt1', 'bb1', 'cs1'])
        filtered = self.client.get('/api/bundles/', {'occasion': 'all'})
        unfiltered = self.client.get('/api/bundles/')
        self.assertEqual(filtered.status_code, 200)
        self.assertEqual(
            [b['bundle_id'] for b in filtered.data],
            [b['bundle_id'] for b in unfiltered.data],
        )


class BundleScoringDebugApiTests(TestCase):
    """Debug/observability contract: generated bundles expose the real
    backend scoring values (compatibility / personalization / diversity /
    final) without the UI computing anything itself."""

    def setUp(self):
        self.user = User.objects.create_user(mobile_no='9999999997')
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        base = {
            'user': self.user,
            'pattern': 'Solid',
            'fit': 'Regular',
            'season': 'All-season',
            'formality_level': 3,
            'color_family': 'Neutral',
            'occasion_type': ['Casual'],
            'added_at': '2026-08-19T00:00:00Z',
        }
        for item_id, category, subcategory, color in (
            ('dbg-top1', 'Top', 'T-Shirt', 'White'),
            ('dbg-top2', 'Top', 'Shirt', 'Black'),
            ('dbg-bot1', 'Bottom', 'Jeans', 'Grey'),
            ('dbg-bot2', 'Bottom', 'Chinos', 'Beige'),
            ('dbg-sho1', 'Footwear', 'Sneakers', 'Black'),
            ('dbg-sho2', 'Footwear', 'Loafers', 'White'),
        ):
            WardrobeItem.objects.create(
                item_id=item_id, name=f'{color} {subcategory}', category=category,
                subcategory=subcategory, primary_color=color, **base,
            )

    def _stored_bundle(self):
        return OutfitBundle.objects.create(
            bundle_id='dbg-stored', user=self.user, items=['dbg-top1', 'dbg-bot1', 'dbg-sho1'],
            compatibility_score=70.0, dominant_color='White', dominant_palette='Neutral',
            occasion_tags=['Casual'], style_tags=['Casual'], mood_tags=[],
            is_saved=True, wear_count=0, source='user_generated',
            created_at='2026-08-19T00:00:00Z',
        )

    SCORING_KEYS = (
        'compatibility_score',
        'personalization_score',
        'ranking_score',
        'diversity_penalty',
        'diversity_breakdown',
    )

    def test_generated_bundles_expose_consistent_scoring_fields(self):
        response = self.client.get('/api/bundles/')
        self.assertEqual(response.status_code, 200)
        generated = [b for b in response.data if b['bundle_id'].startswith('GEN-')]
        self.assertTrue(generated, 'expected generated bundles from the wardrobe')

        for bundle in generated:
            for key in self.SCORING_KEYS:
                self.assertIn(key, bundle)
            self.assertIsInstance(bundle['compatibility_score'], (int, float))
            self.assertGreaterEqual(bundle['personalization_score'], 0)
            self.assertLessEqual(bundle['personalization_score'], 30)
            self.assertGreaterEqual(bundle['diversity_penalty'], 0)
            # Backend math: ranking = compatibility + personalization − diversity.
            self.assertAlmostEqual(
                bundle['ranking_score'],
                round(
                    bundle['compatibility_score']
                    + bundle['personalization_score']
                    - bundle['diversity_penalty'], 2
                ),
                places=2,
            )
            # Diversity penalty == sum of its numeric component breakdown.
            self.assertEqual(
                bundle['diversity_penalty'],
                round(sum(bundle['diversity_breakdown'].values()), 2),
            )

    def test_same_top_bundle_reports_diversity_penalty_in_breakdown(self):
        response = self.client.get('/api/bundles/')
        self.assertEqual(response.status_code, 200)
        repeated_top = [
            b for b in response.data
            if b['diversity_breakdown'].get('same_top', 0) > 0
        ]
        self.assertTrue(repeated_top, 'expected a same-top bundle to be detected')
        for bundle in repeated_top:
            self.assertGreater(bundle['diversity_penalty'], 0)
            self.assertGreaterEqual(
                bundle['diversity_breakdown']['same_top'],
                DIVERSITY_PENALTIES['same_top'],
            )
            # A same-top + same-bottom bundle carries a stronger penalty.
            if bundle['diversity_breakdown'].get('same_bottom', 0) > 0:
                self.assertGreaterEqual(
                    bundle['diversity_penalty'],
                    DIVERSITY_PENALTIES['same_top'] + DIVERSITY_PENALTIES['same_bottom'],
                )

    def test_stored_bundle_is_scored_with_the_same_canonical_formula(self):
        self._stored_bundle()
        response = self.client.get('/api/bundles/')
        self.assertEqual(response.status_code, 200)
        stored = next(b for b in response.data if b['bundle_id'] == 'dbg-stored')
        self.assertEqual(stored['compatibility_score'], 70.0)
        for key in self.SCORING_KEYS:
            self.assertIn(key, stored)
        self.assertIsNotNone(stored['personalization_score'])
        self.assertIsNotNone(stored['ranking_score'])
        self.assertIsNotNone(stored['diversity_penalty'])
        self.assertIsNotNone(stored['diversity_breakdown'])
        # The stored bundle ranks by the exact same formula as generated ones.
        self.assertAlmostEqual(
            stored['ranking_score'],
            round(
                stored['compatibility_score']
                + stored['personalization_score']
                - stored['diversity_penalty'], 2
            ),
            places=2,
        )
        rankings = [b['ranking_score'] for b in response.data]
        self.assertEqual(rankings, sorted(rankings, reverse=True))

    def test_recommend_from_wardrobe_endpoint_exposes_scoring(self):
        response = self.client.post(
            '/api/bundle-generate/recommend-from-wardrobe/',
            {'item_id': 'dbg-top1'},
            format='json',
        )
        self.assertEqual(response.status_code, 200)
        bundles = response.data if isinstance(response.data, list) else []
        self.assertTrue(bundles)
        for bundle in bundles:
            for key in self.SCORING_KEYS:
                self.assertIn(key, bundle)
            self.assertIsNotNone(bundle['personalization_score'])
            self.assertIsNotNone(bundle['ranking_score'])
            self.assertIsNotNone(bundle['diversity_penalty'])
            self.assertIsNotNone(bundle['diversity_breakdown'])