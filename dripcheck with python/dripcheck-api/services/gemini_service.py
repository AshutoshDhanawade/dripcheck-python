import io
import re
import urllib.request
import json
import base64
import ssl
import logging
from django.conf import settings

from PIL import Image

from services.occasion_taxonomy import ALL_OCCASIONS

logger = logging.getLogger(__name__)

# Use SSL context that tolerates certificate errors in development if any
ssl_context = ssl.create_default_context()
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_NONE

# Fallback vision model when settings.GEMINI_VISION_MODEL is not configured.
# gemini-2.0-flash was retired by Google (404 "no longer available"); the
# endpoint recommends gemini-3.6-flash for this project's API key.
GEMINI_VISION_MODEL = 'gemini-3.6-flash'
GEMINI_IMAGE_MODEL = 'gemini-2.5-flash-image'


def _get_vision_model():
    return getattr(settings, 'GEMINI_VISION_MODEL', None) or GEMINI_VISION_MODEL

VISION_TIMEOUT_SECONDS = 20
LEGACY_VISION_TIMEOUT_SECONDS = 8

CATEGORY_CHOICES = ['Top', 'Bottom', 'Footwear', 'Layer', 'Accessory']
COLOR_FAMILY_CHOICES = ['Neutral', 'Earth', 'Dark', 'Bold', 'Pastel', 'Warm']
PATTERN_CHOICES = ['Solid', 'Stripes', 'Checks', 'Graphic', 'Floral', 'Abstract']
FIT_CHOICES = ['Slim', 'Regular', 'Relaxed', 'Oversized', 'Cropped', 'Baggy', 'Tapered']
# Canonical occasion vocabulary: every parent and child of the hierarchical
# occasion taxonomy (services/occasion_taxonomy.py — the single source of
# truth). Kept flat here so the model can pick candidates without building
# the hierarchy itself.
OCCASION_CHOICES = list(ALL_OCCASIONS)
SEASON_CHOICES = ['Summer', 'Winter', 'Monsoon', 'All-season']
STYLE_TAG_CHOICES = [
    'Minimalist', 'Streetwear', 'Sporty', 'Vintage', 'Bohemian', 'Classic',
    'Business Casual', 'Y2K', 'Preppy', 'Grunge', 'Monochrome', 'Techwear',
    'Cottagecore', 'Bold', 'Layered', 'Designer',
]

# OpenAPI-style response schema for structured Gemini vision output.
# Mirrors the WardrobeItem vocabulary (see api/models.py) and adds internal
# fields (garment_type, sleeve, confidence) that are not persisted.
VISION_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "garment_type": {"type": "string", "description": "Plain garment type, e.g. shirt, jeans, jacket"},
        "category": {"type": "string", "enum": CATEGORY_CHOICES},
        "subcategory": {"type": "string"},
        "primary_color": {"type": "string"},
        "secondary_colors": {"type": "array", "items": {"type": "string"}},
        "pattern": {"type": "string", "enum": PATTERN_CHOICES},
        "fit": {"type": "string", "enum": FIT_CHOICES},
        "material": {"type": "string", "description": "Fabric composition, e.g. Cotton or Linen/Cotton, or null when unknown"},
        "sleeve": {"type": "string", "description": "Sleeve length seen on the garment, e.g. Short Sleeve, Long Sleeve, Sleeveless"},
        "occasion_candidates": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "tag": {
                        "type": "string",
                        "description": "Occasion tag (e.g. Business, Wedding, Gym). Pick only from the occasion list provided in the prompt; do not invent new occasions.",
                    },
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                },
                "required": ["tag", "confidence"],
            },
            "description": "0-5 plausible occasions for this garment with per-tag confidence",
        },
        "season": {"type": "string", "enum": SEASON_CHOICES},
        "formality_level": {"type": "integer", "minimum": 1, "maximum": 10},
        "style_tags": {"type": "array", "items": {"type": "string", "enum": STYLE_TAG_CHOICES}},
        "mood_tags": {"type": "array", "items": {"type": "string"}},
        "confidence": {
            "type": "object",
            "properties": {
                "garment_type": {"type": "number"},
                "category": {"type": "number"},
                "subcategory": {"type": "number"},
                "primary_color": {"type": "number"},
                "pattern": {"type": "number"},
                "fit": {"type": "number"},
                "material": {"type": "number"},
                "occasion_type": {"type": "number"},
                "season": {"type": "number"},
                "formality_level": {"type": "number"},
            },
            "required": [
                "garment_type", "category", "subcategory", "primary_color",
                "fit", "material", "occasion_type", "season",
            ],
        },
    },
    "required": [
        "garment_type", "category", "subcategory", "primary_color",
        "pattern", "fit", "occasion_candidates", "season", "formality_level",
        "style_tags", "confidence",
    ],
}


