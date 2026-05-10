"""
Bundle Generation - Django REST Framework
=========================================
This module previously used FastAPI. It has been fully converted to
Django REST Framework (DRF). The three endpoints below preserve the
original logic from the FastAPI version:

  GET  /api/bundles/<user_id>         → BundleListView
  POST /api/bundles/<user_id>/save    → SaveBundleView
  GET  /api/marketplace               → MarketplaceView

These views are registered in api/urls.py and served via Django's
URL routing (dripcheck_django/urls.py → api/).
"""

# ──────────────────────────────────────────────────────────────────────────────
# NOTE: FastAPI / uvicorn have been removed. This file now documents the
#       DRF view classes that live in api/views.py and are wired in api/urls.py.
#       Import them here for reference / re-export if needed.
# ──────────────────────────────────────────────────────────────────────────────

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404

from api.models import OutfitBundle, WardrobeItem, UserProfile, MarketplaceBundle
from api.serializers import OutfitBundleSerializer, MarketplaceBundleSerializer
from engine.compatibility_engine import generate_bundles


class BundleListView(APIView):
    """
    GET /api/bundles/<user_id>?occasion=<occasion>

    Returns up to 10 deduplicated outfit bundles for a user,
    merging stored bundles with freshly generated ones.
    An optional `occasion` query param filters both stored
    and generated bundles.
    """

    def get(self, request, user_id):
        occasion = request.query_params.get('occasion')

        # ── Stored bundles ────────────────────────────────────────────────────
        stored_bundles = list(OutfitBundle.objects.filter(user_id=user_id))
        if occasion:
            stored_bundles = [
                b for b in stored_bundles if occasion in (b.occasion_tags or [])
            ]

        # ── User wardrobe & preferences ───────────────────────────────────────
        user_wardrobe = list(WardrobeItem.objects.filter(user_id=user_id))
        try:
            user_profile = UserProfile.objects.get(user_id=user_id)
            avoided_colors = user_profile.avoided_colors or []
        except UserProfile.DoesNotExist:
            avoided_colors = []

        # ── Engine-generated bundles ──────────────────────────────────────────
        generated_bundles = generate_bundles(
            user_id, user_wardrobe, occasion, avoided_colors
        )

        # ── Merge & deduplicate by sorted item list ───────────────────────────
        all_bundles = stored_bundles + generated_bundles
        seen = set()
        deduplicated = []
        for bundle in all_bundles:
            key = ",".join(sorted(bundle.items))
            if key not in seen:
                seen.add(key)
                deduplicated.append(bundle)

        # ── Sort by compatibility score (highest first), cap at 10 ────────────
        deduplicated.sort(key=lambda b: b.compatibility_score, reverse=True)
        top_bundles = deduplicated[:10]

        # ── Serialize (ORM objects use serializer; raw dicts pass through) ─────
        response_data = []
        for bundle in top_bundles:
            if isinstance(bundle, OutfitBundle):
                response_data.append(OutfitBundleSerializer(bundle).data)
            else:
                response_data.append(bundle)

        return Response(response_data, status=status.HTTP_200_OK)


class SaveBundleView(APIView):
    """
    POST /api/bundles/<user_id>/save

    Saves an outfit bundle for a user. If the bundle already exists
    (matched by bundle_id + user_id), it is marked as saved in-place.
    Otherwise a new bundle record is created.
    """

    def post(self, request, user_id):
        data = request.data.copy()
        data['user_id'] = user_id
        data['is_saved'] = True

        bundle_id = data.get('bundle_id')

        # ── If bundle already exists, mark it saved ───────────────────────────
        if bundle_id:
            try:
                bundle = OutfitBundle.objects.get(bundle_id=bundle_id, user_id=user_id)
                bundle.is_saved = True
                bundle.save()
                return Response(OutfitBundleSerializer(bundle).data, status=status.HTTP_200_OK)
            except OutfitBundle.DoesNotExist:
                pass  # Fall through to create

        # ── Create a new saved bundle ─────────────────────────────────────────
        serializer = OutfitBundleSerializer(data=data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class MarketplaceView(APIView):
    """
    GET /api/marketplace?occasion=<occasion>&style=<style>

    Returns marketplace bundles, optionally filtered by occasion tag
    and/or style tag.
    """

    def get(self, request):
        occasion = request.query_params.get('occasion')
        style = request.query_params.get('style')

        bundles = MarketplaceBundle.objects.all()

        # ── Filter by occasion tag ────────────────────────────────────────────
        if occasion:
            bundles = [b for b in bundles if occasion in (b.occasion_tags or [])]

        # ── Filter by style tag ───────────────────────────────────────────────
        if style:
            bundles = [b for b in bundles if style in (b.style_tags or [])]

        serializer = MarketplaceBundleSerializer(bundles, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
