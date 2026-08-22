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
from services.occasion_taxonomy import (
    expand_occasion_list,
    normalize_occasion_list,
    normalize_tag,
    occasion_relevance,
)


def _resolve_occasion_filter(value):
    """Validate + expand an occasion query token.

    Returns ``None`` when no occasion filter applies (absent, empty, or
    ``all``), or the expanded canonical tag set otherwise. Raises
    ``ValueError`` for unknown tokens — the taxonomy is never extended from
    user input.
    """
    if not value:
        return None
    token = str(value).strip()
    if token.casefold() == 'all':
        return None
    if normalize_tag(token) is None:
        raise ValueError(token)
    return expand_occasion_list([token])


def _matches_style(bundle, style: str) -> bool:
    """Case-insensitive style membership on existing bundle style metadata."""
    target = str(style).strip().casefold()
    return any(tag.casefold() == target for tag in (bundle.style_tags or []))


class BundleListView(APIView):
    """
    GET /api/bundles/?occasion=<occasion>&style=<style>

    Returns up to 10 deduplicated outfit bundles for the requesting user,
    merging stored bundles with freshly generated ones.

    Filters (additive — combined context, never reset):
      * ``occasion`` — a taxonomy tag or ``all``. Parents expand to their
        descendants; children match strictly (a generic parent-only bundle
        does not auto-qualify for a child request). Unknown tags return 400.
      * ``style`` — case-insensitive match on existing bundle style_tags.

    Each returned bundle carries an ``occasion_relevance`` map (canonical tag
    -> 1.0/0.5) derived from the bundle's occasion tags.
    """

    def get(self, request):
        try:
            expanded_occasions = _resolve_occasion_filter(
                request.query_params.get('occasion')
            )
        except ValueError as exc:
            return Response(
                {
                    'detail': (
                        f"Unknown occasion filter '{exc}'. Use a taxonomy tag "
                        "or 'all'."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        occasion = request.query_params.get('occasion')
        style = request.query_params.get('style')

        # ── Stored bundles ────────────────────────────────────────────────────
        stored_bundles = list(OutfitBundle.objects.filter(user=request.user))
        if expanded_occasions is not None:
            stored_bundles = [
                b for b in stored_bundles
                if expanded_occasions & set(normalize_occasion_list(b.occasion_tags))
            ]
        if style:
            stored_bundles = [b for b in stored_bundles if _matches_style(b, style)]

        # ── User wardrobe & preferences ───────────────────────────────────────
        user_wardrobe = list(WardrobeItem.objects.filter(user=request.user))
        preferences = preferences_for_user(request.user)
        avoided_colors = preferences.get('avoided_colors', [])
        item_lookup = {str(getattr(item, 'item_id', '')): item for item in user_wardrobe}

        # ── Personalized bundle generation ────────────────────────────────────
        # Every eligible wardrobe item is fed into the engine (no top-K cap,
        # no per-category limits). The engine generates ALL valid combinations,
        # scores them, and returns the full list ranked by ranking_score
        # (compatibility + personalization − diversity penalty).
        # Onboarding preferences are merged by the profile builder.
        recommendation_engine = RecommendationEngine()
        recommendation_result = recommendation_engine.recommend(
            items=user_wardrobe,
            user_profile=preferences,
            user_id=str(request.user.user_uid),
            occasion_filter=occasion if expanded_occasions is not None else None,
            avoided_colors=avoided_colors,
        )
        generated_bundles = [scored.bundle for scored in recommendation_result.bundles]
        if style:
            generated_bundles = [b for b in generated_bundles if _matches_style(b, style)]

        # ── Score stored bundles with the SAME canonical formula ──────────────
        # Stored bundles were never scored at request time, so the personalization
        # (onboarding bonus 0–30) is computed here from the same preferences and
        # wardrobe the engine uses.
        for bundle in stored_bundles:
            pers = recommendation_engine.personalizer.score_bundle(
                bundle=bundle,
                user_preferences=preferences,
                item_lookup=item_lookup,
            )
            bundle.personalization_score = round(pers.score, 2)

        # ── Merge & deduplicate by sorted item list ───────────────────────────
        all_bundles = stored_bundles + generated_bundles
        seen = set()
        deduplicated = []
        for bundle in all_bundles:
            key = ",".join(sorted(bundle.items))
            if key not in seen:
                seen.add(key)
                deduplicated.append(bundle)

        # ── Rank by the canonical score (compat + pers − diversity) ───────────
        # Diversity penalties are computed against the FULL merged set so stored
        # and generated bundles compete on exactly the same basis, then the
        # ranking score is recomputed for every bundle. The occasion filter only
        # selects candidates; it never changes their ranking values.
        from engine.recommendation_engine import (
            bundle_ranking_score,
            compute_diversity_penalties,
        )

        compute_diversity_penalties(deduplicated, item_lookup=item_lookup)
        for bundle in deduplicated:
            bundle.ranking_score = bundle_ranking_score(
                bundle.compatibility_score,
                bundle.personalization_score,
                bundle.diversity_penalty,
            )
        deduplicated.sort(key=lambda bundle: bundle.ranking_score, reverse=True)

        # ── Serialize (ORM objects use serializer; raw dicts pass through) ─────
        # `occasion_relevance` is additive: each bundle carries its derived
        # occasion profile so the frontend can render/maintain its filter
        # without re-requesting the taxonomy hierarchy per bundle.
        response_data = []
        for bundle in deduplicated:
            if isinstance(bundle, OutfitBundle):
                data = dict(OutfitBundleSerializer(bundle).data)
            else:
                data = dict(bundle)
            data['occasion_relevance'] = occasion_relevance(bundle.occasion_tags)
            response_data.append(data)

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

        # ── Filter by occasion tag (hierarchy-aware: a parent occasion also
        #    matches bundles tagged with its descendant children) ─────────────
        if occasion:
            expanded_occasions = expand_occasion_list([occasion])
            bundles = [
                b for b in bundles
                if expanded_occasions & set(normalize_occasion_list(b.occasion_tags))
            ]

        # ── Filter by style tag ───────────────────────────────────────────────
        if style:
            bundles = [b for b in bundles if _matches_style(b, style)]

        serializer = MarketplaceBundleSerializer(bundles, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
