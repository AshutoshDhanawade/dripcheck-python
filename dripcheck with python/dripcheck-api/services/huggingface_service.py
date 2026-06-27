"""
services/huggingface_service.py
================================
Calls the Hugging Face Inference API to generate an avatar image
using the FLUX.2-klein-9B model.

Uses urllib.request (stdlib only) — no new dependencies required.
"""

import json
import urllib.request
import ssl
import logging
from django.conf import settings

logger = logging.getLogger(__name__)

# Reuse permissive SSL context (same pattern as gemini_service.py)
ssl_context = ssl.create_default_context()
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_NONE


def generate_avatar_image(prompt: str) -> bytes | None:
    """
    Calls the HF Inference API for FLUX.2-klein-9B with the given prompt.

    Args:
        prompt: A detailed fashion prompt describing the avatar and outfit.

    Returns:
        Raw image bytes (JPEG/PNG) on success, or None on failure.
    """
    api_token = getattr(settings, 'HF_API_TOKEN', '')
    model_id = getattr(settings, 'HF_MODEL_ID', 'black-forest-labs/FLUX.2-klein-9B')

    if not api_token:
        logger.error("HF_API_TOKEN is not configured in settings.")
        return None

    # HF Inference API endpoint for text-to-image
    url = f"https://api-inference.huggingface.co/models/{model_id}"

    payload = {
        "inputs": prompt,
        "parameters": {
            "num_inference_steps": 4,   # 4-step distilled model — fast
            "guidance_scale": 3.5,
            "width": 512,
            "height": 768,              # Portrait aspect ratio for full-body avatar
        }
    }

    req_body = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(
        url,
        data=req_body,
        headers={
            'Authorization': f'Bearer {api_token}',
            'Content-Type': 'application/json',
            'Accept': 'image/jpeg',
        }
    )

    try:
        logger.info(f"Calling HF Inference API for model: {model_id}")
        # 60s timeout — FLUX can take time on cold starts
        with urllib.request.urlopen(req, context=ssl_context, timeout=60) as response:
            image_bytes = response.read()
            if not image_bytes:
                logger.error("HF API returned empty image bytes.")
                return None
            logger.info(f"Successfully received avatar image ({len(image_bytes)} bytes).")
            return image_bytes
    except urllib.error.HTTPError as e:
        body = ''
        try:
            body = e.read().decode('utf-8')
        except Exception:
            pass
        logger.error(f"HF API HTTP error {e.code}: {body}")
        return None
    except Exception as e:
        logger.error(f"HF API request failed: {e}")
        return None


def build_avatar_prompt(
    uploaded_item_desc: str,
    uploaded_category: str,
    bundle_items: list,
    user_profile: dict | None = None
) -> str:
    """
    Constructs a detailed FLUX fashion prompt for the avatar.

    Args:
        uploaded_item_desc: Human-readable description of the uploaded clothing item.
        uploaded_category:  'Top', 'Bottom', or 'Footwear'
        bundle_items:       List of dicts with keys: name, category, primary_color, fit
        user_profile:       Optional dict with skin_tone, hair_color, body_type

    Returns:
        A well-structured prompt string for FLUX.
    """
    # ── Avatar persona ────────────────────────────────────────────────────────
    if user_profile:
        skin = user_profile.get('skin_tone', 'medium')
        hair = user_profile.get('hair_color', 'dark brown')
        body = user_profile.get('body_type', 'athletic')
        persona = f"a {body} build fashion model with {skin} skin tone and {hair} hair"
    else:
        persona = "a stylish young fashion model"

    # ── Build outfit description ──────────────────────────────────────────────
    outfit_parts = {}

    # Place uploaded item in its slot
    cat_map = {'Top': 'top', 'Bottom': 'bottom', 'Footwear': 'footwear',
               'Top Wear': 'top', 'Bottom Wear': 'bottom', 'Foot Wear': 'footwear'}
    norm_cat = cat_map.get(uploaded_category, 'top')
    outfit_parts[norm_cat] = uploaded_item_desc

    # Fill remaining slots from bundle items
    for item in bundle_items:
        item_cat = cat_map.get(item.get('category', ''), '')
        if item_cat and item_cat not in outfit_parts:
            desc = f"{item.get('primary_color', '')} {item.get('name', '')}".strip()
            outfit_parts[item_cat] = desc

    # Defaults for any still-missing slots
    defaults = {
        'top': 'a clean white fitted T-shirt',
        'bottom': 'slim fit dark blue jeans',
        'footwear': 'clean white sneakers',
    }
    for slot, default in defaults.items():
        if slot not in outfit_parts:
            outfit_parts[slot] = default

    outfit_desc = (
        f"Top: {outfit_parts['top']}. "
        f"Bottom: {outfit_parts['bottom']}. "
        f"Footwear: {outfit_parts['footwear']}."
    )

    prompt = (
        f"Full body fashion photograph of {persona}. "
        f"The model is wearing: {outfit_desc} "
        f"Studio lighting, clean white background, high resolution, "
        f"professional fashion photography, sharp details, "
        f"front-facing pose, standing straight, "
        f"ultra realistic, 4K quality."
    )

    logger.info(f"Built FLUX prompt: {prompt}")
    return prompt
