"""
API Health & Integration Audit (focused tests).

Covers every endpoint in the inventory: auth enforcement, validation,
response structure, taxonomy hierarchy, Home Page filtering, external-service
failure handling, cross-user authorization and database edge cases.

Tests asserting CORRECT (spec) behavior for suspected defects are marked with
``# AUDIT EXPECTED`` — a failure in those tests documents the defect for the
QA report. Nothing here modifies application code.
"""

import io
import os
import shutil
import tempfile
from unittest import mock
from datetime import datetime

from django.test import TestCase, override_settings
from PIL import Image
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.models import User, OTPRecord, OnboardingQuestion
from api.models import OutfitBundle, WardrobeItem, WearLog


def make_user(mobile_no='+919999999900'):
    return User.objects.create(mobile_no=mobile_no, is_active=True)


AUDIT_MEDIA_ROOT = tempfile.mkdtemp(prefix='audit-media-')


def token_for(user):
    return str(RefreshToken.for_user(user).access_token)


def tiny_image_bytes():
    buf = io.BytesIO()
    Image.new('RGB', (64, 64), (30, 30, 30)).save(buf, format='PNG')
    return buf.getvalue()


def item_kwargs(item_id, **overrides):
    kwargs = {
        'item_id': item_id,
        'name': 'White Shirt',
        'category': 'Top',
        'subcategory': 'Shirt',
        'primary_color': 'White',
        'color_family': 'Neutral',
        'pattern': 'Solid',
        'fit': 'Regular',
        'occasion_type': ['Formal', 'Business'],
        'season': 'All-season',
        'formality_level': 5,
        'style_tags': ['Minimalist'],
        'mood_tags': [],
        'added_at': '2026-08-19T00:00:00Z',
        'wear_count': 0,
    }
    kwargs.update(overrides)
    return kwargs


