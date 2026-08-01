import csv
import json
from django.core.management.base import BaseCommand
from bundle_generate.models import TopwearAiRecommendation


class Command(BaseCommand):
    help = 'Import topwear AI recommendations from CSV file'

    def add_arguments(self, parser):
        parser.add_argument('csv_path', type=str, help='Path to the CSV file')

    def handle(self, *args, **kwargs):
        csv_path = kwargs['csv_path']

        self.stdout.write('Clearing existing topwear AI recommendations...')
        TopwearAiRecommendation.objects.all().delete()

        batch = []
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                batch.append(TopwearAiRecommendation(
                    item_id=row['item_id'],
                    name=row['name'],
                    category=row['category'],
                    subcategory=row['subcategory'],
                    primary_color=row.get('primary_color', '') or '',
                    secondary_color=row.get('secondary_color', '') or '',
                    color_family=row.get('color_family', '') or '',
                    pattern=row['pattern'],
                    fit=row['fit'],
                    occasion_type=json.loads(row['occasion_type']),
                    season=row['season'],
                    formality_level=int(row['formality_level']),
                    brand=row.get('brand', '') or '',
                    material=row.get('material', '') or '',
                    style_tags=json.loads(row['style_tags']) if row.get('style_tags') else [],
                    mood_tags=json.loads(row['mood_tags']) if row.get('mood_tags') else [],
                    aesthetic_tone=row.get('aesthetic_tone', '') or '',
                    wear_count=int(row.get('wear_count', 0)),
                    last_worn=row.get('last_worn', '') or '',
                    image_url=row.get('image_url', '') or '',
                    original_image=row.get('original_image', '') or '',
                    processed_image=row.get('processed_image', '') or '',
                    product_url=row.get('product_url', '') or '',
                    ai_generated=row.get('ai_generated', 'false').lower() == 'true',
                    fallback_used=row.get('fallback_used', 'false').lower() == 'true',
                    added_at=row.get('added_at', ''),
                    user_id=int(row.get('user_id', 0)),
                ))

        TopwearAiRecommendation.objects.bulk_create(batch, batch_size=500)
        self.stdout.write(self.style.SUCCESS(f'Successfully imported {len(batch)} topwear AI recommendations.'))
