from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from api.models import Category, WardrobeItem
from .services import generate_ai_bundles, get_ai_candidates, serialize_item


class AISuggestionBaseView(APIView):
    category = None

    def handle_request(self, request):
        user = request.user

        occasion = request.data.get('occasion') or request.query_params.get('occasion')
        season = request.data.get('season') or request.query_params.get('season')

        wardrobe_items = list(WardrobeItem.objects.filter(user=user))
        owned_ids = {item.item_id for item in wardrobe_items}

        ai_candidates = get_ai_candidates(
            self.category,
            occasion=occasion,
            season=season,
            excluded_ids=owned_ids,
            limit=20,
        )
        if not ai_candidates:
            return Response(
                {"detail": "No AI suggestions available for this category."},
                status=status.HTTP_404_NOT_FOUND,
            )

        bundles, best_ai_item, error = generate_ai_bundles(self.category, wardrobe_items, ai_candidates)
        if error:
            return Response({"detail": error}, status=status.HTTP_400_BAD_REQUEST)

        return Response({
            "category": self.category,
            "recommended_item": serialize_item(best_ai_item, is_ai=True),
            "bundles": bundles,
        }, status=status.HTTP_200_OK)

    def get(self, request):
        return self.handle_request(request)

    def post(self, request):
        return self.handle_request(request)


class TopwearSuggestionView(AISuggestionBaseView):
    category = Category.TOP


class BottomwearSuggestionView(AISuggestionBaseView):
    category = Category.BOTTOM


class FootwearSuggestionView(AISuggestionBaseView):
    category = Category.FOOTWEAR
