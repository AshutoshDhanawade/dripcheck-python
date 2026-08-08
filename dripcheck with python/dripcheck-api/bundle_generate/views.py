from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404

from api.models import WardrobeItem, Category
from api.serializers import WardrobeItemSerializer, OutfitBundleSerializer
from engine.recommendation_engine import RecommendationEngine
from engine.wardrobe_profile import preferences_for_user

# Categories a complete outfit is expected to include; used to decide which
# categories still need filling from the user's own wardrobe.
REQUIRED_CATEGORIES = {Category.TOP, Category.BOTTOM, Category.FOOTWEAR}


def _fill_missing_categories_items(wardrobe_items, selected_item, max_per_category=8):
    """Return wardrobe items that fill the categories missing for the selected
    item. Built purely from the user's own wardrobe — no merchant catalog.
    """
    missing_categories = REQUIRED_CATEGORIES - {selected_item.category}
    if not missing_categories:
        return []

    fill_items = [
        item for item in wardrobe_items
        if item.category in missing_categories and item.item_id != selected_item.item_id
    ]

    grouped = {}
    for item in fill_items:
        grouped.setdefault(item.category, []).append(item)

    # Cap candidates per category to bound the combinatorial explosion.
    capped = []
    for category in missing_categories:
        capped.extend(grouped.get(category, [])[:max_per_category])
    return capped


class HomepageProductsView(APIView):
    """
    GET /api/bundle-generate/homepage/
    Returns products from the user's OWN wardrobe that fill the categories an
    outfit still needs. Categories are deduplicated so a returned product does
    not repeat again and again.
    """
    def get(self, request):
        category = request.query_params.get('category')

        wardrobe_items = list(WardrobeItem.objects.filter(user=request.user))
        if category:
            wardrobe_items = [item for item in wardrobe_items if item.category == category]

        # De-duplicate by item_id, preserving order.
        seen = set()
        unique = []
        for item in wardrobe_items:
            if item.item_id not in seen:
                seen.add(item.item_id)
                unique.append(item)

        serializer = WardrobeItemSerializer(unique, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class BestSellingProductsView(APIView):
    """
    GET /api/bundle-generate/homepage/best-selling/
    Returns the top N most-worn items from the user's own wardrobe. Previously
    sourced from a merchant catalog (sales_count); with no merchant data it now
    reflects what the user already wears most.
    """
    def get(self, request):
        items = list(WardrobeItem.objects.filter(user=request.user))[:10]
        items.sort(key=lambda item: (item.wear_count or 0, item.last_worn or ''), reverse=True)
        serializer = WardrobeItemSerializer(items, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class GenerateFromProductView(APIView):
    """
    POST /api/bundle-generate/recommend/

    Generates bundles anchored around a selected wardrobe item, filling the
    missing categories from the user's own wardrobe. Requires a valid JWT.
    """
    def post(self, request):
        data = request.data
        item_id = data.get('product_id') or data.get('item_id')

        if not item_id:
            return Response({"detail": "product_id is required."}, status=status.HTTP_400_BAD_REQUEST)

        # A user-wardrobe item acts as the anchor. Merchant products don't exist.
        selected_item = get_object_or_404(WardrobeItem, item_id=item_id, user=request.user)

        wardrobe_items = list(WardrobeItem.objects.filter(user=request.user))
        fill_items = _fill_missing_categories_items(wardrobe_items, selected_item)

        pool = [selected_item] + fill_items

        preferences = preferences_for_user(request.user)

        recommendation_engine = RecommendationEngine(top_k=40)
        recommendation_result = recommendation_engine.recommend(
            items=pool,
            user_profile=preferences,
            user_id=str(request.user.user_uid),
            avoided_colors=preferences.get('avoided_colors'),
            must_keep_ids=[selected_item.item_id],
        )
        generated_bundles = [scored.bundle for scored in recommendation_result.bundles]

        serializer = OutfitBundleSerializer(generated_bundles, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class GenerateFromWardrobeItemView(APIView):
    """
    POST /api/bundle-generate/recommend-from-wardrobe/
    Payload: {"item_id": "..."}
    Generates bundles centering around the user's selected wardrobe item, filling
    the rest from the user's own wardrobe. Requires a valid JWT.
    """
    def post(self, request):
        data = request.data
        item_id = data.get('item_id')

        if not item_id:
            return Response({"detail": "item_id is required."}, status=status.HTTP_400_BAD_REQUEST)

        selected_item = get_object_or_404(WardrobeItem, item_id=item_id, user=request.user)

        wardrobe_items = list(WardrobeItem.objects.filter(user=request.user))
        fill_items = _fill_missing_categories_items(wardrobe_items, selected_item)

        pool = [selected_item] + fill_items

        preferences = preferences_for_user(request.user)

        recommendation_engine = RecommendationEngine(top_k=40)
        recommendation_result = recommendation_engine.recommend(
            items=pool,
            user_profile=preferences,
            user_id=str(request.user.user_uid),
            avoided_colors=preferences.get('avoided_colors'),
            must_keep_ids=[selected_item.item_id],
        )
        generated_bundles = [scored.bundle for scored in recommendation_result.bundles]

        serializer = OutfitBundleSerializer(generated_bundles, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)