import uuid
from datetime import datetime
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from .models import WardrobeItem, UserProfile, WearLog, OutfitBundle, MarketplaceBundle
from .serializers import WardrobeItemSerializer, UserProfileSerializer, WearLogSerializer, OutfitBundleSerializer, MarketplaceBundleSerializer

class WardrobeListCreateView(APIView):
    def get(self, request, user_id):
        items = WardrobeItem.objects.filter(user_id=user_id)
        serializer = WardrobeItemSerializer(items, many=True)
        return Response(serializer.data)

    def post(self, request, user_id):
        data = request.data.copy()
        data['item_id'] = str(uuid.uuid4())
        data['user_id'] = user_id
        data['added_at'] = datetime.utcnow().isoformat() + 'Z'
        data['wear_count'] = 0
        serializer = WardrobeItemSerializer(data=data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class WardrobeDetailView(APIView):
    def put(self, request, user_id, item_id):
        item = get_object_or_404(WardrobeItem, user_id=user_id, item_id=item_id)
        serializer = WardrobeItemSerializer(item, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, user_id, item_id):
        item = get_object_or_404(WardrobeItem, user_id=user_id, item_id=item_id)
        item.delete()
        OutfitBundle.objects.filter(user_id=user_id, items__contains=item_id).update(has_missing_item=True)
        return Response({"status": "success"}, status=status.HTTP_204_NO_CONTENT)

class UserProfileDetailView(APIView):
    def get(self, request, user_id):
        user = get_object_or_404(UserProfile, user_id=user_id)
        serializer = UserProfileSerializer(user)
        return Response(serializer.data)

    def put(self, request, user_id):
        user, created = UserProfile.objects.get_or_create(user_id=user_id, defaults=request.data)
        if not created:
            serializer = UserProfileSerializer(user, data=request.data, partial=True)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        serializer = UserProfileSerializer(user)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

class AnalyticsView(APIView):
    def get(self, request, user_id):
        user_wardrobe = WardrobeItem.objects.filter(user_id=user_id)
        total_items = user_wardrobe.count()
        never_worn_count = user_wardrobe.filter(wear_count=0).count()
        
        most_worn_item = user_wardrobe.order_by('-wear_count').first()
        most_worn_item_data = WardrobeItemSerializer(most_worn_item).data if most_worn_item else None
        
        utilization_percentage = ((total_items - never_worn_count) / total_items * 100) if total_items > 0 else 0
        
        saved_bundles = OutfitBundle.objects.filter(user_id=user_id, is_saved=True)
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
    def get(self, request, user_id):
        logs = WearLog.objects.filter(user_id=user_id)
        serializer = WearLogSerializer(logs, many=True)
        return Response(serializer.data)

    def post(self, request, user_id):
        data = request.data
        bundle_id = data.get("bundle_id")
        date = data.get("worn_date")
        occasion = data.get("occasion_tag")
        
        if not date or not occasion:
            return Response({"detail": "Missing worn_date or occasion_tag"}, status=status.HTTP_400_BAD_REQUEST)
            
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
                item = WardrobeItem.objects.get(item_id=item_id, user_id=user_id)
                item.wear_count += 1
                item.last_worn = date
                item.save()
            except WardrobeItem.DoesNotExist:
                pass
                
        log_data = {
            "log_id": str(uuid.uuid4()),
            "user_id": user_id,
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


import logging

frontend_logger = logging.getLogger('frontend')

class FrontendLogView(APIView):
    """
    POST /api/logs
    Accepts frontend logs and prints/records them in the backend.
    """
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


