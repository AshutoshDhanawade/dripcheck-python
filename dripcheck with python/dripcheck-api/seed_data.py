import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dripcheck_django.settings')
django.setup()

from api.models import WardrobeItem as DjangoWardrobeItem, UserProfile as DjangoUserProfile, OutfitBundle as DjangoOutfitBundle, MarketplaceBundle as DjangoMarketplaceBundle
from data.mock_wardrobe import mock_wardrobe_items
from data.mock_users import mock_users
from data.mock_bundles import mock_pre_generated_bundles
from data.mock_marketplace import mock_marketplace_bundles

def seed():
    for u in mock_users:
        data = u.dict()
        DjangoUserProfile.objects.create(**data)
        
    for w in mock_wardrobe_items:
        data = w.dict()
        # Some Pydantic enums need their string value
        if hasattr(data['category'], 'value'): data['category'] = data['category'].value
        if hasattr(data['color_family'], 'value'): data['color_family'] = data['color_family'].value
        if hasattr(data['pattern'], 'value'): data['pattern'] = data['pattern'].value
        if hasattr(data['fit'], 'value'): data['fit'] = data['fit'].value
        if hasattr(data['season'], 'value'): data['season'] = data['season'].value
        data['occasion_type'] = [o.value if hasattr(o, 'value') else str(o) for o in data['occasion_type']]
        DjangoWardrobeItem.objects.create(**data)
        
    for b in mock_pre_generated_bundles:
        data = b.dict()
        DjangoOutfitBundle.objects.create(**data)
        
    for mb in mock_marketplace_bundles:
        data = mb.dict()
        # the items in MarketplaceBundle are objects
        data['items'] = [i.dict() for i in data.get('items', [])]
        DjangoMarketplaceBundle.objects.create(**data)
        
    print("Seed complete!")

if __name__ == '__main__':
    seed()
