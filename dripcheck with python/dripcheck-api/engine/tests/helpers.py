"""Shared test helpers for the personalization layer tests."""

from __future__ import annotations

import os
from types import SimpleNamespace

# Configure Django before importing any code that touches app models.
# Safe under ``manage.py test`` (setup() is idempotent) and works under a
# bare ``python -m unittest`` run (no database required for these tests).
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dripcheck_django.settings')
import django  # noqa: E402

django.setup()


def make_item(
    item_id: str,
    category: str = 'Top',
    primary_color: str = 'Black',
    color_family: str = 'Neutral',
    pattern: str = 'Solid',
    fit: str = 'Regular',
    season: str = 'All-season',
    formality_level: int = 3,
    occasion: list[str] | None = None,
    style_tags: list[str] | None = None,
    brand: str | None = None,
    material: str = 'Cotton',
    mood_tags: list[str] | None = None,
    subcategory: str = 'T-Shirt',
) -> SimpleNamespace:
    """Build a lightweight item object exposing the attributes the engines use."""
    return SimpleNamespace(
        item_id=item_id,
        name=f"{primary_color} {subcategory}",
        category=category,
        subcategory=subcategory,
        primary_color=primary_color,
        secondary_color=None,
        color_family=color_family,
        pattern=pattern,
        fit=fit,
        occasion_type=occasion or [],
        season=season,
        formality_level=formality_level,
        brand=brand,
        material=material,
        style_tags=style_tags or [],
        mood_tags=mood_tags or [],
        aesthetic_tone=None,
        wear_count=0,
        last_worn=None,
        image_url=None,
    )