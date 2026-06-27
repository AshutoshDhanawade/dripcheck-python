import urllib.request
import json
import base64
import ssl
import logging
from django.conf import settings

logger = logging.getLogger(__name__)

# Use SSL context that tolerates certificate errors in development if any
ssl_context = ssl.create_default_context()
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_NONE

def generate_ecommerce_image(image_bytes: bytes) -> bytes:
    """
    Sends the input product image to the Gemini 2.5 Flash Image model (Nano Banana)
    with custom system instructions to remove the background, clean the image, 
    and format it as a professional e-commerce product listing shot.
    """
    api_key = getattr(settings, 'GEMINI_API_KEY', None)
    if not api_key:
        raise ValueError("GEMINI_API_KEY is not configured in settings.")
        
    model_name = "gemini-2.5-flash-image"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
    
    image_b64 = base64.b64encode(image_bytes).decode('utf-8')
    
    prompt = (
        "Generate a professional e-commerce style product image of the clothing item shown in the input image. "
        "Follow these rules exactly:\n"
        "- Preserve the exact clothing product from the input image (design, cut, graphics, patterns).\n"
        "- Preserve the original colors of the product.\n"
        "- Preserve all logos, branding, and details.\n"
        "- Preserve the texture and fit of the clothing.\n"
        "- Remove the messy, dark, or distracting background.\n"
        "- Replace the background with a clean, solid, pure white or minimal studio background.\n"
        "- Improve the lighting naturally to show the clothing clearly.\n"
        "- Center the product professionally in the frame.\n"
        "- The output must look like a high-quality product photo on Myntra, Amazon, or Flipkart.\n"
        "- Do NOT redesign the clothing or hallucinate extra accessories.\n"
        "- Keep the output realistic, high-fidelity, and maintain the same product identity."
    )
    
    payload = {
        "contents": [
            {
                "parts": [
                    {"text": prompt},
                    {
                        "inlineData": {
                            "mimeType": "image/png",
                            "data": image_b64
                        }
                    }
                ]
            }
        ],
        "generationConfig": {
            "responseModalities": ["IMAGE"]
        }
    }
    
    req_body = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(
        url,
        data=req_body,
        headers={'Content-Type': 'application/json'}
    )
    
    try:
        logger.info(f"Invoking {model_name} Nano Banana image generation...")
        # 15s timeout for fast UI response
        with urllib.request.urlopen(req, context=ssl_context, timeout=15) as response:
            res_data = json.loads(response.read().decode('utf-8'))
            candidates = res_data.get("candidates", [])
            if not candidates:
                raise Exception("No generation candidates returned from Gemini image API.")
                
            parts = candidates[0].get("content", {}).get("parts", [])
            for part in parts:
                if "inlineData" in part:
                    img_data_b64 = part["inlineData"].get("data", "")
                    if img_data_b64:
                        return base64.b64decode(img_data_b64)
            raise Exception("No image bytes found in Gemini image API response parts.")
    except Exception as e:
        logger.error(f"Gemini image generation failed: {e}")
        # If possible, log details
        if hasattr(e, 'read'):
            try:
                logger.error(f"Detail: {e.read().decode('utf-8')}")
            except:
                pass
        raise e

