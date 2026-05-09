from models.types import MarketplaceBundle, MarketplaceItem

mock_marketplace_bundles = [
    MarketplaceBundle(
        bundle_id='MKT-001',
        title='Casual Starter Pack',
        description='The perfect everyday basics that go with everything.',
        items=[
            MarketplaceItem(name='Essential White Tee', brand='Basics', price=12.99, category='Top', image_url='https://images.unsplash.com/photo-1521572163474-6864f9cf17ab?w=400&q=80'),
            MarketplaceItem(name='Classic Blue Denim', brand='DenimCo', price=29.99, category='Bottom', image_url='https://images.unsplash.com/photo-1542272454315-4c01d7abdf4a?w=400&q=80'),
            MarketplaceItem(name='White Canvas Sneakers', brand='StepStart', price=19.99, category='Footwear', image_url='https://images.unsplash.com/photo-1460353581641-37baddab0fa2?w=400&q=80')
        ],
        total_price=62.97,
        match_percentage=95,
        occasion_tags=['Casual', 'Weekend'],
        style_tags=['Minimalist', 'Classic'],
        source='marketplace'
    ),
    MarketplaceBundle(
        bundle_id='MKT-002',
        title='Business Essentials',
        description='Sharp, professional outfits for the modern workplace.',
        items=[
            MarketplaceItem(name='Oxford Button-Down', brand='Executive', price=24.99, category='Top', image_url='https://images.unsplash.com/photo-1596755094514-f87e34085b2c?w=400&q=80'),
            MarketplaceItem(name='Tailored Navy Chinos', brand='Executive', price=29.99, category='Bottom', image_url='https://images.unsplash.com/photo-1624378439575-d8705ad7ae80?w=400&q=80'),
            MarketplaceItem(name='Brown Leather Oxfords', brand='StepStart', price=39.99, category='Footwear', image_url='https://images.unsplash.com/photo-1614252339460-e1f409559c55?w=400&q=80')
        ],
        total_price=94.97,
        match_percentage=98,
        occasion_tags=['Business', 'Formal'],
        style_tags=['Business Casual', 'Classic'],
        source='marketplace'
    )
]