def _get_api_key():
    api_key = getattr(settings, 'GEMINI_API_KEY', None)
    if not api_key:
        raise ValueError("GEMINI_API_KEY is not configured in settings.")
    return api_key


def _post_generate_content(model_name, parts, generation_config, timeout=15):
    """Shared raw REST call to the Gemini GenerateContent endpoint."""
    api_key = _get_api_key()
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"

    payload = {
        "contents": [
            {
                "parts": parts
            }
        ],
        "generationConfig": generation_config,
    }

    req_body = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(
        url,
        data=req_body,
        headers={'Content-Type': 'application/json'}
    )

    try:
        with urllib.request.urlopen(req, context=ssl_context, timeout=timeout) as response:
            return json.loads(response.read().decode('utf-8'))
    except Exception as e:
        logger.error(f"Gemini API call to {model_name} failed: {e}")
        if hasattr(e, 'read'):
            try:
                logger.error(f"Detail: {e.read().decode('utf-8')}")
            except Exception:
                pass
        raise e


def _parse_json_text(text):
    """Parse JSON from a Gemini text response, tolerating markdown fences and stray prose."""
    if not text:
        raise ValueError("Empty response text from Gemini.")
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        raise


def detect_image_mime(image_bytes):
    """Sniff the real image format so Gemini is not sent a wrong mimeType."""
    try:
        image_format = Image.open(io.BytesIO(image_bytes)).format
        return {
            'JPEG': 'image/jpeg',
            'PNG': 'image/png',
            'WEBP': 'image/webp',
            'GIF': 'image/gif',
        }.get(image_format, 'image/png')
    except Exception:
        return 'image/png'


def _inline_image_part(image_bytes):
    mime_type = detect_image_mime(image_bytes)
    return {
        "inlineData": {
            "mimeType": mime_type,
            "data": base64.b64encode(image_bytes).decode('utf-8'),
        }
    }


def generate_ecommerce_image(image_bytes: bytes) -> bytes:
    """
    Sends the input product image to the Gemini 2.5 Flash Image model (Nano Banana)
    with custom system instructions to remove the background, clean the image,
    and format it as a professional e-commerce product listing shot.
    """
    model_name = GEMINI_IMAGE_MODEL
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

    try:
        logger.info(f"Invoking {model_name} Nano Banana image generation...")
        # 15s timeout for fast UI response
        res_data = _post_generate_content(
            model_name,
            [{"text": prompt}, _inline_image_part(image_bytes)],
            {"responseModalities": ["IMAGE"]},
            timeout=15,
        )
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
        raise e


