from django.contrib import admin
from .models import MerchantProduct, FootwearAiRecommendation, BottomwearAiGeneration, TopwearAiRecommendation

@admin.register(MerchantProduct)
class MerchantProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'brand', 'price', 'sales_count')
    list_filter = ('category', 'brand')
    search_fields = ('name', 'brand')

@admin.register(FootwearAiRecommendation)
class FootwearAiRecommendationAdmin(admin.ModelAdmin):
    list_display = ('name', 'subcategory', 'primary_color', 'brand')
    list_filter = ('subcategory', 'color_family')
    search_fields = ('name', 'brand')

@admin.register(BottomwearAiGeneration)
class BottomwearAiGenerationAdmin(admin.ModelAdmin):
    list_display = ('name', 'subcategory', 'primary_color', 'brand')
    list_filter = ('subcategory', 'color_family')
    search_fields = ('name', 'brand')

@admin.register(TopwearAiRecommendation)
class TopwearAiRecommendationAdmin(admin.ModelAdmin):
    list_display = ('name', 'subcategory', 'primary_color', 'brand')
    list_filter = ('subcategory', 'color_family')
    search_fields = ('name', 'brand')
