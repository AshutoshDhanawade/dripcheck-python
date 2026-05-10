from rest_framework import serializers
from .models import UserProfile, WardrobeItem, OutfitBundle, WearLog, MarketplaceBundle

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
