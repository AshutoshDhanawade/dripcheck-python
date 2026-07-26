from django.urls import path
from .views import (
    WardrobeListCreateView,
    WardrobeDetailView,
    UserProfileDetailView,
    AnalyticsView,
    WearLogView,
    FrontendLogView,
)
from .views_upload import AddProductLinkView, UploadProductView, ApproveProductView
from .views_avatar import GenerateAvatarView
# Bundle & Marketplace views are now served from the converted DRF module
from bundlegeneration import BundleListView, SaveBundleView, MarketplaceView

urlpatterns = [
    # ── Wardrobe ──────────────────────────────────────────────────────────────
    path('wardrobe/upload-product', UploadProductView.as_view(), name='wardrobe-upload-product'),
    path('wardrobe/add-product-link', AddProductLinkView.as_view(), name='wardrobe-add-product-link'),
    path('wardrobe/approve-product', ApproveProductView.as_view(), name='wardrobe-approve-product'),
    path('wardrobe/generate-avatar', GenerateAvatarView.as_view(), name='wardrobe-generate-avatar'),
    path('wardrobe/<uuid:user_id>', WardrobeListCreateView.as_view(), name='wardrobe-list-create'),

    path('wardrobe/<uuid:user_id>/<str:item_id>', WardrobeDetailView.as_view(), name='wardrobe-detail'),

    # ── User Profile ──────────────────────────────────────────────────────────
    path('users/<uuid:user_id>', UserProfileDetailView.as_view(), name='user-profile'),

    # ── Analytics ─────────────────────────────────────────────────────────────
    path('analytics/<uuid:user_id>', AnalyticsView.as_view(), name='analytics'),

    # ── Wear Log ──────────────────────────────────────────────────────────────
    path('wearlog/<uuid:user_id>', WearLogView.as_view(), name='wearlog'),

    # ── Bundle Generation (converted from FastAPI → DRF) ──────────────────────
    path('bundles/<uuid:user_id>', BundleListView.as_view(), name='bundles'),
    path('bundles/<uuid:user_id>/save', SaveBundleView.as_view(), name='save-bundle'),

    # ── Marketplace (converted from FastAPI → DRF) ────────────────────────────
    path('marketplace', MarketplaceView.as_view(), name='marketplace'),

    # ── Frontend Logs ─────────────────────────────────────────────────────────
    path('logs', FrontendLogView.as_view(), name='frontend-logs'),
]
