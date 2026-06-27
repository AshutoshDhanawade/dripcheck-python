"""
api/views_avatar.py
====================
GenerateAvatarView — POST /api/wardrobe/generate-avatar

Flow:
  1. Accept multipart form data (image + clothing metadata + user_id)
  2. Map the uploaded item to the compatibility engine's WardrobeItem format
  3. Query DB for wardrobe items in the OTHER categories
  4. Run the compatibility engine to find the best-matching bundle
  5. Build a Qwen Image Edit prompt (using user profile attributes if available)
  6. Call Qwen/Qwen-Image-Edit via Hugging Face Diffusers
  7. Save avatar to media/avatars/
  8. Return avatar_url + bundle details + compatibility score
"""

import os
import uuid
import logging
from datetime import datetime

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.conf import settings

from .models import WardrobeItem, UserProfile
from .views_upload import clean_category, CATEGORY_MAPPING
from engine.compatibility_engine import (
    calculate_compatibility_score,
    assign_style_tags,
    compute_dominant_color,
    recommend_bundle_for_anchor,
)
from services import gemini_service, huggingface_service

logger = logging.getLogger(__name__)


# ── Inline fake WardrobeItem for compatibility engine ────────────────────────
class _FakeItem:
    """
    Mimics WardrobeItem's attribute interface so we can pass the user's
    newly uploaded item into the compatibility engine without saving it to DB first.
    """
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


# ── Category complement map ───────────────────────────────────────────────────
COMPLEMENT_MAP = {
    'Top':      ['Bottom', 'Footwear'],
    'Bottom':   ['Top', 'Footwear'],
    'Footwear': ['Top', 'Bottom'],
    'Layer':    ['Top', 'Bottom', 'Footwear'],
    'Accessory': ['Top', 'Bottom', 'Footwear'],
}

# DB category name → display name for prompt
CATEGORY_DISPLAY = {
    'Top': 'top',
    'Bottom': 'bottom',
    'Footwear': 'footwear',
    'Layer': 'layer/jacket',
    'Accessory': 'accessory',
}


def _item_to_dict(item: WardrobeItem) -> dict:
    """Convert a WardrobeItem ORM object to a plain dict for JSON serialization."""
    return {
        'item_id': item.item_id,
        'name': item.name,
        'category': item.category,
        'subcategory': item.subcategory,
        'primary_color': item.primary_color,
        'color_family': item.color_family,
        'pattern': item.pattern,
        'fit': item.fit,
        'occasion_type': item.occasion_type,
        'season': item.season,
        'formality_level': item.formality_level,
        'brand': item.brand,
        'image_url': item.image_url,
        'style_tags': item.style_tags,
    }


