import random
import uuid
from django.core.management.base import BaseCommand
from bundle_generate.models import MerchantProduct
from api.models import Category, ColorFamily, Pattern, Fit, OccasionType, Season

class Command(BaseCommand):
    help = 'Seed the MerchantProduct database with 100 items per category (Top, Bottom, Footwear)'

    def handle(self, *args, **kwargs):
        self.stdout.write('Clearing existing merchant products...')
        MerchantProduct.objects.all().delete()

        categories = [Category.TOP, Category.BOTTOM, Category.FOOTWEAR]
        
        color_map = {
            ColorFamily.NEUTRAL: ['White', 'Black', 'Grey', 'Beige', 'Ivory', 'Off-White', 'Charcoal'],
            ColorFamily.EARTH: ['Brown', 'Camel', 'Khaki', 'Olive', 'Tan', 'Rust', 'Terracotta'],
            ColorFamily.DARK: ['Navy', 'Dark Green', 'Burgundy', 'Slate', 'Midnight Blue'],
            ColorFamily.BOLD: ['Red', 'Yellow', 'Cobalt Blue', 'Fuchsia', 'Orange', 'Neon Green', 'Purple'],
            ColorFamily.PASTEL: ['Baby Pink', 'Mint', 'Lavender', 'Baby Blue', 'Blush', 'Peach'],
            ColorFamily.WARM: ['Mustard', 'Sage Green', 'Dusty Rose', 'Mauve', 'Warm Beige']
        }

        subcategories = {
            Category.TOP: ['T-Shirt', 'Shirt', 'Sweater', 'Hoodie', 'Polo', 'Tank Top', 'Crop Top'],
            Category.BOTTOM: ['Jeans', 'Chinos', 'Shorts', 'Trousers', 'Skirt', 'Joggers', 'Leggings'],
            Category.FOOTWEAR: ['Sneakers', 'Boots', 'Loafers', 'Oxfords', 'Sandals', 'Running Shoes', 'Heels']
        }

        materials = ['Cotton', 'Polyester', 'Linen', 'Wool', 'Leather', 'Denim', 'Spandex', 'Nylon']
        brands = ['Nike', 'Adidas', 'Zara', 'H&M', 'Gucci', 'Levi\'s', 'Puma', 'Vans', 'Uniqlo', 'Prada']
        style_tags_pool = ['Minimalist', 'Streetwear', 'Sporty', 'Vintage', 'Bohemian', 'Classic', 'Business Casual', 'Y2K', 'Preppy', 'Grunge', 'Monochrome', 'Techwear', 'Cottagecore', 'Bold', 'Layered']
        mood_tags_pool = ['Confident', 'Relaxed', 'Energetic', 'Cozy', 'Professional', 'Edgy', 'Romantic', 'Playful']
        
        count_per_category = 100
        total_created = 0

        for cat in categories:
            for i in range(count_per_category):
                color_family = random.choice([c[0] for c in ColorFamily.choices])
                primary_color = random.choice(color_map[color_family])
                
                # Introduce occasional pattern conflict avoidance by making 70% solid
                pattern = random.choice([Pattern.SOLID] * 7 + [c[0] for c in Pattern.choices if c[0] != Pattern.SOLID])
                
                fit = random.choice([c[0] for c in Fit.choices])
                
                # Pick 1-3 occasions
                occasions = random.sample([c[0] for c in OccasionType.choices], k=random.randint(1, 3))
                
                season = random.choice([c[0] for c in Season.choices])
                formality = random.randint(1, 5)
                
                stags = random.sample(style_tags_pool, k=random.randint(1, 3))
                mtags = random.sample(mood_tags_pool, k=random.randint(1, 2))
                
                subcat = random.choice(subcategories[cat])
                
                MerchantProduct.objects.create(
                    product_id=str(uuid.uuid4()),
                    name=f"Merchant {random.choice(brands)} {primary_color} {subcat}",
                    category=cat,
                    subcategory=subcat,
                    primary_color=primary_color,
                    color_family=color_family,
                    pattern=pattern,
                    fit=fit,
                    occasion_type=occasions,
                    season=season,
                    formality_level=formality,
                    brand=random.choice(brands),
                    material=random.choice(materials),
                    style_tags=stags,
                    mood_tags=mtags,
                    image_url=f"https://example.com/images/{uuid.uuid4().hex[:8]}.jpg",
                    price=round(random.uniform(15.0, 250.0), 2)
                )
                total_created += 1

        self.stdout.write(self.style.SUCCESS(f'Successfully created {total_created} merchant products.'))
