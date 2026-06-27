import os
import uuid
import shutil
import logging
from datetime import datetime
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.conf import settings
from .models import WardrobeItem
from .serializers import WardrobeItemSerializer
from services import gemini_service

logger = logging.getLogger(__name__)

# Category Choices mapping to ensure strict DB model compatibility
CATEGORY_MAPPING = {
    'top': 'Top',
    'top wear': 'Top',
    'bottom': 'Bottom',
    'bottom wear': 'Bottom',
    'footwear': 'Footwear',
    'foot wear': 'Footwear',
    'layer': 'Layer',
    'layer wear': 'Layer',
    'accessory': 'Accessory'
}

def clean_category(cat_str: str) -> str:
    cleaned = cat_str.strip().lower()
    return CATEGORY_MAPPING.get(cleaned, 'Top')

class UploadProductView(APIView):
    """
    POST /api/wardrobe/upload-product
    
    Accepts:
      - image: File upload (compulsory)
      - name: String (compulsory)
      - color: String (compulsory)
      - type: String (compulsory)
      - category: String (compulsory)
      - user_id: String (optional, default: user_demo)
      
    Returns a preview payload with original image, enhanced image, and inferred metadata tags.
    """
    def post(self, request):
        image_file = request.FILES.get('image')
        name = request.data.get('name')
        color = request.data.get('color')
        type_str = request.data.get('type')
        category = request.data.get('category')
        user_id = request.data.get('user_id', 'user_demo')
        
        # 1. Input validations
        if not image_file:
            return Response({"success": False, "error": "Product image is required."}, status=status.HTTP_400_BAD_REQUEST)
        if not all([name, color, type_str, category]):
            return Response({"success": False, "error": "Fields: name, color, type, and category are compulsory."}, status=status.HTTP_400_BAD_REQUEST)
            
        # 2. File type validation
        ext = os.path.splitext(image_file.name)[1].lower()
        if ext not in ['.jpg', '.jpeg', '.png', '.webp']:
            return Response({"success": False, "error": "Only JPG, JPEG, PNG, and WEBP image uploads are allowed."}, status=status.HTTP_400_BAD_REQUEST)
            
        # 3. File size validation (Max 5MB)
        if image_file.size > 5 * 1024 * 1024:
            return Response({"success": False, "error": "Image file size exceeds the 5MB limit."}, status=status.HTTP_400_BAD_REQUEST)
            
        # 4. Create temp directory
        temp_dir = os.path.join(settings.MEDIA_ROOT, 'temp')
        os.makedirs(temp_dir, exist_ok=True)
        
        # 5. Save original image temporarily
        temp_id = str(uuid.uuid4())
        orig_filename = f"orig_{temp_id}{ext}"
        orig_path = os.path.join(temp_dir, orig_filename)
        
        try:
            with open(orig_path, 'wb+') as destination:
                for chunk in image_file.chunks():
                    destination.write(chunk)
        except Exception as e:
            logger.error(f"Failed to write temporary upload file: {e}")
            return Response({"success": False, "error": "Failed to save file on server."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
        # Read file bytes for Gemini APIs
        try:
            with open(orig_path, 'rb') as f:
                image_bytes = f.read()
        except Exception as e:
            logger.error(f"Failed to read image bytes: {e}")
            return Response({"success": False, "error": "Failed to process image bytes."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
        # 6. Call Nano Banana (Gemini 2.5 Flash Image)
        fallback_used = False
        processed_filename = f"gen_{temp_id}{ext}"
        processed_path = os.path.join(temp_dir, processed_filename)
        
        try:
            gen_bytes = gemini_service.generate_ecommerce_image(image_bytes)
            with open(processed_path, 'wb') as f:
                f.write(gen_bytes)
            logger.info("Successfully generated e-commerce image via Nano Banana API.")
        except Exception as e:
            # Activate fallback system
            logger.warning(f"Nano Banana image generation failed. Fallback active. Error: {e}")
            fallback_used = True
            shutil.copy(orig_path, processed_path)
            
        # 7. Call Gemini 2.0 Flash to extract metadata
        metadata = {}
        try:
            metadata = gemini_service.extract_product_metadata(image_bytes, name, color, type_str, category)
            logger.info("Successfully extracted product metadata via Gemini.")
        except Exception as e:
            logger.warning(f"Gemini metadata extraction failed. Using local heuristic fallback. Error: {e}")
            metadata = gemini_service.infer_metadata_locally(name, color, type_str, category)
            
        # 8. Build URLs
        original_url = f"{settings.MEDIA_URL}temp/{orig_filename}"
        generated_url = f"{settings.MEDIA_URL}temp/{processed_filename}"
        
        response_data = {
            "success": True,
            "fallback_used": fallback_used,
            "original_image": original_url,
            "generated_image": generated_url,
            "temp_orig_name": orig_filename,
            "temp_gen_name": processed_filename,
            "product": {
                "name": name,
                "color": color,
                "type": type_str,
                "category": category,
                "metadata": metadata
            }
        }
        
        return Response(response_data, status=status.HTTP_200_OK)

class ApproveProductView(APIView):
    """
    POST /api/wardrobe/approve-product
    
    Accepts:
      - approved: Boolean (compulsory)
      - temp_orig_name: String (compulsory)
      - temp_gen_name: String (compulsory)
      - fallback_used: Boolean (optional, default: False)
      - user_id: String (optional, default: user_demo)
      - product: Dict containing product information:
          {
            name: String,
            color: String,
            type: String,
            category: String,
            metadata: Dict
          }
    """
    def post(self, request):
        approved = request.data.get('approved')
        temp_orig_name = request.data.get('temp_orig_name')
        temp_gen_name = request.data.get('temp_gen_name')
        fallback_used = request.data.get('fallback_used', False)
        user_id = request.data.get('user_id', 'user_demo')
        product_data = request.data.get('product', {})
        
        if approved is None or not temp_orig_name or not temp_gen_name:
            return Response({"success": False, "error": "approved, temp_orig_name, and temp_gen_name are required fields."}, status=status.HTTP_400_BAD_REQUEST)
            
        temp_dir = os.path.join(settings.MEDIA_ROOT, 'temp')
        orig_temp_path = os.path.join(temp_dir, temp_orig_name)
        gen_temp_path = os.path.join(temp_dir, temp_gen_name)
        
        # 1. Handle Rejection
        if not approved:
            # Clean up temporary files
            if os.path.exists(orig_temp_path):
                os.remove(orig_temp_path)
            if os.path.exists(gen_temp_path):
                os.remove(gen_temp_path)
            return Response({"success": True, "message": "Product upload rejected. Temporary images cleaned up."}, status=status.HTTP_200_OK)
            
        # 2. Check if temp files exist
        if not os.path.exists(orig_temp_path) or not os.path.exists(gen_temp_path):
            return Response({"success": False, "error": "Temporary files not found. Upload may have expired or been deleted."}, status=status.HTTP_400_BAD_REQUEST)
            
        # 3. Create wardrobe media directory
        wardrobe_dir = os.path.join(settings.MEDIA_ROOT, 'wardrobe')
        os.makedirs(wardrobe_dir, exist_ok=True)
        
        # 4. Move files to permanent storage
        orig_perm_path = os.path.join(wardrobe_dir, temp_orig_name)
        gen_perm_path = os.path.join(wardrobe_dir, temp_gen_name)
        
        try:
            shutil.move(orig_temp_path, orig_perm_path)
            shutil.move(gen_temp_path, gen_perm_path)
        except Exception as e:
            logger.error(f"Failed to save temporary files to permanent storage: {e}")
            return Response({"success": False, "error": "Failed to save files permanently on the server."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
        # 5. Extract product metadata from input payload (or set defaults)
        name = product_data.get('name', 'Wardrobe Item')
        color = product_data.get('color', 'Other')
        type_str = product_data.get('type', 'Clothing')
        category_raw = product_data.get('category', 'Top Wear')
        category = clean_category(category_raw)
        
        metadata = product_data.get('metadata', {})
        
        original_img_url = f"{settings.MEDIA_URL}wardrobe/{temp_orig_name}"
        processed_img_url = f"{settings.MEDIA_URL}wardrobe/{temp_gen_name}"
        
        # 6. Construct DB entry payload
        item_id = str(uuid.uuid4())
        wardrobe_data = {
            "item_id": item_id,
            "user_id": user_id,
            "name": name,
            "category": category,
            "subcategory": type_str,
            "primary_color": color,
            "secondary_color": metadata.get('secondary_color'),
            "color_family": metadata.get('color_family', 'Neutral'),
            "pattern": metadata.get('pattern', 'Solid'),
            "fit": metadata.get('fit', 'Regular'),
            "occasion_type": metadata.get('occasion_type', ['Casual']),
            "season": metadata.get('season', 'All-season'),
            "formality_level": metadata.get('formality_level', 5),
            "brand": metadata.get('brand'),
            "material": metadata.get('material'),
            "style_tags": metadata.get('style_tags', []),
            "mood_tags": metadata.get('mood_tags', []),
            "aesthetic_tone": metadata.get('aesthetic_tone', ''),
            "image_url": processed_img_url,  # The main image url references the processed one
            "original_image": original_img_url,
            "processed_image": processed_img_url,
            "ai_generated": not fallback_used,
            "fallback_used": fallback_used,
            "added_at": datetime.utcnow().isoformat() + 'Z',
            "wear_count": 0
        }
        
        # 7. Save to DB using Serializer
        serializer = WardrobeItemSerializer(data=wardrobe_data)
        if serializer.is_valid():
            serializer.save()
            return Response({
                "success": True, 
                "message": "Product successfully added to wardrobe.",
                "product": serializer.data
            }, status=status.HTTP_201_CREATED)
            
        # If serialization failed, clean up the moved files to prevent orphan image files
        try:
            if os.path.exists(orig_perm_path): os.remove(orig_perm_path)
            if os.path.exists(gen_perm_path): os.remove(gen_perm_path)
        except:
            pass
            
        logger.error(f"Serialization failed for WardrobeItem: {serializer.errors}")
        return Response({"success": False, "error": "Database validation failed.", "details": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
