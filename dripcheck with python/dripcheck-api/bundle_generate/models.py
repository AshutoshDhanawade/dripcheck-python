from django.db import models
from api.models import Category, ColorFamily, Pattern, Fit, OccasionType, Season

class MerchantProduct(models.Model):
    product_id = models.CharField(max_length=255, primary_key=True)
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
    image_url = models.URLField(max_length=1000, null=True, blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    added_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.category})"