class AuthEnforcementTests(TestCase):
    """Section 13: every protected endpoint must 401 without a valid token."""

    PROTECTED_CALLS = [
        ('get', '/api/occasions/taxonomy'),
        ('get', '/api/wardrobe/'),
        ('post', '/api/wardrobe/upload-product'),
        ('post', '/api/wardrobe/add-product-link'),
        ('post', '/api/wardrobe/approve-product'),
        ('post', '/api/wardrobe/generate-avatar'),
        ('put', '/api/wardrobe/does-not-exist'),
        ('delete', '/api/wardrobe/does-not-exist'),
        ('get', '/api/users/'),
        ('get', '/api/analytics/'),
        ('get', '/api/wearlog/'),
        ('post', '/api/wearlog/'),
        ('get', '/api/bundles/'),
        ('post', '/api/bundles/save'),
        ('get', '/api/marketplace'),
        ('get', '/api/wishlist/'),
        ('post', '/api/wishlist/'),
        ('get', '/api/bundle-generate/homepage/'),
        ('get', '/api/bundle-generate/homepage/best-selling/'),
        ('post', '/api/bundle-generate/recommend/'),
        ('post', '/api/bundle-generate/recommend-from-wardrobe/'),
        ('get', '/api/ai-generation/topwear-suggestion/'),
        ('get', '/api/ai-generation/bottomwear-suggestion/'),
        ('get', '/api/ai-generation/footwear-suggestion/'),
        ('get', '/auth/onboarding/questions/'),
        ('get', '/auth/onboarding/preferences/'),
    ]

    def test_all_protected_endpoints_require_auth(self):
        client = APIClient()
        for method, url in self.PROTECTED_CALLS:
            response = getattr(client, method)(url)
            self.assertEqual(
                response.status_code, 401,
                f'{method.upper()} {url} should be 401 without a token, got {response.status_code}',
            )

    def test_invalid_token_is_rejected(self):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION='Bearer not-a-real-token')
        for url in ('/api/bundles/', '/api/wardrobe/', '/api/occasions/taxonomy'):
            response = client.get(url)
            self.assertEqual(response.status_code, 401, url)

    def test_logs_endpoint_is_public(self):
        response = APIClient().post('/api/logs', {'level': 'info', 'message': 'audit'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['status'], 'logged')

    def test_public_auth_endpoints_do_not_require_auth(self):
        client = APIClient()
        self.assertEqual(client.post('/auth/signup/').status_code, 400)
        self.assertEqual(client.post('/auth/login/').status_code, 400)
        self.assertEqual(client.post('/auth/verify-otp/').status_code, 400)


class WardrobeCrudTests(TestCase):
    """Sections 4, 10, 15: wardrobe list/create/detail, ownership + 404s."""

    def setUp(self):
        self.user = make_user()
        self.other = make_user('+919999999901')
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token_for(self.user)}')

    def _create_item(self, **kw):
        return WardrobeItem.objects.create(
            user=self.user, **item_kwargs('itm-1', **kw)
        )

    def test_post_valid_item_returns_201_with_full_fields(self):
        response = self.client.post(
            '/api/wardrobe/', item_kwargs('new-1'), format='json'
        )
        self.assertEqual(response.status_code, 201)
        for field in ('item_id', 'name', 'category', 'subcategory', 'primary_color',
                      'color_family', 'pattern', 'fit', 'occasion_type', 'season',
                      'formality_level', 'style_tags', 'wear_count', 'added_at'):
            self.assertIn(field, response.data, field)
        self.assertEqual(response.data['occasion_type'], ['Formal', 'Business'])

    def test_post_invalid_category_returns_400(self):
        data = item_kwargs('new-2', category='Shoes')
        response = self.client.post('/api/wardrobe/', data, format='json')
        self.assertEqual(response.status_code, 400)

    def test_get_lists_only_own_items(self):
        self._create_item()
        WardrobeItem.objects.create(user=self.other, **item_kwargs('other-1'))
        response = self.client.get('/api/wardrobe/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual([i['item_id'] for i in response.data], ['itm-1'])

    def test_put_updates_own_item(self):
        self._create_item()
        response = self.client.put(
            '/api/wardrobe/itm-1', {'name': 'Renamed'}, format='json'
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['name'], 'Renamed')

    def test_put_unknown_item_returns_404(self):
        response = self.client.put(
            '/api/wardrobe/missing', {'name': 'x'}, format='json'
        )
        self.assertEqual(response.status_code, 404)

    def test_put_other_users_item_returns_404(self):
        WardrobeItem.objects.create(user=self.other, **item_kwargs('other-1'))
        response = self.client.put(
            '/api/wardrobe/other-1', {'name': 'x'}, format='json'
        )
        self.assertEqual(response.status_code, 404)

    def test_delete_own_item_returns_204(self):
        self._create_item()
        response = self.client.delete('/api/wardrobe/itm-1')
        self.assertEqual(response.status_code, 204)

    def test_delete_unknown_item_returns_404(self):
        response = self.client.delete('/api/wardrobe/missing')
        self.assertEqual(response.status_code, 404)

    def test_delete_other_users_item_returns_404(self):
        WardrobeItem.objects.create(user=self.other, **item_kwargs('other-1'))
        response = self.client.delete('/api/wardrobe/other-1')
        self.assertEqual(response.status_code, 404)

    def test_deleted_item_marks_bundle_missing(self):
        self._create_item()
        OutfitBundle.objects.create(
            bundle_id='b-1', user=self.user, items=['itm-1'],
            compatibility_score=70.0, dominant_color='Black',
            dominant_palette='Neutral', occasion_tags=['Formal', 'Business'],
            style_tags=[], mood_tags=[], source='user_generated',
            created_at='2026-08-19T00:00:00Z',
        )
        self.client.delete('/api/wardrobe/itm-1')
        bundle = OutfitBundle.objects.get(bundle_id='b-1')
        self.assertTrue(bundle.has_missing_item)


class AnalyticsEdgeTests(TestCase):
    """Sections 14, 15: empty wardrobes, null metadata, no bundles."""

    def setUp(self):
        self.user = make_user()
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token_for(self.user)}')

    def test_empty_wardrobe_returns_zeroed_stats(self):
        response = self.client.get('/api/analytics/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['total_items'], 0)
        self.assertEqual(response.data['utilization_percentage'], 0)
        self.assertEqual(response.data['average_compatibility_score'], 0)
        self.assertIsNone(response.data['most_worn_item'])

    def test_item_with_null_occasion_type_is_handled(self):
        WardrobeItem.objects.create(
            user=self.user, **item_kwargs('n-1', occasion_type=[])
        )
        response = self.client.get('/api/analytics/')
        self.assertEqual(response.status_code, 200)

    def test_saved_bundles_avg_score(self):
        WardrobeItem.objects.create(user=self.user, **item_kwargs('n-1'))
        OutfitBundle.objects.create(
            bundle_id='b-1', user=self.user, items=['n-1'],
            compatibility_score=80.0, dominant_color='Black',
            dominant_palette='Neutral', occasion_tags=['Formal', 'Business'],
            style_tags=[], mood_tags=[], is_saved=True, source='user_generated',
            created_at='2026-08-19T00:00:00Z',
        )
        response = self.client.get('/api/analytics/')
        self.assertEqual(response.data['average_compatibility_score'], 80.0)
        self.assertIn('Formal', response.data['occasion_distribution'])


class WearLogTests(TestCase):
    """Sections 4, 13: validation, taxonomy normalization, ownership."""

    def setUp(self):
        self.user = make_user()
        self.other = make_user('+919999999902')
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token_for(self.user)}')

    def _bundle(self, owner, bundle_id, items):
        return OutfitBundle.objects.create(
            bundle_id=bundle_id, user=owner, items=items,
            compatibility_score=70.0, dominant_color='Black',
            dominant_palette='Neutral', occasion_tags=['Formal', 'Business'],
            style_tags=[], mood_tags=[], source='user_generated',
            created_at='2026-08-19T00:00:00Z',
        )

    def test_post_missing_fields_returns_400(self):
        response = self.client.post('/api/wearlog/', {'worn_date': '2026-08-19'}, format='json')
        self.assertEqual(response.status_code, 400)

    def test_post_unknown_occasion_is_preserved(self):
        response = self.client.post(
            '/api/wearlog/',
            {'worn_date': '2026-08-19', 'occasion_tag': 'My Custom Vibe'},
            format='json',
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['occasion_tag'], 'My Custom Vibe')

    def test_post_occasion_is_normalized_to_taxonomy(self):
        response = self.client.post(
            '/api/wearlog/',
            {'worn_date': '2026-08-19', 'occasion_tag': 'business'},
            format='json',
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['occasion_tag'], 'Business')

    def test_post_with_own_bundle_increments_counts(self):
        item = WardrobeItem.objects.create(user=self.user, **item_kwargs('w-1'))
        bundle = self._bundle(self.user, 'b-own', ['w-1'])
        response = self.client.post(
            '/api/wearlog/',
            {'worn_date': '2026-08-19', 'occasion_tag': 'Business', 'bundle_id': 'b-own'},
            format='json',
        )
        self.assertEqual(response.status_code, 201)
        item.refresh_from_db()
        bundle.refresh_from_db()
        self.assertEqual(item.wear_count, 1)
        self.assertEqual(bundle.wear_count, 1)
        self.assertEqual(WearLog.objects.get(log_id=response.data['log_id']).item_ids, ['w-1'])

    def test_post_with_other_users_bundle_does_not_touch_it(self):
        # AUDIT EXPECTED: another user's bundle must not be mutated.
        self._bundle(self.other, 'b-other', ['w-9'])
        response = self.client.post(
            '/api/wearlog/',
            {'worn_date': '2026-08-19', 'occasion_tag': 'Business', 'bundle_id': 'b-other'},
            format='json',
        )
        self.assertEqual(response.status_code, 201)
        bundle = OutfitBundle.objects.get(bundle_id='b-other')
        self.assertEqual(bundle.wear_count, 0)

    def test_get_lists_own_logs(self):
        self.client.post(
            '/api/wearlog/', {'worn_date': '2026-08-19', 'occasion_tag': 'Casual'},
            format='json',
        )
        response = self.client.get('/api/wearlog/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['occasion_tag'], 'Casual')


class WishlistTests(TestCase):
    """Sections 4, 10, 13: validation, 404s, ownership."""

    def setUp(self):
        self.user = make_user()
        self.other = make_user('+919999999903')
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token_for(self.user)}')

    def test_post_missing_fields_returns_400(self):
        response = self.client.post('/api/wishlist/', {}, format='json')
        self.assertEqual(response.status_code, 400)

    def test_post_invalid_item_type_returns_400(self):
        response = self.client.post(
            '/api/wishlist/', {'item_type': 'banana', 'item_id': 'x'}, format='json'
        )
        self.assertEqual(response.status_code, 400)

    def test_post_unknown_product_returns_404(self):
        response = self.client.post(
            '/api/wishlist/', {'item_type': 'product', 'product_id': 'missing'}, format='json'
        )
        self.assertEqual(response.status_code, 404)

    def test_post_wardrobe_item_like_and_unlike(self):
        WardrobeItem.objects.create(user=self.user, **item_kwargs('w-1'))
        response = self.client.post(
            '/api/wishlist/', {'item_type': 'wardrobe_item', 'item_id': 'w-1'}, format='json'
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['item_type'], 'wardrobe_item')
        self.assertEqual(response.data['wardrobe_item']['item_id'], 'w-1')

        dup = self.client.post(
            '/api/wishlist/', {'item_type': 'wardrobe_item', 'item_id': 'w-1'}, format='json'
        )
        self.assertEqual(dup.status_code, 200)

        listed = self.client.get('/api/wishlist/')
        self.assertEqual(len(listed.data), 1)

        removed = self.client.delete(
            '/api/wishlist/', {'item_type': 'wardrobe_item', 'item_id': 'w-1'}, format='json'
        )
        self.assertEqual(removed.status_code, 200)
        self.assertTrue(removed.data['removed'])

        again = self.client.delete(
            '/api/wishlist/', {'item_type': 'wardrobe_item', 'item_id': 'w-1'}, format='json'
        )
        self.assertEqual(again.status_code, 200)
        self.assertFalse(again.data['removed'])

    def test_liking_other_users_bundle_is_forbidden(self):
        # AUDIT EXPECTED: a user must not be able to like/read another user's
        # private bundle (and must not persist a snapshot of it).
        OutfitBundle.objects.create(
            bundle_id='b-other', user=self.other, items=['w-9'],
            compatibility_score=90.0, dominant_color='Black',
            dominant_palette='Neutral', occasion_tags=['Formal'],
            style_tags=[], mood_tags=[], source='user_generated',
            created_at='2026-08-19T00:00:00Z',
        )
        response = self.client.post(
            '/api/wishlist/', {'item_type': 'bundle', 'bundle_id': 'b-other'}, format='json'
        )
        self.assertEqual(response.status_code, 404)


