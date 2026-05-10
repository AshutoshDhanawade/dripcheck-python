from django.urls import path
from .views import HomepageProductsView, GenerateFromProductView

urlpatterns = [
    path('homepage/', HomepageProductsView.as_view(), name='homepage-products'),
    path('recommend/', GenerateFromProductView.as_view(), name='generate-recommendation'),
]
