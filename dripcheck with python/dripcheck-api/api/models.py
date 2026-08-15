from django.db import models

class Category(models.TextChoices):
    TOP = 'Top', 'Top'
    BOTTOM = 'Bottom', 'Bottom'
    FOOTWEAR = 'Footwear', 'Footwear'
    LAYER = 'Layer', 'Layer'
    ACCESSORY = 'Accessory', 'Accessory'

class ColorFamily(models.TextChoices):
    NEUTRAL = 'Neutral', 'Neutral'
    EARTH = 'Earth', 'Earth'
    DARK = 'Dark', 'Dark'
    BOLD = 'Bold', 'Bold'
    PASTEL = 'Pastel', 'Pastel'
    WARM = 'Warm', 'Warm'

class Pattern(models.TextChoices):
    SOLID = 'Solid', 'Solid'
    STRIPES = 'Stripes', 'Stripes'
    CHECKS = 'Checks', 'Checks'
    GRAPHIC = 'Graphic', 'Graphic'
    FLORAL = 'Floral', 'Floral'
    ABSTRACT = 'Abstract', 'Abstract'

class Fit(models.TextChoices):
    SLIM = 'Slim', 'Slim'
    REGULAR = 'Regular', 'Regular'
    RELAXED = 'Relaxed', 'Relaxed'
    OVERSIZED = 'Oversized', 'Oversized'
    CROPPED = 'Cropped', 'Cropped'
    BAGGY = 'Baggy', 'Baggy'
    TAPERED = 'Tapered', 'Tapered'

class OccasionType(models.TextChoices):
    CASUAL = 'Casual', 'Casual'
    FORMAL = 'Formal', 'Formal'
    BUSINESS = 'Business', 'Business'
    PARTY = 'Party', 'Party'
    GYM = 'Gym', 'Gym'
    DATE_NIGHT = 'Date Night', 'Date Night'
    WEEKEND = 'Weekend', 'Weekend'

class Season(models.TextChoices):
    SUMMER = 'Summer', 'Summer'
    WINTER = 'Winter', 'Winter'
    MONSOON = 'Monsoon', 'Monsoon'
    ALL_SEASON = 'All-season', 'All-season'

class StyleTag(models.TextChoices):
    MINIMALIST = 'Minimalist', 'Minimalist'
    STREETWEAR = 'Streetwear', 'Streetwear'
    SPORTY = 'Sporty', 'Sporty'
    VINTAGE = 'Vintage', 'Vintage'
    BOHEMIAN = 'Bohemian', 'Bohemian'
    CLASSIC = 'Classic', 'Classic'
    BUSINESS_CASUAL = 'Business Casual', 'Business Casual'
    Y2K = 'Y2K', 'Y2K'
    PREPPY = 'Preppy', 'Preppy'
    GRUNGE = 'Grunge', 'Grunge'
    MONOCHROME = 'Monochrome', 'Monochrome'
    TECHWEAR = 'Techwear', 'Techwear'
    COTTAGECORE = 'Cottagecore', 'Cottagecore'
    BOLD = 'Bold', 'Bold'
    LAYERED = 'Layered', 'Layered'
    DESIGNER = 'Designer', 'Designer'

class UserProfile(models.Model):
    user = models.ForeignKey('accounts.User', on_delete=models.CASCADE, null=True, blank=True)
    username = models.CharField(max_length=255)
    email = models.EmailField()
    skin_tone = models.CharField(max_length=100)
    hair_color = models.CharField(max_length=100)
    body_type = models.CharField(max_length=100)
    daily_routines = models.JSONField(default=list)
    occasion_frequency = models.JSONField(default=dict)
    style_vibes = models.JSONField(default=list)
    favorite_colors = models.JSONField(default=list)
    avoided_colors = models.JSONField(default=list)
    fit_preferences = models.JSONField(default=list)
    material_sensitivity = models.JSONField(default=list)
    pattern_preferences = models.JSONField(default=list)
    onboarding_complete = models.BooleanField(default=False)
    created_at = models.CharField(max_length=100)