def extract_product_metadata(image_bytes: bytes, name: str, color: str, type_str: str, category: str) -> dict:
    """
    Calls Gemini 2.0 Flash to extract additional rich metadata details about the clothing item.
    """
    api_key = getattr(settings, 'GEMINI_API_KEY', None)
    if not api_key:
        raise ValueError("GEMINI_API_KEY is not configured in settings.")
        
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
    
    image_b64 = base64.b64encode(image_bytes).decode('utf-8')
    
    prompt = (
        f"Analyze this image of a clothing item with the following base fields:\n"
        f"Name: {name}\n"
        f"Color: {color}\n"
        f"Type: {type_str}\n"
        f"Category: {category}\n\n"
        "Return a JSON object containing the following keys (fill in matching values from the image and details):\n"
        "1. secondary_color: string (a secondary color present, or null if solid color)\n"
        "2. color_family: string (one of: 'Neutral', 'Earth', 'Dark', 'Bold', 'Pastel', 'Warm')\n"
        "3. pattern: string (one of: 'Solid', 'Stripes', 'Checks', 'Graphic', 'Floral', 'Abstract')\n"
        "4. fit: string (one of: 'Slim', 'Regular', 'Relaxed', 'Oversized', 'Cropped', 'Baggy', 'Tapered')\n"
        "5. occasion_type: array of strings (one or more of: 'Casual', 'Formal', 'Business', 'Party', 'Gym', 'Date Night', 'Weekend')\n"
        "6. season: string (one of: 'Summer', 'Winter', 'Monsoon', 'All-season')\n"
        "7. formality_level: integer from 1 (very casual) to 10 (extremely formal)\n"
        "8. brand: string or null (detect visible brand names/logos, or null)\n"
        "9. material: string or null (inferred material like Cotton, Denim, Linen, Polyester, Wool, Leather)\n"
        "10. style_tags: array of strings (select from: 'Minimalist', 'Streetwear', 'Sporty', 'Vintage', 'Bohemian', 'Classic', 'Business Casual', 'Y2K', 'Preppy', 'Grunge', 'Monochrome', 'Techwear', 'Cottagecore', 'Bold', 'Layered', 'Designer')\n"
        "11. mood_tags: array of 2-3 mood strings (e.g., ['Relaxed', 'Confident'])\n"
        "12. aesthetic_tone: string (e.g., 'Sleek and modern', 'Vibrant streetwear')\n\n"
        "Return ONLY a valid JSON object without markdown code blocks."
    )
    
    payload = {
        "contents": [
            {
                "parts": [
                    {"text": prompt},
                    {
                        "inlineData": {
                            "mimeType": "image/png",
                            "data": image_b64
                        }
                    }
                ]
            }
        ],
        "generationConfig": {
            "responseMimeType": "application/json"
        }
    }
    
    req_body = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(
        url,
        data=req_body,
        headers={'Content-Type': 'application/json'}
    )
    
    try:
        logger.info("Invoking Gemini 2.0 Flash metadata extraction...")
        # 8s timeout for analysis
        with urllib.request.urlopen(req, context=ssl_context, timeout=8) as response:
            res_data = json.loads(response.read().decode('utf-8'))
            text_out = res_data["candidates"][0]["content"]["parts"][0]["text"].strip()
            # Clean possible markdown wrapping if any
            if text_out.startswith("```json"):
                text_out = text_out[7:]
            if text_out.endswith("```"):
                text_out = text_out[:-3]
            text_out = text_out.strip()
            return json.loads(text_out)
    except Exception as e:
        logger.error(f"Gemini metadata extraction failed: {e}")
        # Re-raise to trigger local fallback mapping
        raise e