class HomePageFilterAuditTests(TestCase):
    """Sections 7, 8: every Home Page filter label resolves safely."""

    LABELS = ['formal', 'smart-casual', 'casual', 'party', 'wedding',
              'streetwear', 'sports', 'travel', 'date', 'all']

    def setUp(self):
        self.user = make_user()
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token_for(self.user)}')
        WardrobeItem.objects.create(user=self.user, **item_kwargs('t-1'))
        WardrobeItem.objects.create(
            user=self.user, **item_kwargs('b-1', category='Bottom',
                                          subcategory='Trousers')
        )
        WardrobeItem.objects.create(
            user=self.user, **item_kwargs('s-1', category='Footwear',
                                          subcategory='Loafers')
        )

    def test_every_home_page_label_returns_200(self):
        for label in self.LABELS:
            response = self.client.get('/api/bundles/', {'occasion': label})
            self.assertEqual(response.status_code, 200, label)

    def test_every_label_returns_occasion_relevance(self):
        for label in self.LABELS:
            response = self.client.get('/api/bundles/', {'occasion': label})
            self.assertEqual(response.status_code, 200, label)
            for bundle in response.data:
                self.assertIn('occasion_relevance', bundle, label)

    def test_unknown_label_returns_400(self):
        response = self.client.get('/api/bundles/', {'occasion': 'not-a-real-tag'})
        self.assertEqual(response.status_code, 400)

    def test_formal_style_combination(self):
        response = self.client.get(
            '/api/bundles/', {'occasion': 'formal', 'style': 'minimalist'}
        )
        self.assertEqual(response.status_code, 200)

    def test_casual_style_combination(self):
        response = self.client.get(
            '/api/bundles/', {'occasion': 'casual', 'style': 'streetwear'}
        )
        self.assertEqual(response.status_code, 200)