def extract_product_metadata_from_evidence(image_bytes: bytes, evidence: dict, timeout: int = VISION_TIMEOUT_SECONDS) -> dict:
    """
    Sends the product image plus scraped product evidence to Gemini vision
    (gemini-2.0-flash) and returns structured metadata with per-field confidence.

    `evidence` is the raw scraped product evidence dict produced by
    services.product_link_scraper.scrape_clothing_product(). The model is asked
    to inspect the image independently — scraped values may be wrong and are
    treated as evidence, not truth.

    Returns a dict whose keys match the legacy metadata keys used by the
    image-upload flow, plus extra internal keys (garment_type, primary_color,
    secondary_colors, sleeve, confidence).
    """
    if not image_bytes:
        raise ValueError("image_bytes is required for Gemini vision analysis.")

    name = str(evidence.get('name') or '')
    title = str(evidence.get('title') or '')
    description = str(evidence.get('description') or '')
    brand = str(evidence.get('brand') or '')
    structured_color = str(evidence.get('structured_color') or '')
    structured_category = str(evidence.get('structured_category') or '')
    structured_material = str(evidence.get('structured_material') or '')
    specs_text = str(evidence.get('specs_text') or '')
    source_url = str(evidence.get('source_url') or '')

    structured_attributes = evidence.get('structured_attributes') or {}
    variant_data = evidence.get('variant_data') or {}

    evidence_block = (
        f"Name: {name or 'unknown'}\n"
        f"Page title: {title or 'unknown'}\n"
        f"Description: {description or 'unknown'}\n"
        f"Brand: {brand or 'unknown'}\n"
        f"Structured color: {structured_color or 'unknown'}\n"
        f"Structured category: {structured_category or 'unknown'}\n"
        f"Structured material: {structured_material or 'unknown'}\n"
        f"Structured attributes: {json.dumps(structured_attributes, default=str)[:1500]}\n"
        f"Variants: {json.dumps(variant_data, default=str)[:800]}\n"
        f"Specifications: {specs_text[:1500]}\n"
        f"Source URL: {source_url}"
    )

    prompt = (
        "You are analyzing a clothing product for a wardrobe catalog. A product image and scraped "
        "product page evidence are provided.\n\n"
        "INSPECT THE IMAGE FIRST AND INDEPENDENTLY. The scraped evidence may be wrong or may "
        "conflict with the image (for example, the page may list a color that does not match the "
        "photo, or the title may describe a fit the garment does not have). Do not simply repeat "
        "the scraped values.\n\n"
        "Rules:\n"
        "- primary_color, pattern, fit (visible silhouette), garment_type, category, subcategory: "
        "base these on what you actually SEE in the image.\n"
        "- material: prefer the product evidence (specifications, structured data, description) "
        "when it is present and specific (e.g. \"100% Cotton\", \"70% Linen / 30% Cotton\"); "
        "otherwise estimate from the image only when reasonably confident; otherwise return null.\n"
        "- occasion_candidates: return 0-5 plausible occasions with per-tag confidence, using "
        "product evidence and image context. Pick ONLY tags from this allowed list: "
        f"{', '.join(OCCASION_CHOICES)}. Be conservative and do not invent occasions.\n"
        "- season: use product evidence and image context; be conservative and do not invent seasons.\n"
        "- Use only the allowed enum values. If a value is genuinely unknown, prefer the most "
        "neutral allowed value and give it low confidence.\n"
        "- Return confidence (0.0 to 1.0) for every field.\n\n"
        f"PRODUCT EVIDENCE (may conflict with the image):\n{evidence_block}\n\n"
        "Return ONLY the JSON object described by the response schema."
    )

    logger.info("Invoking Gemini %s metadata extraction from product evidence...", _get_vision_model())
    res_data = _post_generate_content(
        _get_vision_model(),
        [{"text": prompt}, _inline_image_part(image_bytes)],
        {
            "responseMimeType": "application/json",
            "responseSchema": VISION_RESPONSE_SCHEMA,
        },
        timeout=timeout,
    )
    text_out = res_data["candidates"][0]["content"]["parts"][0]["text"].strip()
    return normalize_vision_result(_parse_json_text(text_out))


