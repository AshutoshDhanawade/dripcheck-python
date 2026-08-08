"""
Bundle Generation - Django REST Framework
=========================================
This module previously used FastAPI. It has been fully converted to
Django REST Framework (DRF). The three endpoints below preserve the
original logic from the FastAPI version:

  GET  /api/bundles/         → BundleListView
  POST /api/bundles/save     → SaveBundleView
  GET  /api/marketplace      → MarketplaceView

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

from api.models import OutfitBundle, WardrobeItem, UserProfile, MarketplaceBundle
from api.serializers import OutfitBundleSerializer, MarketplaceBundleSerializer
from engine.recommendation_engine import RecommendationEngine
from engine.wardrobe_profile import preferences_for_user


class BundleListView(APIView):
    """
    GET /api/bundles/<user_id>?occasion=<occasion>

    Returns up to 10 deduplicated outfit bundles for a user,
    merging stored bundles with freshly generated ones.
    An optional `occasion` query param filters both stored
    and generated bundles.
    """

    def get(self, request):
        occasion = request.query_params.get('occasion')

        # ── Stored bundles ────────────────────────────────────────────────────
        stored_bundles = list(OutfitBundle.objects.filter(user=request.user))
        if occasion:
            stored_bundles = [
                b for b in stored_bundles if occasion in (b.occasion_tags or [])
            ]

        # ── User wardrobe & preferences ───────────────────────────────────────
        user_wardrobe = list(WardrobeItem.objects.filter(user=request.user))
        preferences = preferences_for_user(request.user)
        avoided_colors = preferences.get('avoided_colors', [])

        # ── Personalized bundle generation ────────────────────────────────────
        # The new personalization layer ranks the user's wardrobe by relevance,
        # keeps only the top-K most relevant items, feeds them into the existing
        # compatibility engine, then blends compatibility + personalization into
        # the final ranking. Onboarding preferences are merged by the profile
        # builder.
        recommendation_engine = RecommendationEngine(top_k=40)
        recommendation_result = recommendation_engine.recommend(
            items=user_wardrobe,
            user_profile=preferences,
            user_id=str(request.user.user_uid),
            occasion_filter=occasion,
            avoided_colors=avoided_colors,
        )
        generated_bundles = [scored.bundle for scored in recommendation_result.bundles]
        # Track the blended final score per generated bundle for later sorting.
        final_score_by_id = {
            scored.bundle.bundle_id: scored.final_score
            for scored in recommendation_result.bundles
        }

        # ── Merge & deduplicate by sorted item list ───────────────────────────
        all_bundles = stored_bundles + generated_bundles
        seen = set()
        deduplicated = []
        for bundle in all_bundles:
            key = ",".join(sorted(bundle.items))
            if key not in seen:
                seen.add(key)
                deduplicated.append(bundle)

        # ── Sort by blended score (personalized), falling back to compatibility ─
        deduplicated.sort(
            key=lambda b: final_score_by_id.get(b.bundle_id, b.compatibility_score),
            reverse=True,
        )

        # ── Serialize (ORM objects use serializer; raw dicts pass through) ─────
        response_data = []
        for bundle in deduplicated:
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

    def post(self, request):
        user = request.user
        data = request.data.copy()
        data['user'] = user.id
        data['is_saved'] = True

        bundle_id = data.get('bundle_id')

        # ── If bundle already exists, mark it saved ───────────────────────────
        if bundle_id:
            try:
                bundle = OutfitBundle.objects.get(bundle_id=bundle_id, user=request.user)
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
