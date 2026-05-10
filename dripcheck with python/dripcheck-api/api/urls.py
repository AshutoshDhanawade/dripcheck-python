from django.urls import path
from .views import (
    WardrobeListCreateView,
    WardrobeDetailView,
    UserProfileDetailView,
    AnalyticsView,
    WearLogView,
)
# Bundle & Marketplace views are now served from the converted DRF module
from bundlegeneration import BundleListView, SaveBundleView, MarketplaceView

urlpatterns = [
    # ── Wardrobe ──────────────────────────────────────────────────────────────
    path('wardrobe/<str:user_id>', WardrobeListCreateView.as_view(), name='wardrobe-list-create'),
    path('wardrobe/<str:user_id>/<str:item_id>', WardrobeDetailView.as_view(), name='wardrobe-detail'),

    # ── User Profile ──────────────────────────────────────────────────────────
    path('users/<str:user_id>', UserProfileDetailView.as_view(), name='user-profile'),

    # ── Analytics ─────────────────────────────────────────────────────────────
    path('analytics/<str:user_id>', AnalyticsView.as_view(), name='analytics'),

    # ── Wear Log ──────────────────────────────────────────────────────────────
    path('wearlog/<str:user_id>', WearLogView.as_view(), name='wearlog'),

    # ── Bundle Generation (converted from FastAPI → DRF) ──────────────────────
    path('bundles/<str:user_id>', BundleListView.as_view(), name='bundles'),
    path('bundles/<str:user_id>/save', SaveBundleView.as_view(), name='save-bundle'),

    # ── Marketplace (converted from FastAPI → DRF) ────────────────────────────
    path('marketplace', MarketplaceView.as_view(), name='marketplace'),
]