class WardrobeItem(models.Model):
    item_id = models.CharField(max_length=255, primary_key=True)
    user = models.ForeignKey('accounts.User', on_delete=models.CASCADE, null=True, blank=True)
    name = models.CharField(max_length=255)
    category = models.CharField(max_length=50, choices=Category.choices)
    subcategory = models.CharField(max_length=100)
    primary_color = models.CharField(max_length=100)
    secondary_color = models.CharField(max_length=100, null=True, blank=True)
    color_family = models.CharField(max_length=50, choices=ColorFamily.choices)
    pattern = models.CharField(max_length=50, choices=Pattern.choices)
    fit = models.CharField(max_length=50, choices=Fit.choices)
    occasion_type = models.JSONField(default=list)
    season = models.CharField(max_length=50, choices=Season.choices)
    formality_level = models.IntegerField()
    brand = models.CharField(max_length=255, null=True, blank=True)
    material = models.CharField(max_length=100, null=True, blank=True)
    style_tags = models.JSONField(null=True, blank=True)
    mood_tags = models.JSONField(null=True, blank=True)
    aesthetic_tone = models.CharField(max_length=255, null=True, blank=True)
    wear_count = models.IntegerField(default=0)
    last_worn = models.CharField(max_length=100, null=True, blank=True)
    image_url = models.CharField(max_length=1000, null=True, blank=True)
    original_image = models.CharField(max_length=1000, null=True, blank=True)
    processed_image = models.CharField(max_length=1000, null=True, blank=True)
    product_url = models.CharField(max_length=2000, null=True, blank=True)
    ai_generated = models.BooleanField(default=False)
    fallback_used = models.BooleanField(default=False)
    added_at = models.CharField(max_length=100)



class OutfitBundle(models.Model):
    bundle_id = models.CharField(max_length=255, primary_key=True)
    user = models.ForeignKey('accounts.User', on_delete=models.CASCADE, null=True, blank=True)
    items = models.JSONField(default=list)
    compatibility_score = models.FloatField()
    dominant_color = models.CharField(max_length=100)
    dominant_palette = models.CharField(max_length=100)
    occasion_tags = models.JSONField(default=list)
    style_tags = models.JSONField(default=list)
    mood_tags = models.JSONField(default=list)
    is_saved = models.BooleanField(default=False)
    wear_count = models.IntegerField(default=0)
    source = models.CharField(max_length=50, choices=[('user_generated', 'User Generated'), ('marketplace_inspiration', 'Marketplace Inspiration')])
    has_missing_item = models.BooleanField(null=True, blank=True)
    created_at = models.CharField(max_length=100)

class WearLog(models.Model):
    log_id = models.CharField(max_length=255, primary_key=True)
    user = models.ForeignKey('accounts.User', on_delete=models.CASCADE, null=True, blank=True)
    bundle_id = models.CharField(max_length=255, null=True, blank=True)
    item_ids = models.JSONField(default=list)
    occasion_tag = models.CharField(max_length=100)
    worn_date = models.CharField(max_length=100)
    notes = models.TextField(null=True, blank=True)

class MarketplaceBundle(models.Model):
    bundle_id = models.CharField(max_length=255, primary_key=True)
    title = models.CharField(max_length=255)
    description = models.TextField()
    items = models.JSONField(default=list)  # list of MarketplaceItem dicts
    total_price = models.FloatField()
    match_percentage = models.FloatField()
    occasion_tags = models.JSONField(default=list)
    style_tags = models.JSONField(default=list)
    source = models.CharField(max_length=50, default='marketplace')

class WishlistItem(models.Model):
    ITEM_TYPE_CHOICES = (
        ('product', 'Product'),
        ('wardrobe_item', 'Wardrobe Item'),
        ('bundle', 'Bundle'),
        ('marketplace_bundle', 'Marketplace Bundle'),
        ('ai_bundle', 'AI Bundle'),
    )

    wishlist_id = models.CharField(max_length=255, primary_key=True)
    user = models.ForeignKey('accounts.User', on_delete=models.CASCADE, null=True, blank=True)
    item_type = models.CharField(max_length=20, choices=ITEM_TYPE_CHOICES)
    item_id = models.CharField(max_length=255)
    item_data = models.JSONField(default=dict, help_text="Snapshot of the liked item at like-time")
    created_at = models.CharField(max_length=100)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'item_type', 'item_id'],
                name='unique_wishlist_item_per_user',
            )
        ]

    def __str__(self):
        return f"{self.item_type}:{self.item_id} ({self.user})"