class TaxonomyAuditTests(TestCase):
    """Section 5: hierarchy resolution via the public endpoint."""

    def setUp(self):
        self.user = make_user()
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token_for(self.user)}')

    def test_taxonomy_endpoint_shape(self):
        response = self.client.get('/api/occasions/taxonomy')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data['parents']), 11)
        formal = next(p for p in response.data['parents'] if p['name'] == 'Formal')
        self.assertIn('Business', formal['children'])
        self.assertIn('Work / Office', formal['children'])

    def test_parent_does_not_imply_every_child(self):
        response = self.client.get('/api/occasions/taxonomy')
        formal = next(p for p in response.data['parents'] if p['name'] == 'Formal')
        self.assertEqual(len(formal['children']), 10)
        # 'Party' belongs to Party & Nightlife, not Formal.
        party_parent = next(
            p for p in response.data['parents'] if p['name'] == 'Party & Nightlife'
        )
        self.assertIn('Party', party_parent['children'])

    def test_unknown_occasion_in_filter_is_safe(self):
        response = self.client.get('/api/bundles/', {'occasion': 'diwali-fusion'})
        self.assertEqual(response.status_code, 400)
        self.assertIn('detail', response.data)
        # The taxonomy source of truth must be untouched by the bad request.
        taxonomy = self.client.get('/api/occasions/taxonomy')
        payload_text = taxonomy.content.decode()
        self.assertNotIn('diwali-fusion', payload_text)


