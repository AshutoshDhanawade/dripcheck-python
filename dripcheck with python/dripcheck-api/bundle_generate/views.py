from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404

from .models import MerchantProduct
from .serializers import MerchantProductSerializer
from api.models import WardrobeItem, UserProfile, Category
from api.serializers import OutfitBundleSerializer
from engine.compatibility_engine import generate_bundles

def map_merchant_to_wardrobe_item(merchant_product):
    return WardrobeItem(
        item_id=merchant_product.product_id,
        user_id="merchant",
        name=merchant_product.name,
        category=merchant_product.category,
        subcategory=merchant_product.subcategory,
        primary_color=merchant_product.primary_color,
        secondary_color=merchant_product.secondary_color,
        color_family=merchant_product.color_family,
        pattern=merchant_product.pattern,
        fit=merchant_product.fit,
        occasion_type=merchant_product.occasion_type,
        season=merchant_product.season,
        formality_level=merchant_product.formality_level,
        brand=merchant_product.brand,
        material=merchant_product.material,
        style_tags=merchant_product.style_tags,
        mood_tags=merchant_product.mood_tags,
        aesthetic_tone=merchant_product.aesthetic_tone,
        image_url=merchant_product.image_url
    )

class HomepageProductsView(APIView):
    """
    GET /api/bundle-generate/homepage/
    Returns all products from the merchant database to be displayed on the homepage.
    """
    def get(self, request):
        category = request.query_params.get('category')
        products = MerchantProduct.objects.all()
        if category:
            products = products.filter(category=category)
            
        serializer = MerchantProductSerializer(products, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

class BestSellingProductsView(APIView):
    """
    GET /api/bundle-generate/homepage/best-selling/
    Returns top N products from the merchant database based on sales count.
    """
    def get(self, request):
        # Return top 10 best-selling products
        products = MerchantProduct.objects.all().order_by('-sales_count')[:10]
        serializer = MerchantProductSerializer(products, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

class GenerateFromProductView(APIView):
    """
    POST /api/bundle-generate/recommend/
    Payload: {"product_id": "..."}
    Generates bundles centering around the selected merchant product.
    Requires a valid JWT; the user is resolved from the token.
    """
    def post(self, request):
        data = request.data
        product_id = data.get('product_id')

        if not product_id:
            return Response({"detail": "product_id is required."}, status=status.HTTP_400_BAD_REQUEST)

        # Get the selected product
        selected_product = get_object_or_404(MerchantProduct, product_id=product_id)
        selected_wardrobe_item = map_merchant_to_wardrobe_item(selected_product)

        # Determine missing categories (Top, Bottom, Footwear)
        required_categories = {Category.TOP, Category.BOTTOM, Category.FOOTWEAR}
        missing_categories = required_categories - {selected_product.category}

        # Fetch candidate products from the missing categories
        candidate_products = MerchantProduct.objects.filter(category__in=missing_categories)
        
        # Convert candidates to WardrobeItems
        candidate_items = [map_merchant_to_wardrobe_item(p) for p in candidate_products]

        # The initial pool for the engine contains ONLY the selected item for its category,
        # ensuring the engine MUST use it to form a valid bundle.
        wardrobe_items = [selected_wardrobe_item] + candidate_items

        # Fetch user preferences from the JWT-authenticated user
        avoided_colors = []
        try:
            user_profile = UserProfile.objects.get(user=request.user)
            avoided_colors = user_profile.avoided_colors or []
        except UserProfile.DoesNotExist:
            pass

        # Generate bundles
        # We pass the authenticated user's uid, since the engine requires a string
        target_user_id = str(request.user.user_uid)
        
        generated_bundles = generate_bundles(
            user_id=target_user_id,
            wardrobe_items=wardrobe_items,
            occasion_filter=None, # Or we could extract it from request if needed
            avoided_colors=avoided_colors
        )

        # Serialize and return
        serializer = OutfitBundleSerializer(generated_bundles, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

class GenerateFromWardrobeItemView(APIView):
    """
    POST /api/bundle-generate/recommend-from-wardrobe/
    Payload: {"item_id": "..."}
    Generates bundles centering around the user's selected wardrobe item, filling the rest from merchant products.
    Requires a valid JWT; the user is resolved from the token.
    """
    def post(self, request):
        data = request.data
        item_id = data.get('item_id')

        if not item_id:
            return Response({"detail": "item_id is required."}, status=status.HTTP_400_BAD_REQUEST)

        # Get the selected wardrobe item (scoped to the JWT-authenticated user)
        selected_wardrobe_item = get_object_or_404(WardrobeItem, item_id=item_id, user=request.user)

        # Determine missing categories (Top, Bottom, Footwear)
        required_categories = {Category.TOP, Category.BOTTOM, Category.FOOTWEAR}
        missing_categories = required_categories - {selected_wardrobe_item.category}

        # Fetch candidate products from the missing categories
        candidate_products = MerchantProduct.objects.filter(category__in=missing_categories)
        
        # Convert candidates to WardrobeItems (in-memory)
        candidate_items = [map_merchant_to_wardrobe_item(p) for p in candidate_products]

        # The initial pool for the engine contains ONLY the selected item for its category,
        # ensuring the engine MUST use it to form a valid bundle.
        wardrobe_items = [selected_wardrobe_item] + candidate_items

        # Fetch user preferences
        avoided_colors = []
        try:
            user_profile = UserProfile.objects.get(user=request.user)
            avoided_colors = user_profile.avoided_colors or []
        except UserProfile.DoesNotExist:
            pass

        # Generate bundles
        generated_bundles = generate_bundles(
            user_id=str(request.user.user_uid),
            wardrobe_items=wardrobe_items,
            occasion_filter=None, 
            avoided_colors=avoided_colors
        )

        # Serialize and return
        serializer = OutfitBundleSerializer(generated_bundles, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