class GenerateAvatarView(APIView):
    """
    POST /api/wardrobe/generate-avatar

    Accepts multipart/form-data:
      - image      : File  (required) — the clothing item photo
      - name       : str   (required)
      - color      : str   (required)
      - type       : str   (required) — e.g. T-Shirt, Jeans, Sneakers
      - category   : str   (required) — Top Wear / Bottom Wear / Foot Wear
      - user_id    : str   (optional, default: user_demo)

    Returns:
      {
        "success": true,
        "avatar_url": "/media/avatars/<filename>",
        "avatar_generated": true/false,
        "bundle": [{ item dict }, ...],
        "uploaded_item": { ... },
        "compatibility_score": 72.5,
        "style_tags": ["Streetwear", "Minimalist"],
        "dominant_color": "Black",
        "occasion_tags": ["Casual", "Weekend"],
        "prompt_used": "..."
      }
    """

    def post(self, request):
        # ── 1. Parse & validate inputs ────────────────────────────────────────
        image_file = request.FILES.get('image')
        name       = request.data.get('name', '').strip()
        color      = request.data.get('color', '').strip()
        type_str   = request.data.get('type', '').strip()
        category   = request.data.get('category', 'Top Wear').strip()
        user_id    = request.data.get('user_id', 'user_demo')

        if not image_file:
            return Response(
                {"success": False, "error": "Image file is required."},
                status=status.HTTP_400_BAD_REQUEST
            )
        if not all([name, color, type_str, category]):
            return Response(
                {"success": False, "error": "Fields name, color, type, and category are required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # ── 2. Map category to DB enum ─────────────────────────────────────────
        db_category = clean_category(category)  # e.g. 'Top', 'Bottom', 'Footwear'

        # ── 3. Extract basic metadata from the image using Gemini (or fallback) ─
        try:
            with image_file.open('rb') as f:
                image_bytes = f.read()
        except Exception as e:
            logger.error(f"Failed to read image bytes: {e}")
            return Response(
                {"success": False, "error": "Failed to read the uploaded image."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        metadata = {}
        try:
            metadata = gemini_service.extract_product_metadata(
                image_bytes, name, color, type_str, category
            )
        except Exception as e:
            logger.warning(f"Gemini metadata extraction failed, using local fallback: {e}")
            metadata = gemini_service.infer_metadata_locally(name, color, type_str, category)

        # ── 4. Build a fake WardrobeItem for the uploaded piece ────────────────
        uploaded_fake = _FakeItem(
            item_id          = f"UPLOADED-{uuid.uuid4()}",
            name             = name,
            category         = db_category,
            subcategory      = type_str,
            primary_color    = color,
            secondary_color  = metadata.get('secondary_color'),
            color_family     = metadata.get('color_family', 'Neutral'),
            pattern          = metadata.get('pattern', 'Solid'),
            fit              = metadata.get('fit', 'Regular'),
            occasion_type    = metadata.get('occasion_type', ['Casual']),
            season           = metadata.get('season', 'All-season'),
            formality_level  = metadata.get('formality_level', 5),
            brand            = metadata.get('brand'),
            material         = metadata.get('material', 'Cotton'),
            style_tags       = metadata.get('style_tags', []),
            mood_tags        = metadata.get('mood_tags', []),
        )

        uploaded_item_desc = f"{color} {name} ({type_str})"

        # ── 5. Query DB for complementary items ───────────────────────────────
        needed_categories = COMPLEMENT_MAP.get(db_category, ['Top', 'Bottom', 'Footwear'])
        db_items = list(
            WardrobeItem.objects.filter(
                user_id=user_id,
                category__in=needed_categories
            )
        )

        # ── 6. Find best-matching bundle via compatibility engine ─────────────
        best_score        = 0.0
        best_style_tags   = []
        best_dominant     = {'color': color, 'palette': metadata.get('color_family', 'Neutral')}
        best_occasion     = metadata.get('occasion_type', ['Casual'])
        recommended_bundle = {
            'topwear': None,
            'bottomwear': None,
            'footwear': None,
            'outerwear': None,
        }
        best_bundle_items = []

        # Allow optional onboarding metadata to influence the prompt, not the core engine.
        gender          = request.data.get('gender', '').strip()
        age             = request.data.get('age', '').strip()
        preferred_style = request.data.get('preferred_style', '').strip()
        occasion_pref   = request.data.get('occasion', '').strip()
        season_pref     = request.data.get('season', '').strip()
        budget          = request.data.get('budget', '').strip()

        if db_items:
            recommendation = recommend_bundle_for_anchor(uploaded_fake, db_items)
            if recommendation['has_recommendations']:
                best_bundle_items = recommendation['items']
                best_score        = recommendation['matching_score'] * 100
                for slot, item in recommendation['recommended_bundle'].items():
                    recommended_bundle[slot] = item

                dom = compute_dominant_color(best_bundle_items)
                best_dominant   = dom
                tags_result     = assign_style_tags(best_bundle_items)
                best_style_tags = [t['name'] for t in tags_result[:3]]
                occ_set = set()
                for itm in best_bundle_items:
                    occ_set.update(getattr(itm, 'occasion_type', []) or [])
                best_occasion = list(occ_set)

        # Serialise bundle for response (exclude the uploaded fake item — include real DB items only)
        bundle_dicts = {}
        for slot, item in recommended_bundle.items():
            bundle_dicts[slot] = _item_to_dict(item) if isinstance(item, WardrobeItem) else None

        # ── 7. Build Qwen Image Edit prompt for avatar generation ──────────────
        qwen_prompt = huggingface_service.build_avatar_prompt(
            uploaded_item_desc = uploaded_item_desc,
            uploaded_category  = db_category,
            recommended_bundle = bundle_dicts,
            user_profile       = {
                'gender': gender,
                'age': age,
                'preferred_style': preferred_style,
                'occasion': occasion_pref,
                'season': season_pref,
                'budget': budget,
                'skin_tone':  None,
                'hair_color': None,
                'body_type':  None,
                'style_vibes': [],
            }
        )

        try:
            profile = UserProfile.objects.get(user_id=user_id)
            qwen_prompt = huggingface_service.build_avatar_prompt(
                uploaded_item_desc = uploaded_item_desc,
                uploaded_category  = db_category,
                recommended_bundle = bundle_dicts,
                user_profile       = {
                    'gender': gender,
                    'age': age,
                    'preferred_style': preferred_style,
                    'occasion': occasion_pref,
                    'season': season_pref,
                    'budget': budget,
                    'skin_tone':  profile.skin_tone,
                    'hair_color': profile.hair_color,
                    'body_type':  profile.body_type,
                    'style_vibes': profile.style_vibes or [],
                }
            )
        except UserProfile.DoesNotExist:
            pass

        # ── 8. Call Qwen avatar generation ─────────────────────────────────────
        avatar_bytes = huggingface_service.generate_avatar_image(
            qwen_prompt,
            image_bytes=image_bytes,
        )
        avatar_generated = avatar_bytes is not None

        avatar_url = None
        if avatar_generated:
            # Save to media/avatars/
            avatars_dir = os.path.join(settings.MEDIA_ROOT, 'avatars')
            os.makedirs(avatars_dir, exist_ok=True)

            avatar_filename = f"avatar_{uuid.uuid4()}.png"
            avatar_path     = os.path.join(avatars_dir, avatar_filename)

            try:
                with open(avatar_path, 'wb') as f:
                    f.write(avatar_bytes)
                avatar_url = f"{settings.MEDIA_URL}avatars/{avatar_filename}"
                logger.info(f"Avatar saved: {avatar_path}")
            except Exception as e:
                logger.error(f"Failed to save avatar image: {e}")
                avatar_generated = False

        # ── 10. Return response ────────────────────────────────────────────────
        uploaded_item_out = {
            'name':           name,
            'category':       db_category,
            'subcategory':    type_str,
            'primary_color':  color,
            'color_family':   metadata.get('color_family', 'Neutral'),
            'pattern':        metadata.get('pattern', 'Solid'),
            'fit':            metadata.get('fit', 'Regular'),
            'season':         metadata.get('season', 'All-season'),
            'formality_level': metadata.get('formality_level', 5),
            'style_tags':     metadata.get('style_tags', []),
            'occasion_type':  metadata.get('occasion_type', ['Casual']),
        }

        matching_score = round(best_score / 100, 2)

        return Response({
            "success":            True,
            "avatar_image_url":   avatar_url,
            "avatar_generated":   avatar_generated,
            "recommended_bundle": bundle_dicts,
            "uploaded_item":      uploaded_item_out,
            "compatibility_score": round(best_score, 1),
            "matching_score":     matching_score,
            "style_tags":         best_style_tags,
            "dominant_color":     best_dominant.get('color', color),
            "dominant_palette":   best_dominant.get('palette', 'Neutral'),
            "occasion_tags":      best_occasion,
            "generation_prompt":  qwen_prompt,
            "prompt_used":        qwen_prompt,
        }, status=status.HTTP_200_OK)