class ExternalServiceFailureTests(TestCase):
    """Section 12: third-party failures must stay controlled."""

    def setUp(self):
        self.user = make_user()
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token_for(self.user)}')
        self.url = '/api/wardrobe/add-product-link'

    @mock.patch('api.views_upload.scrape_clothing_product')
    @mock.patch('api.views_upload.gemini_service.extract_product_metadata_from_evidence')
    def test_gemini_failure_still_imports_product(self, mock_gemini, mock_scrape):
        mock_gemini.side_effect = RuntimeError('Gemini down')
        mock_scrape.return_value = {
            'name': 'Crewneck', 'color': 'Black', 'type': 'T-Shirt',
            'category': 'Top Wear', 'image_url': 'https://x/i.jpg',
            'source_url': 'https://x/p', 'brand': 'Nike',
            'evidence': {'name': 'Crewneck', 'structured_category': 'Top Wear'},
        }
        response = self.client.post(self.url, {'url': 'https://x/p'}, format='json')
        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.data['product']['fallback_used'])
        self.assertEqual(
            response.data['product']['occasion_type'], ['Casual']
        )

    @mock.patch('api.views_upload.scrape_clothing_product')
    def test_scrape_error_returns_400(self, mock_scrape):
        from services.product_link_scraper import ProductScrapeError
        mock_scrape.side_effect = ProductScrapeError('Could not parse')
        response = self.client.post(self.url, {'url': 'https://x/p'}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('Could not parse', response.data['error'])

    @mock.patch('api.views_upload.scrape_clothing_product')
    def test_unexpected_scrape_failure_returns_500_without_traceback(self, mock_scrape):
        mock_scrape.side_effect = RuntimeError('boom')
        response = self.client.post(self.url, {'url': 'https://x/p'}, format='json')
        self.assertEqual(response.status_code, 500)
        self.assertNotIn('Traceback', response.content.decode())
        self.assertNotIn('boom', response.content.decode())

    def test_missing_url_returns_400(self):
        response = self.client.post(self.url, {}, format='json')
        self.assertEqual(response.status_code, 400)

    def test_upload_product_missing_image_returns_400(self):
        response = self.client.post(
            '/api/wardrobe/upload-product',
            {'name': 'x', 'color': 'Black', 'type': 'T-Shirt', 'category': 'Top Wear'},
            format='multipart',
        )
        self.assertEqual(response.status_code, 400)

    def test_upload_product_bad_extension_returns_400(self):
        response = self.client.post(
            '/api/wardrobe/upload-product',
            {'image': io.BytesIO(b'x' * 100), 'name': 'x', 'color': 'Black',
             'type': 'T-Shirt', 'category': 'Top Wear'},
            format='multipart',
        )
        self.assertEqual(response.status_code, 400)

    @mock.patch('api.views_upload.gemini_service.generate_ecommerce_image')
    @mock.patch('api.views_upload.gemini_service.extract_product_metadata_from_evidence')
    def test_upload_product_gemini_failure_returns_fallback_metadata(self, mock_meta, mock_gen):
        mock_meta.side_effect = RuntimeError('Gemini down')
        mock_gen.side_effect = RuntimeError('Nano Banana down')
        image = io.BytesIO(tiny_image_bytes())
        image.name = 'shirt.png'
        response = self.client.post(
            '/api/wardrobe/upload-product',
            {'image': image, 'name': 'Blue Tee', 'color': 'Blue',
             'type': 'T-Shirt', 'category': 'Top Wear'},
            format='multipart',
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['success'])
        self.assertTrue(response.data['fallback_used'])
        self.assertEqual(response.data['product']['metadata']['occasion_type'], ['Casual'])


@override_settings(MEDIA_ROOT=AUDIT_MEDIA_ROOT)
class ApproveProductAuditTests(TestCase):
    """Sections 4, 15: approval validation + boolean handling."""

    @classmethod
    def tearDownClass(cls):
        if os.path.exists(AUDIT_MEDIA_ROOT):
            shutil.rmtree(AUDIT_MEDIA_ROOT, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.user = make_user()
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token_for(self.user)}')
        self.media_root = AUDIT_MEDIA_ROOT
        self.temp_dir = os.path.join(self.media_root, 'temp')
        os.makedirs(self.temp_dir, exist_ok=True)
        self.orig = 'orig_audit1.png'
        self.gen = 'gen_audit1.png'
        for name in (self.orig, self.gen):
            with open(os.path.join(self.temp_dir, name), 'wb') as f:
                f.write(b'fake-image-bytes')

    def tearDown(self):
        if os.path.exists(self.media_root):
            shutil.rmtree(self.media_root, ignore_errors=True)

    def _payload(self, approved):
        return {
            'approved': approved,
            'temp_orig_name': self.orig,
            'temp_gen_name': self.gen,
            'product': {'name': 'Tee', 'color': 'Black', 'type': 'T-Shirt',
                        'category': 'Top Wear'},
        }

    def test_missing_fields_returns_400(self):
        response = self.client.post('/api/wardrobe/approve-product', {}, format='json')
        self.assertEqual(response.status_code, 400)

    def test_rejected_approval_cleans_up_and_returns_200(self):
        response = self.client.post(
            '/api/wardrobe/approve-product', self._payload(False), format='json'
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(os.path.exists(os.path.join(self.temp_dir, self.orig)))

    def test_approved_true_creates_item(self):
        response = self.client.post(
            '/api/wardrobe/approve-product', self._payload(True), format='json'
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(WardrobeItem.objects.count(), 1)

    def test_string_false_is_rejected(self):
        # AUDIT EXPECTED: the string "false" must not be treated as True.
        response = self.client.post(
            '/api/wardrobe/approve-product', self._payload('false'), format='json'
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(WardrobeItem.objects.count(), 0)


class BundleGenerateEndpointTests(TestCase):
    """Sections 6, 10: anchored generation endpoints."""

    def setUp(self):
        self.user = make_user()
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token_for(self.user)}')

    def test_homepage_and_best_selling_return_200(self):
        self.assertEqual(self.client.get('/api/bundle-generate/homepage/').status_code, 200)
        self.assertEqual(
            self.client.get('/api/bundle-generate/homepage/best-selling/').status_code, 200
        )

    def test_recommend_missing_id_returns_400(self):
        response = self.client.post('/api/bundle-generate/recommend/', {}, format='json')
        self.assertEqual(response.status_code, 400)

    def test_recommend_unknown_item_returns_404(self):
        response = self.client.post(
            '/api/bundle-generate/recommend/', {'product_id': 'missing'}, format='json'
        )
        self.assertEqual(response.status_code, 404)

    def test_recommend_without_complements_returns_empty_200(self):
        WardrobeItem.objects.create(user=self.user, **item_kwargs('only-top'))
        response = self.client.post(
            '/api/bundle-generate/recommend/', {'product_id': 'only-top'}, format='json'
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, [])

    def test_recommend_with_complete_wardrobe_returns_bundles(self):
        WardrobeItem.objects.create(user=self.user, **item_kwargs('t-1'))
        WardrobeItem.objects.create(
            user=self.user, **item_kwargs('b-1', category='Bottom',
                                          subcategory='Trousers')
        )
        WardrobeItem.objects.create(
            user=self.user, **item_kwargs('s-1', category='Footwear',
                                          subcategory='Loafers')
        )
        response = self.client.post(
            '/api/bundle-generate/recommend/', {'product_id': 't-1'}, format='json'
        )
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.data, list)

    def test_recommend_from_wardrobe_flow(self):
        WardrobeItem.objects.create(user=self.user, **item_kwargs('t-2'))
        response = self.client.post(
            '/api/bundle-generate/recommend-from-wardrobe/', {'item_id': 't-2'}, format='json'
        )
        self.assertEqual(response.status_code, 200)


class AiSuggestionEndpointTests(TestCase):
    """Sections 6, 12: AI suggestion endpoints handle empty data gracefully."""

    def setUp(self):
        self.user = make_user()
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token_for(self.user)}')

    def test_no_candidates_returns_404_detail(self):
        response = self.client.get('/api/ai-generation/topwear-suggestion/')
        self.assertEqual(response.status_code, 404)
        self.assertIn('detail', response.data)


class AvatarEndpointTests(TestCase):
    """Section 12: avatar generation survives external failures."""

    def setUp(self):
        self.user = make_user()
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token_for(self.user)}')

    def test_missing_image_returns_400(self):
        response = self.client.post(
            '/api/wardrobe/generate-avatar',
            {'name': 'x', 'color': 'Black', 'type': 'T-Shirt', 'category': 'Top Wear'},
            format='multipart',
        )
        self.assertEqual(response.status_code, 400)

    @mock.patch('api.views_avatar.huggingface_service.generate_avatar_image')
    @mock.patch('api.views_avatar.gemini_service.extract_product_metadata')
    def test_avatar_generation_failure_returns_200_with_flag(self, mock_gemini, mock_avatar):
        mock_gemini.side_effect = RuntimeError('Gemini down')
        mock_avatar.return_value = None
        image = io.BytesIO(tiny_image_bytes())
        image.name = 'tee.png'
        response = self.client.post(
            '/api/wardrobe/generate-avatar',
            {'image': image, 'name': 'Tee', 'color': 'Black',
             'type': 'T-Shirt', 'category': 'Top Wear'},
            format='multipart',
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['success'])
        self.assertFalse(response.data['avatar_generated'])
        self.assertIsNone(response.data['avatar_url'])
        self.assertIn('occasion_tags', response.data)
        self.assertEqual(response.data['uploaded_item']['occasion_type'], ['Casual'])