def normalize_vision_result(data: dict) -> dict:
    """Normalize raw Gemini vision output into the shared metadata dict shape."""
    if not isinstance(data, dict):
        raise ValueError("Gemini vision response was not a JSON object.")

    def first_in(value, choices, default=None):
        if not value:
            return default
        value = str(value).strip()
        for choice in choices:
            if choice.lower() == value.lower():
                return choice
        return default

    primary_color = str(data.get('primary_color') or '').strip() or 'Other'
    secondary_colors = [c for c in (data.get('secondary_colors') or []) if isinstance(c, str) and c.strip()]
    category = first_in(data.get('category'), CATEGORY_CHOICES, None)
    fit = first_in(data.get('fit'), FIT_CHOICES, None)
    season = first_in(data.get('season'), SEASON_CHOICES, None)
    pattern = first_in(data.get('pattern'), PATTERN_CHOICES, 'Solid')
    # Occasion candidates: schema-based occasion_candidates [{tag, confidence}]
    # with backward compatibility for the legacy flat occasion_type list.
    raw_candidates = data.get('occasion_candidates')
    occasion_candidates = []
    if isinstance(raw_candidates, list):
        for cand in raw_candidates:
            if not isinstance(cand, dict):
                continue
            tag = str(cand.get('tag') or '').strip()
            if not tag:
                continue
            conf = cand.get('confidence')
            try:
                conf = float(conf)
            except (TypeError, ValueError):
                conf = None
            occasion_candidates.append({'tag': tag, 'confidence': conf})
    if not occasion_candidates and isinstance(data.get('occasion_type'), list):
        occasion_candidates = [
            {'tag': str(t).strip(), 'confidence': None}
            for t in data.get('occasion_type')
            if str(t).strip()
        ]
    normalized_candidates = []
    for cand in occasion_candidates:
        canonical = first_in(cand['tag'], OCCASION_CHOICES)
        if canonical:
            normalized_candidates.append({'tag': canonical, 'confidence': cand['confidence']})
    occasions = [cand['tag'] for cand in normalized_candidates]
    style_tags = [first_in(t, STYLE_TAG_CHOICES) for t in (data.get('style_tags') or []) if first_in(t, STYLE_TAG_CHOICES)]
    mood_tags = [str(m).strip() for m in (data.get('mood_tags') or []) if str(m).strip()][:3]
    formality_raw = data.get('formality_level')
    try:
        formality_level = max(1, min(10, int(formality_raw)))
    except (TypeError, ValueError):
        formality_level = 5

    subcategory = str(data.get('subcategory') or '').strip()
    if len(subcategory) > 50:
        subcategory = subcategory[:50]
    garment_type = str(data.get('garment_type') or '').strip()[:50]

    confidence = data.get('confidence') or {}
    if not isinstance(confidence, dict):
        confidence = {}

    def confidence_for(key):
        try:
            value = float(confidence.get(key))
        except (TypeError, ValueError):
            return None
        return max(0.0, min(1.0, value))

    material = str(data.get('material') or '').strip() or None
    sleeve = str(data.get('sleeve') or '').strip()[:50] or None

    return {
        "garment_type": garment_type,
        "category": category,
        "subcategory": subcategory,
        "primary_color": primary_color,
        "secondary_colors": secondary_colors,
        "secondary_color": secondary_colors[0] if secondary_colors else None,
        "color_family": infer_color_family(primary_color),
        "pattern": pattern,
        "fit": fit,
        "material": material,
        "sleeve": sleeve,
        "occasion_type": occasions,
        "occasion_candidates": normalized_candidates,
        "season": season,
        "formality_level": formality_level,
        "brand": None,
        "style_tags": style_tags,
        "mood_tags": mood_tags,
        "aesthetic_tone": " ".join(filter(None, [pattern, primary_color, subcategory or garment_type])),
        "confidence": {
            "garment_type": confidence_for('garment_type'),
            "category": confidence_for('category'),
            "subcategory": confidence_for('subcategory'),
            "primary_color": confidence_for('primary_color'),
            "pattern": confidence_for('pattern'),
            "fit": confidence_for('fit'),
            "material": confidence_for('material'),
            "occasion_type": confidence_for('occasion_type'),
            "season": confidence_for('season'),
            "formality_level": confidence_for('formality_level'),
        },
    }


