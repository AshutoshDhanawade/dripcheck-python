import os

file_path = r'c:\Users\acer\Desktop\Dripcheck-python\dripcheck-python\dripcheck with python\dripcheck-api\engine\compatibility_engine.py'
with open(file_path, 'r') as f:
    content = f.read()

content = content.replace('from models.types import WardrobeItem, ColorFamily, OccasionType, Category, OutfitBundle', 'from api.models import WardrobeItem, ColorFamily, OccasionType, Category, OutfitBundle')
content = content.replace('.value', '')

with open(file_path, 'w') as f:
    f.write(content)
print("Updated compatibility_engine.py")
