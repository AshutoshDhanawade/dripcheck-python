from rest_framework import serializers
from .models import UserProfile, WardrobeItem, OutfitBundle, WearLog, MarketplaceBundle, Wishlist
from bundle_generate.serializers import MerchantProductSerializer

class UserProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserProfile
        fields = '__all__'

class WardrobeItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = WardrobeItem
        fields = '__all__'

class OutfitBundleSerializer(serializers.ModelSerializer):
    class Meta:
        model = OutfitBundle
        fields = '__all__'

class WearLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = WearLog
        fields = '__all__'

class MarketplaceBundleSerializer(serializers.ModelSerializer):
    class Meta:
        model = MarketplaceBundle
        fields = '__all__'

class WishlistSerializer(serializers.ModelSerializer):
    product = MerchantProductSerializer(read_only=True)
    wardrobe_item = WardrobeItemSerializer(read_only=True)
    bundle = OutfitBundleSerializer(read_only=True)
    marketplace_bundle = MarketplaceBundleSerializer(read_only=True)

    class Meta:
        model = Wishlist
        fields = ['id', 'item_type', 'product', 'wardrobe_item', 'bundle', 'marketplace_bundle', 'ai_bundle_id', 'bundle_data', 'added_at']