class OnboardingSubmitAuditTests(TestCase):
    """Sections 12, 13: onboarding completes with realistic list answers."""

    def setUp(self):
        self.user = make_user()
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token_for(self.user)}')
        OnboardingQuestion.objects.create(
            text='What Is Your Style?', question_type='multiple_choice', order=1
        )

    def test_multiple_choice_list_answers_complete_onboarding(self):
        # AUDIT EXPECTED: a list answer to a multiple-choice question must be
        # treated as an answered question so onboarding can complete.
        response = self.client.post(
            '/auth/onboarding/submit/',
            {'responses': {'styles': ['Casual', 'Streetwear']},
             'full_name': 'Audit User', 'email': 'audit@example.com'},
            format='json',
        )
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_onboarded)


class ResponseStructureTests(TestCase):
    """Sections 3, 11: field names/types survive DB -> serializer -> response."""

    def setUp(self):
        self.user = make_user()
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token_for(self.user)}')

    def test_wardrobe_response_fields_match_serializer(self):
        WardrobeItem.objects.create(user=self.user, **item_kwargs('r-1'))
        response = self.client.get('/api/wardrobe/')
        item = response.data[0]
        self.assertIsInstance(item['occasion_type'], list)
        self.assertIsInstance(item['style_tags'], list)
        self.assertEqual(item['formality_level'], 5)
        self.assertIsInstance(item['wear_count'], int)
        self.assertNotIn('undefined', json_dumps(item))

    def test_bundle_response_has_occasion_relevance(self):
        WardrobeItem.objects.create(user=self.user, **item_kwargs('r-1'))
        WardrobeItem.objects.create(
            user=self.user, **item_kwargs('r-2', category='Bottom',
                                          subcategory='Trousers')
        )
        WardrobeItem.objects.create(
            user=self.user, **item_kwargs('r-3', category='Footwear',
                                          subcategory='Loafers')
        )
        response = self.client.get('/api/bundles/')
        self.assertEqual(response.status_code, 200)
        for bundle in response.data:
            for field in ('bundle_id', 'items', 'compatibility_score',
                          'dominant_color', 'occasion_tags', 'style_tags',
                          'occasion_relevance'):
                self.assertIn(field, bundle, field)
            self.assertIsInstance(bundle['items'], list)
            self.assertIsInstance(bundle['occasion_relevance'], dict)

    def test_marketplace_response_is_array(self):
        response = self.client.get('/api/marketplace')
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.data, list)


def json_dumps(data):
    import json
    return json.dumps(data)