def infer_metadata_locally(name: str, color: str, type_str: str, category: str) -> dict:
    """
    Fallback method to infer metadata programmatically using standard rules if Gemini API fails.
    """
    logger.info("Executing local metadata inference fallback engine...")
    
    # 1. Color family heuristics
    color_lower = color.lower()
    color_family = 'Bold'
    if any(c in color_lower for c in ['black', 'navy', 'charcoal', 'dark grey', 'dark gray', 'slate', 'indigo']):
        color_family = 'Dark'
    elif any(c in color_lower for c in ['white', 'grey', 'gray', 'beige', 'cream', 'off-white', 'sand']):
        color_family = 'Neutral'
    elif any(c in color_lower for c in ['brown', 'khaki', 'olive', 'tan', 'terracotta', 'rust', 'sage', 'earth']):
        color_family = 'Earth'
    elif any(c in color_lower for c in ['pink', 'lavender', 'mint', 'peach', 'baby blue', 'pastel']):
        color_family = 'Pastel'
    elif any(c in color_lower for c in ['red', 'yellow', 'orange', 'gold', 'amber']):
        color_family = 'Warm'
    
    # 2. Category parsing
    cat_lower = category.lower()
    inferred_category = 'Top'
    if 'bottom' in cat_lower or 'pant' in cat_lower or 'jeans' in cat_lower or 'trouser' in cat_lower or 'shorts' in cat_lower:
        inferred_category = 'Bottom'
    elif 'foot' in cat_lower or 'shoe' in cat_lower or 'sneaker' in cat_lower or 'boot' in cat_lower or 'sandal' in cat_lower:
        inferred_category = 'Footwear'
    elif 'layer' in cat_lower or 'jacket' in cat_lower or 'coat' in cat_lower or 'shrug' in cat_lower or 'blazer' in cat_lower or 'hoodie' in cat_lower:
        inferred_category = 'Layer'
    elif 'accessory' in cat_lower or 'bag' in cat_lower or 'belt' in cat_lower or 'cap' in cat_lower or 'watch' in cat_lower:
        inferred_category = 'Accessory'
        
    # 3. Fit heuristics
    type_lower = type_str.lower()
    fit = 'Regular'
    if 'oversized' in type_lower or 'loose' in type_lower or 'baggy' in type_lower or 'boxy' in type_lower:
        fit = 'Oversized'
    elif 'slim' in type_lower or 'skinny' in type_lower or 'fitted' in type_lower:
        fit = 'Slim'
    elif 'relaxed' in type_lower:
        fit = 'Relaxed'
    elif 'cropped' in type_lower:
        fit = 'Cropped'
        
    # 4. Formality and Occasions
    formality = 3
    occasions = ['Casual', 'Weekend']
    style_tags = ['Minimalist', 'Classic']
    mood_tags = ['Comfy', 'Relaxed']
    material = 'Cotton'
    
    if 'formal' in type_lower or 'suit' in type_lower or 'blazer' in type_lower or 'tuxedo' in type_lower:
        formality = 9
        occasions = ['Formal', 'Business']
        style_tags = ['Classic', 'Business Casual']
        mood_tags = ['Elegant', 'Confident']
        material = 'Wool Blend'
    elif 'shirt' in type_lower or 'polo' in type_lower:
        formality = 5
        occasions = ['Casual', 'Business', 'Date Night']
        style_tags = ['Classic', 'Business Casual']
        mood_tags = ['Smart', 'Sharp']
    elif 'jeans' in type_lower or 'denim' in type_lower:
        formality = 4
        occasions = ['Casual', 'Weekend', 'Date Night']
        style_tags = ['Streetwear', 'Vintage']
        mood_tags = ['Casual', 'Rugged']
        material = 'Denim'
    elif 'gym' in type_lower or 'sport' in type_lower or 'running' in type_lower or 'track' in type_lower or 'jogger' in type_lower:
        formality = 1
        occasions = ['Gym', 'Weekend']
        style_tags = ['Sporty', 'Techwear']
        mood_tags = ['Active', 'Energetic']
        material = 'Polyester'
    elif 'hoodie' in type_lower or 'sweatshirt' in type_lower:
        formality = 2
        occasions = ['Casual', 'Weekend']
        style_tags = ['Streetwear', 'Grunge']
        mood_tags = ['Cozy', 'Relaxed']
        material = 'Fleece'
        
    # 5. Season heuristics
    season = 'All-season'
    if any(w in type_lower or w in name.lower() for w in ['sweater', 'jacket', 'coat', 'wool', 'fleece', 'winter', 'thermal', 'beanie']):
        season = 'Winter'
    elif any(w in type_lower or w in name.lower() for w in ['shorts', 'sandal', 'tank', 'summer', 'swim', 'linen']):
        season = 'Summer'
    elif any(w in type_lower or w in name.lower() for w in ['rain', 'waterproof', 'windbreaker']):
        season = 'Monsoon'

    return {
        "secondary_color": None,
        "color_family": color_family,
        "pattern": "Solid",
        "fit": fit,
        "occasion_type": occasions,
        "season": season,
        "formality_level": formality,
        "brand": None,
        "material": material,
        "style_tags": style_tags,
        "mood_tags": mood_tags,
        "aesthetic_tone": f"Clean {color_family} {type_str}"
    }
