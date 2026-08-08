from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404

from .models import Wishlist, OutfitBundle, MarketplaceBundle, WardrobeItem
from .serializers import WishlistSerializer
from bundle_generate.models import MerchantProduct

VALID_ITEM_TYPES = {choice for choice, _ in Wishlist.ItemType.choices}


class WishlistView(APIView):
    """
    GET    /api/wishlist/                       → list the user's wishlist
    POST   /api/wishlist/                       → add an item
           {"item_type": "product", "product_id": "..."}
           {"item_type": "wardrobe_item", "wardrobe_item_id": "..."}
           {"item_type": "bundle", "bundle_id": "..."}
           {"item_type": "marketplace_bundle", "bundle_id": "..."}
           {"item_type": "ai_bundle", "bundle_id": "...", "bundle_data": {...}}
    DELETE /api/wishlist/                       → remove an item (same payload)
    """

    @staticmethod
    def _resolve_target(item_type, data):
        kwargs = {'item_type': item_type}

        if item_type == Wishlist.ItemType.PRODUCT:
            product_id = data.get('product_id')
            if not product_id:
                raise ValueError("product_id is required.")
            kwargs['product'] = get_object_or_404(MerchantProduct, product_id=product_id)

        elif item_type == Wishlist.ItemType.WARDROBE_ITEM:
            wardrobe_item_id = data.get('wardrobe_item_id')
            if not wardrobe_item_id:
                raise ValueError("wardrobe_item_id is required.")
            kwargs['wardrobe_item'] = get_object_or_404(WardrobeItem, item_id=wardrobe_item_id)

        elif item_type == Wishlist.ItemType.BUNDLE:
            bundle_id = data.get('bundle_id')
            if not bundle_id:
                raise ValueError("bundle_id is required.")
            kwargs['bundle'] = get_object_or_404(OutfitBundle, bundle_id=bundle_id)

        elif item_type == Wishlist.ItemType.MARKETPLACE_BUNDLE:
            bundle_id = data.get('bundle_id')
            if not bundle_id:
                raise ValueError("bundle_id is required.")
            kwargs['marketplace_bundle'] = get_object_or_404(MarketplaceBundle, bundle_id=bundle_id)

        elif item_type == Wishlist.ItemType.AI_BUNDLE:
            bundle_id = data.get('bundle_id')
            bundle_data = data.get('bundle_data')
            if not bundle_id or not bundle_data:
                raise ValueError("bundle_id and bundle_data are required.")
            kwargs['ai_bundle_id'] = bundle_id
            kwargs['bundle_data'] = bundle_data

        else:
            raise ValueError("item_type must be one of: product, wardrobe_item, bundle, marketplace_bundle, ai_bundle.")

        return kwargs

    def get(self, request):
        items = Wishlist.objects.filter(user=request.user)
        serializer = WishlistSerializer(items, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
        item_type = request.data.get('item_type')
        if item_type not in VALID_ITEM_TYPES:
            return Response(
                {"detail": "item_type must be one of: product, wardrobe_item, bundle, marketplace_bundle, ai_bundle."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            kwargs = self._resolve_target(item_type, request.data)
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        kwargs['user'] = request.user
        entry, created = Wishlist.objects.get_or_create(**kwargs)
        if not created:
            return Response({"detail": "Item already in wishlist."}, status=status.HTTP_409_CONFLICT)

        serializer = WishlistSerializer(entry)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def delete(self, request):
        item_type = request.data.get('item_type')
        target_id = request.data.get(
            'product_id'
            if item_type == Wishlist.ItemType.PRODUCT
            else 'wardrobe_item_id'
            if item_type == Wishlist.ItemType.WARDROBE_ITEM
            else 'bundle_id'
        )

        if item_type == Wishlist.ItemType.AI_BUNDLE:
            filters = {'user': request.user, 'item_type': item_type, 'ai_bundle_id': target_id}
        elif item_type in VALID_ITEM_TYPES and item_type != Wishlist.ItemType.AI_BUNDLE:
            field = {
                Wishlist.ItemType.PRODUCT: 'product_id',
                Wishlist.ItemType.WARDROBE_ITEM: 'wardrobe_item_id',
                Wishlist.ItemType.BUNDLE: 'bundle_id',
                Wishlist.ItemType.MARKETPLACE_BUNDLE: 'marketplace_bundle_id',
            }[item_type]
            filters = {'user': request.user, 'item_type': item_type, field: target_id}
        else:
            return Response(
                {"detail": "item_type must be one of: product, wardrobe_item, bundle, marketplace_bundle, ai_bundle."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not target_id:
            return Response({"detail": "product_id/wardrobe_item_id/bundle_id is required."}, status=status.HTTP_400_BAD_REQUEST)

        entry = Wishlist.objects.filter(**filters).first()
        if not entry:
            return Response({"detail": "Item not found in wishlist."}, status=status.HTTP_404_NOT_FOUND)

        entry.delete()
        return Response({"status": "success"}, status=status.HTTP_204_NO_CONTENT)