import uuid
from datetime import datetime
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from .models import WardrobeItem, UserProfile, WearLog, OutfitBundle, MarketplaceBundle, WishlistItem
from .serializers import WardrobeItemSerializer, UserProfileSerializer, WearLogSerializer, OutfitBundleSerializer, MarketplaceBundleSerializer, WishlistItemSerializer
from services.occasion_taxonomy import canonical_child, normalize_occasion_list, taxonomy_payload

class OccasionTaxonomyView(APIView):
    """
    GET /api/occasions/taxonomy

    Backend source of truth for the hierarchical occasion taxonomy. The
    frontend must not hardcode occasion lists — it fetches them here.
    """

    def get(self, request):
        return Response(taxonomy_payload())

class WardrobeListCreateView(APIView):
    def get(self, request):
        items = WardrobeItem.objects.filter(user=request.user)
        serializer = WardrobeItemSerializer(items, many=True)
        return Response(serializer.data)

    def post(self, request):
        data = request.data.copy()
        data['item_id'] = str(uuid.uuid4())
        user = request.user
        data['user'] = user.id
        data['added_at'] = datetime.utcnow().isoformat() + 'Z'
        data['wear_count'] = 0
        serializer = WardrobeItemSerializer(data=data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class WardrobeDetailView(APIView):
    def put(self, request, item_id):
        item = get_object_or_404(WardrobeItem, user=request.user, item_id=item_id)
        serializer = WardrobeItemSerializer(item, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, item_id):
        item = get_object_or_404(WardrobeItem, user=request.user, item_id=item_id)
        item.delete()
        OutfitBundle.objects.filter(user=request.user, items__contains=item_id).update(has_missing_item=True)
        return Response({"status": "success"}, status=status.HTTP_204_NO_CONTENT)

class UserProfileDetailView(APIView):
    def get(self, request):
        user_profile = get_object_or_404(UserProfile, user=request.user)
        serializer = UserProfileSerializer(user_profile)
        return Response(serializer.data)

    def put(self, request):
        user_obj = request.user
        data = request.data.copy()
        data['user'] = user_obj.id
        user_profile, created = UserProfile.objects.get_or_create(user=user_obj, defaults=data)
        if not created:
            serializer = UserProfileSerializer(user_profile, data=data, partial=True)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        serializer = UserProfileSerializer(user_profile)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

class AnalyticsView(APIView):
    def get(self, request):
        user_wardrobe = WardrobeItem.objects.filter(user=request.user)
        total_items = user_wardrobe.count()
        never_worn_count = user_wardrobe.filter(wear_count=0).count()
        
        most_worn_item = user_wardrobe.order_by('-wear_count').first()
        most_worn_item_data = WardrobeItemSerializer(most_worn_item).data if most_worn_item else None
        
        utilization_percentage = ((total_items - never_worn_count) / total_items * 100) if total_items > 0 else 0
        
        saved_bundles = OutfitBundle.objects.filter(user=request.user, is_saved=True)
        score_sum = sum(b.compatibility_score for b in saved_bundles)
        avg_score = score_sum / saved_bundles.count() if saved_bundles.count() else 0
        
        occasion_distribution = {}
        for item in user_wardrobe:
            for occ in item.occasion_type:
                occasion_distribution[occ] = occasion_distribution.get(occ, 0) + 1
                
        return Response({
            "total_items": total_items,
            "never_worn_count": never_worn_count,
            "most_worn_item": most_worn_item_data,
            "utilization_percentage": utilization_percentage,
            "average_compatibility_score": round(avg_score, 2),
            "occasion_distribution": occasion_distribution
        })

class WearLogView(APIView):
    def get(self, request):
        logs = WearLog.objects.filter(user=request.user)
        serializer = WearLogSerializer(logs, many=True)
        return Response(serializer.data)

    def post(self, request):
        user_obj = request.user
        data = request.data
        bundle_id = data.get("bundle_id")
        date = data.get("worn_date")
        occasion = data.get("occasion_tag")

        if not date or not occasion:
            return Response({"detail": "Missing worn_date or occasion_tag"}, status=status.HTTP_400_BAD_REQUEST)

        # Normalize free-form wear-log occasions through the taxonomy
        # (aliases + legacy values resolve to canonical tags; unknown values
        # are preserved as entered).
        occasion = canonical_child(occasion) or occasion
            
        item_ids = []
        if bundle_id:
            try:
                bundle = OutfitBundle.objects.get(bundle_id=bundle_id)
                bundle.wear_count += 1
                bundle.save()
                item_ids = bundle.items
            except OutfitBundle.DoesNotExist:
                pass
                
        for item_id in item_ids:
            try:
                item = WardrobeItem.objects.get(item_id=item_id, user=request.user)
                item.wear_count += 1
                item.last_worn = date
                item.save()
            except WardrobeItem.DoesNotExist:
                pass
                
        log_data = {
            "log_id": str(uuid.uuid4()),
            "user": user_obj.id,
            "bundle_id": bundle_id,
            "item_ids": item_ids,
            "occasion_tag": occasion,
            "worn_date": date
        }
        
        serializer = WearLogSerializer(data=log_data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


_ITEM_TYPE_ALIASES = {
    'product': 'product', 'products': 'product',
    'wardrobe_item': 'wardrobe_item', 'wardrobe': 'wardrobe_item',
    'wardrobe-item': 'wardrobe_item', 'item': 'wardrobe_item',
    'single': 'wardrobe_item', 'single_item': 'wardrobe_item',
    'bundle': 'bundle', 'bundles': 'bundle',
    'outfit': 'bundle', 'outfit_bundle': 'bundle',
    'marketplace_bundle': 'marketplace_bundle', 'marketplace': 'marketplace_bundle',
    'ai_bundle': 'ai_bundle', 'ai': 'ai_bundle',
}

_WISHLIST_ID_KEYS = ('item_id', 'wardrobe_item_id', 'product_id', 'bundle_id')


def _normalize_item_type(value):
    """Map common frontend type strings to a canonical wishlist item_type."""
    if not value:
        return None
    key = str(value).strip().lower()
    return _ITEM_TYPE_ALIASES.get(key)


def _extract_wishlist_id(data):
    """Pull the item id from whichever field the frontend used."""
    if not data:
        return None
    for key in _WISHLIST_ID_KEYS:
        val = data.get(key)
        if val:
            return str(val)
    return None


def _resolve_bundle_items(item_ids):
    """Resolve a list of wardrobe item ids into full item data (for bundle cards)."""
    resolved = []
    for iid in item_ids or []:
        item = WardrobeItem.objects.filter(item_id=iid).first()
        if item:
            resolved.append(WardrobeItemSerializer(item).data)
    return resolved


def _create_outfit_bundle_from_data(user, bundle_id, data):
    """Persist a generated/homepage bundle so it can be liked & re-fetched."""
    items = data.get('items')
    if not items:
        return None
    bundle, _ = OutfitBundle.objects.get_or_create(
        bundle_id=bundle_id,
        defaults={
            'user': user,
            'items': items,
            'compatibility_score': float(data.get('compatibility_score', 0) or 0),
            'dominant_color': data.get('dominant_color', '') or '',
            'dominant_palette': data.get('dominant_palette', '') or '',
            'occasion_tags': normalize_occasion_list(data.get('occasion_tags') or []),
            'style_tags': data.get('style_tags') or [],
            'mood_tags': data.get('mood_tags') or [],
            'is_saved': True,
            'wear_count': 0,
            'source': data.get('source', 'user_generated'),
            'created_at': data.get('created_at') or (datetime.utcnow().isoformat() + 'Z'),
        },
    )
    return bundle


def _build_wishlist_snapshot(user, item_type, item_id, bundle_data=None):
    """
    Build a JSON snapshot of the liked item at like-time.

    Returns (stored_item_type, snapshot_dict) — the stored type can differ
    from the requested one (e.g. a 'bundle' that resolves to a marketplace
    bundle). Returns (None, None) when the item cannot be found.
    """
    if item_type == 'wardrobe_item':
        item = WardrobeItem.objects.filter(item_id=item_id).first()
        return ('wardrobe_item', WardrobeItemSerializer(item).data) if item else (None, None)

    if item_type == 'product':
        try:
            from bundle_generate.models import MerchantProduct
            merchant = MerchantProduct.objects.filter(product_id=item_id).first()
            if merchant:
                return ('product', {
                    'product_id': merchant.product_id,
                    'name': merchant.name,
                    'category': merchant.category,
                    'subcategory': merchant.subcategory,
                    'primary_color': merchant.primary_color,
                    'secondary_color': merchant.secondary_color,
                    'color_family': merchant.color_family,
                    'pattern': merchant.pattern,
                    'fit': merchant.fit,
                    'occasion_type': merchant.occasion_type,
                    'season': merchant.season,
                    'formality_level': merchant.formality_level,
                    'brand': merchant.brand,
                    'material': merchant.material,
                    'style_tags': merchant.style_tags,
                    'mood_tags': merchant.mood_tags,
                    'aesthetic_tone': merchant.aesthetic_tone,
                    'image_url': merchant.image_url,
                    'price': str(merchant.price),
                })
        except Exception:
            pass
        return (None, None)

    if item_type == 'bundle':
        bundle = OutfitBundle.objects.filter(bundle_id=item_id).first()
        if not bundle and bundle_data and isinstance(bundle_data, dict):
            bundle = _create_outfit_bundle_from_data(user, item_id, bundle_data)
        if bundle:
            data = OutfitBundleSerializer(bundle).data
            data['items_data'] = _resolve_bundle_items(bundle.items)
            return ('bundle', data)
        marketplace = MarketplaceBundle.objects.filter(bundle_id=item_id).first()
        if marketplace:
            return ('marketplace_bundle', MarketplaceBundleSerializer(marketplace).data)
        return (None, None)

    if item_type == 'marketplace_bundle':
        marketplace = MarketplaceBundle.objects.filter(bundle_id=item_id).first()
        if marketplace:
            return ('marketplace_bundle', MarketplaceBundleSerializer(marketplace).data)
        return (None, None)

    if item_type == 'ai_bundle':
        if bundle_data is None:
            return (None, None)
        return ('ai_bundle', bundle_data)

    return (None, None)


def _serialize_wishlist(entry):
    """Build the nested response shape the frontend Wishlist page expects."""
    data = entry.item_data or {}
    payload = {
        'id': entry.wishlist_id,
        'item_type': entry.item_type,
        'created_at': entry.created_at,
    }
    if entry.item_type == 'product':
        payload['product'] = data
    elif entry.item_type == 'wardrobe_item':
        payload['wardrobe_item'] = data
    elif entry.item_type == 'bundle':
        if not data.get('items_data'):
            data = dict(data)
            data['items_data'] = _resolve_bundle_items(data.get('items'))
        payload['bundle'] = data
    elif entry.item_type == 'marketplace_bundle':
        payload['marketplace_bundle'] = data
    elif entry.item_type == 'ai_bundle':
        payload['bundle_data'] = data
        payload['ai_bundle_id'] = entry.item_id
    return payload


class WishlistView(APIView):
    """
    GET    /api/wishlist?tag=All|Products|Bundles  → list the user's wishlist
    POST   /api/wishlist {item_type, <id>, bundle_data?} → like / add
    DELETE /api/wishlist {item_type, <id>}          → unlike / remove
    """

    def get(self, request):
        tag = request.query_params.get('tag', 'All')
        items = WishlistItem.objects.filter(user=request.user).order_by('-created_at')
        if tag and tag.lower() == 'products':
            items = items.filter(item_type__in=['product', 'wardrobe_item'])
        elif tag and tag.lower() == 'bundles':
            items = items.filter(item_type__in=['bundle', 'marketplace_bundle', 'ai_bundle'])
        return Response([_serialize_wishlist(i) for i in items])

    def post(self, request):
        item_type = _normalize_item_type(request.data.get('item_type'))
        item_id = _extract_wishlist_id(request.data)
        if item_type not in _ITEM_TYPE_ALIASES.values() or not item_id:
            return Response(
                {"detail": "item_type and an item id (item_id, wardrobe_item_id, product_id or bundle_id) are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        stored_type, snapshot = _build_wishlist_snapshot(
            request.user, item_type, item_id, bundle_data=request.data.get('bundle_data')
        )
        if stored_type is None:
            return Response(
                {"detail": f"{item_type} with id {item_id} not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        existing = WishlistItem.objects.filter(
            user=request.user, item_type=stored_type, item_id=item_id
        ).first()
        if existing:
            return Response(_serialize_wishlist(existing), status=status.HTTP_200_OK)

        entry = WishlistItem.objects.create(
            wishlist_id=str(uuid.uuid4()),
            user=request.user,
            item_type=stored_type,
            item_id=item_id,
            item_data=snapshot,
            created_at=datetime.utcnow().isoformat() + 'Z',
        )
        return Response(_serialize_wishlist(entry), status=status.HTTP_201_CREATED)

    def delete(self, request):
        item_type = _normalize_item_type(request.data.get('item_type'))
        item_id = _extract_wishlist_id(request.data)
        if item_type not in _ITEM_TYPE_ALIASES.values() or not item_id:
            return Response(
                {"detail": "item_type and an item id (item_id, wardrobe_item_id, product_id or bundle_id) are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        stored_type, _ = _build_wishlist_snapshot(
            request.user, item_type, item_id, bundle_data=request.data.get('bundle_data')
        )
        if stored_type is None:
            stored_type = item_type
        deleted, _ = WishlistItem.objects.filter(
            user=request.user, item_type=stored_type, item_id=item_id
        ).delete()
        return Response({"removed": bool(deleted)}, status=status.HTTP_200_OK)


import logging

frontend_logger = logging.getLogger('frontend')

class FrontendLogView(APIView):
    """
    POST /api/logs
    Accepts frontend logs and prints/records them in the backend.
    Intentionally public so errors can be logged even when the user is unauthenticated.
    """
    authentication_classes = []
    permission_classes = []

    def post(self, request):
        level = request.data.get('level', 'info').lower()
        message = request.data.get('message', '')
        url = request.data.get('url', '')
        stack = request.data.get('stack', '')
        
        # Configure logger dynamically if no handlers exist
        if not frontend_logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            frontend_logger.addHandler(handler)
        frontend_logger.setLevel(logging.INFO)
        
        log_msg = f"[Frontend {level.upper()}] Url: {url} | Message: {message}"
        if stack:
            log_msg += f"\nStack: {stack}"
            
        if level == 'error':
            frontend_logger.error(log_msg)
        elif level == 'warn':
            frontend_logger.warning(log_msg)
        else:
            frontend_logger.info(log_msg)
            
        return Response({"status": "logged"}, status=status.HTTP_200_OK)