def extract_product_metadata(image_bytes: bytes, name: str, color: str, type_str: str, category: str) -> dict:
    """
    Calls Gemini 2.0 Flash to extract additional rich metadata details about the
    clothing item. Kept for the image-upload and avatar flows; shares the same
    REST plumbing as extract_product_metadata_from_evidence().
    """
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
        "5. occasion_type: array of strings (one or more of: "
        + f"'{', '.join(OCCASION_CHOICES)}')\n"
        "6. season: string (one of: 'Summer', 'Winter', 'Monsoon', 'All-season')\n"
        "7. formality_level: integer from 1 (very casual) to 10 (extremely formal)\n"
        "8. brand: string or null (detect visible brand names/logos, or null)\n"
        "9. material: string or null (inferred material like Cotton, Denim, Linen, Polyester, Wool, Leather)\n"
        "10. style_tags: array of strings (select from: 'Minimalist', 'Streetwear', 'Sporty', 'Vintage', 'Bohemian', 'Classic', 'Business Casual', 'Y2K', 'Preppy', 'Grunge', 'Monochrome', 'Techwear', 'Cottagecore', 'Bold', 'Layered', 'Designer')\n"
        "11. mood_tags: array of 2-3 mood strings (e.g., ['Relaxed', 'Confident'])\n"
        "12. aesthetic_tone: string (e.g., 'Sleek and modern', 'Vibrant streetwear')\n\n"
        "Return ONLY a valid JSON object without markdown code blocks."
    )

    try:
        logger.info("Invoking Gemini %s metadata extraction...", _get_vision_model())
        res_data = _post_generate_content(
            _get_vision_model(),
            [{"text": prompt}, _inline_image_part(image_bytes)],
            {"responseMimeType": "application/json"},
            timeout=LEGACY_VISION_TIMEOUT_SECONDS,
        )
        text_out = res_data["candidates"][0]["content"]["parts"][0]["text"].strip()
        return _parse_json_text(text_out)
    except Exception as e:
        logger.error(f"Gemini metadata extraction failed: {e}")
        # Re-raise to trigger local fallback mapping
        raise e


def infer_color_family(color: str) -> str:
    """Heuristic color-family classification shared by all flows."""
    color_lower = (color or '').lower()
    color_family = 'Bold'
    if any(c in color_lower for c in ['black', 'navy', 'charcoal', 'dark grey', 'dark gray', 'slate', 'indigo', 'teal', 'dark teal', 'dark green', 'burgundy', 'midnight blue', 'forest', 'pine', 'emerald']):
        color_family = 'Dark'
    elif any(c in color_lower for c in ['white', 'grey', 'gray', 'beige', 'cream', 'off-white', 'sand']):
        color_family = 'Neutral'
    elif any(c in color_lower for c in ['brown', 'khaki', 'olive', 'tan', 'terracotta', 'rust', 'sage', 'earth']):
        color_family = 'Earth'
    elif any(c in color_lower for c in ['pink', 'lavender', 'mint', 'peach', 'baby blue', 'pastel']):
        color_family = 'Pastel'
    elif any(c in color_lower for c in ['red', 'yellow', 'orange', 'gold', 'amber']):
        color_family = 'Warm'
    return color_family


def infer_metadata_locally(name: str, color: str, type_str: str, category: str) -> dict:
    """
    Fallback method to infer metadata programmatically using standard rules if Gemini API fails.
    """
    logger.info("Executing local metadata inference fallback engine...")

    # 1. Color family heuristics
    color_family = infer_color_family(color)

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
    # Conservative fallback: no blanket occasion assignments beyond what the
    # garment type itself supports. A generic shirt is Casual — it never gets
    # invented Business/Date Night tags.
    formality = 3
    occasions = ['Casual']
    style_tags = ['Minimalist', 'Classic']
    mood_tags = ['Comfy', 'Relaxed']
    material = None

    if 'formal' in type_lower or 'suit' in type_lower or 'blazer' in type_lower or 'tuxedo' in type_lower:
        formality = 9
        occasions = ['Formal', 'Business']
        style_tags = ['Classic', 'Business Casual']
        mood_tags = ['Elegant', 'Confident']
        material = 'Wool Blend'
    elif 'shirt' in type_lower or 'polo' in type_lower:
        formality = 5
        occasions = ['Casual']
        style_tags = ['Classic', 'Business Casual']
        mood_tags = ['Smart', 'Sharp']
    elif 'jeans' in type_lower or 'denim' in type_lower:
        formality = 4
        occasions = ['Casual']
        style_tags = ['Streetwear', 'Vintage']
        mood_tags = ['Casual', 'Rugged']
        material = 'Denim'
    elif 'gym' in type_lower or 'sport' in type_lower or 'running' in type_lower or 'track' in type_lower or 'jogger' in type_lower:
        formality = 1
        occasions = ['Sports & Active', 'Gym']
        style_tags = ['Sporty', 'Techwear']
        mood_tags = ['Active', 'Energetic']
        material = 'Polyester'
    elif 'hoodie' in type_lower or 'sweatshirt' in type_lower:
        formality = 2
        occasions = ['Casual']
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