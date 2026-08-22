from rest_framework import serializers
from .models import UserProfile, WardrobeItem, OutfitBundle, WearLog, MarketplaceBundle, WishlistItem

class UserProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserProfile
        fields = '__all__'

class WardrobeItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = WardrobeItem
        fields = '__all__'

class OutfitBundleSerializer(serializers.ModelSerializer):
    # Scoring breakdown (debug/observability). These are attached to bundle
    # objects by RecommendationEngine.recommend() and by the /api/bundles/ view
    # (which scores stored bundles the same way). Stored bundles that were never
    # scored serialize them as null. All values are the backend's real scoring
    # values — the serializer never computes them.
    personalization_score = serializers.SerializerMethodField()
    ranking_score = serializers.SerializerMethodField()
    # Diversity penalty: always a POSITIVE number of points to subtract (the
    # UI renders it with a minus sign). None when no diversity metadata exists.
    diversity_penalty = serializers.SerializerMethodField()
    diversity_breakdown = serializers.SerializerMethodField()

    class Meta:
        model = OutfitBundle
        fields = '__all__'

    def get_personalization_score(self, obj):
        return getattr(obj, 'personalization_score', None)

    def get_ranking_score(self, obj):
        return getattr(obj, 'ranking_score', None)

    def get_diversity_penalty(self, obj):
        return getattr(obj, 'diversity_penalty', None)

    def get_diversity_breakdown(self, obj):
        return getattr(obj, 'diversity_breakdown', None)

class WearLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = WearLog
        fields = '__all__'

class MarketplaceBundleSerializer(serializers.ModelSerializer):
    class Meta:
        model = MarketplaceBundle
        fields = '__all__'

class WishlistItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = WishlistItem
        fields = '__all__'
