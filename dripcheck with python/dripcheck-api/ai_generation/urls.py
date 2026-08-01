from django.urls import path

from .views import (
    TopwearSuggestionView,
    BottomwearSuggestionView,
    FootwearSuggestionView,
)

urlpatterns = [
    path('topwear-suggestion/', TopwearSuggestionView.as_view(), name='topwear-suggestion'),
    path('bottomwear-suggestion/', BottomwearSuggestionView.as_view(), name='bottomwear-suggestion'),
    path('footwear-suggestion/', FootwearSuggestionView.as_view(), name='footwear-suggestion'),
]
