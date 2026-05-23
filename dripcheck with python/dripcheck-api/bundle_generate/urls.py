from django.urls import path
from .views import HomepageProductsView, GenerateFromProductView, BestSellingProductsView, GenerateFromWardrobeItemView

urlpatterns = [
    path('homepage/', HomepageProductsView.as_view(), name='homepage-products'),
    path('homepage/best-selling/', BestSellingProductsView.as_view(), name='best-selling-products'),
    path('recommend/', GenerateFromProductView.as_view(), name='generate-recommendation'),
    path('recommend-from-wardrobe/', GenerateFromWardrobeItemView.as_view(), name='generate-from-wardrobe'),
]
