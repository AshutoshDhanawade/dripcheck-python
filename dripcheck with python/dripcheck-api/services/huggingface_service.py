"""
services/huggingface_service.py
================================
Production-ready Hugging Face avatar generation service.

This module keeps the public API used by the Django views unchanged:

    generate_avatar_image(prompt: str, image_bytes: bytes | None = None) -> bytes | None
    build_avatar_prompt(...)

The hosted Inference API fallback uses urllib.request. The Qwen Image Edit
backend uses Pillow, Torch and Diffusers at generation time.
"""

from __future__ import annotations

import json
import logging
import socket
import ssl
import time
import urllib.error
import urllib.request
from io import BytesIO
from typing import Any

from django.conf import settings

logger = logging.getLogger(__name__)

HF_API_BASE_URL = "https://api-inference.huggingface.co/models"

INFERENCE_API_BACKEND = "inference_api"
DEFAULT_BACKEND = "diffusers"
DEFAULT_MODEL_ID = "Qwen/Qwen-Image-Edit"

DEFAULT_TIMEOUT = 180
MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 5

DEFAULT_WIDTH = 768
DEFAULT_HEIGHT = 1024
DEFAULT_GUIDANCE = 7.5
DEFAULT_STEPS = 28

QWEN_TRUE_CFG_SCALE = 4.0
QWEN_NEGATIVE_PROMPT = " "
QWEN_STEPS = 50
QWEN_SEED = 0

MIN_IMAGE_BYTES = 1000
IMAGE_CONTENT_TYPES = {"image/jpeg", "image/png"}

# Enable console prints by default so local API calls are easy to debug.
DEBUG = True

# Reuse permissive SSL context to match the existing project pattern.
ssl_context = ssl.create_default_context()
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_NONE


def _debug_enabled() -> bool:
    """Return whether verbose Hugging Face debug output should be printed."""
    try:
        return bool(getattr(settings, "HF_DEBUG", DEBUG))
    except Exception:
        return DEBUG


def _debug(message: str) -> None:
    """Print and log verbose debug messages when HF_DEBUG is enabled."""
    if not _debug_enabled():
        return
    print(message)
    logger.info(message)


def _error(message: str, exc: Exception | None = None) -> None:
    """Always log errors and print them when debug mode is enabled."""
    if exc is None:
        logger.error(message)
    else:
        logger.error("%s: %s", message, exc)

    if _debug_enabled():
        if exc is None:
            print(message)
        else:
            print(f"{message}: {exc}")


def _get_hf_model_spec() -> tuple[str, str, str]:
    """Return the Hugging Face backend, model ID and API token."""
    api_token = getattr(settings, "HF_API_TOKEN", "")
    model_id = getattr(settings, "HF_MODEL_ID", DEFAULT_MODEL_ID)
    backend = getattr(settings, "HF_GENERATION_BACKEND", DEFAULT_BACKEND)
    return backend, model_id, api_token


def _build_endpoint(model_id: str) -> str:
    """Build the Hugging Face Inference API endpoint for a model."""
    return f"{HF_API_BASE_URL}/{model_id}"


def _build_headers(api_token: str) -> dict[str, str]:
    """Build request headers for Hugging Face without exposing the token."""
    return {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json",
        "Accept": "image/jpeg, image/png, application/json",
    }


def _redacted_headers(headers: dict[str, str]) -> dict[str, str]:
    """Return headers safe for console output."""
    safe_headers = dict(headers)
    if "Authorization" in safe_headers:
        safe_headers["Authorization"] = "Bearer ***"
    return safe_headers


def _build_payload(prompt: str) -> dict[str, Any]:
    """Build an Inference API payload for text-to-image fallback backends."""
    return {
        "inputs": prompt,
        "parameters": {
            "num_inference_steps": DEFAULT_STEPS,
            "guidance_scale": DEFAULT_GUIDANCE,
            "width": DEFAULT_WIDTH,
            "height": DEFAULT_HEIGHT,
        },
        "options": {
            "wait_for_model": True,
        },
    }


def _format_json(value: Any) -> str:
    """Pretty-print JSON-compatible values for logs."""
    try:
        return json.dumps(value, indent=2, ensure_ascii=False)
    except TypeError:
        return str(value)


def _log_request(
    model_id: str,
    endpoint: str,
    prompt: str,
    payload: dict[str, Any],
    headers: dict[str, str],
    attempt: int,
) -> None:
    """Log the outgoing Hugging Face request."""
    _debug(
        "\n========== HUGGING FACE ==========\n"
        f"Generating avatar... attempt {attempt}/{MAX_RETRIES}\n\n"
        f"Model:\n{model_id}\n\n"
        f"URL:\n{endpoint}\n\n"
        f"Prompt:\n{prompt}\n\n"
        f"Payload:\n{_format_json(payload)}\n\n"
        f"Headers:\n{_format_json(_redacted_headers(headers))}"
    )


def _log_response(
    status_code: int,
    headers: dict[str, str],
    content_type: str,
    body: bytes,
) -> None:
    """Log the incoming Hugging Face response."""
    response_text = ""
    if _is_json_content_type(content_type):
        response_text = _decode_body(body)

    message = (
        "\n========== HUGGING FACE RESPONSE ==========\n"
        f"Status:\n{status_code}\n\n"
        f"Response Headers:\n{_format_json(headers)}\n\n"
        f"Content-Type:\n{content_type or 'unknown'}\n\n"
        f"Response Size:\n{len(body)} bytes"
    )

    if response_text:
        message += f"\n\nResponse Body:\n{response_text}"

    _debug(message)


def _decode_body(body: bytes) -> str:
    """Decode response bytes for readable diagnostics."""
    try:
        return body.decode("utf-8")
    except UnicodeDecodeError:
        return body.decode("utf-8", errors="replace")


def _is_json_content_type(content_type: str) -> bool:
    """Return True when a response content type is JSON."""
    return "application/json" in (content_type or "").lower()


def _is_image_response(content_type: str) -> bool:
    """Return True when Hugging Face returned a supported image type."""
    normalized = (content_type or "").split(";")[0].strip().lower()
    return normalized in IMAGE_CONTENT_TYPES


def _looks_like_image(image_bytes: bytes, content_type: str) -> bool:
    """Validate basic image markers before returning bytes to Django."""
    if not image_bytes:
        _error("HF API returned an empty response body.")
        return False

    if len(image_bytes) <= MIN_IMAGE_BYTES:
        _error(
            "HF API returned too few bytes to be a valid avatar image "
            f"({len(image_bytes)} bytes)."
        )
        return False

    normalized = (content_type or "").split(";")[0].strip().lower()
    if normalized == "image/jpeg" and image_bytes.startswith(b"\xff\xd8\xff"):
        return True
    if normalized == "image/png" and image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return True

    _error("HF API response content type was image/* but bytes were not a valid JPEG/PNG.")
    return False


def _parse_json_error(body: bytes) -> dict[str, Any] | None:
    """Parse a JSON error/inference message body from Hugging Face."""
    if not body:
        _error("HF API returned JSON content type with an empty body.")
        return None

    text = _decode_body(body)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        _error(f"HF API returned invalid JSON: {text}", exc)
        return None

    _debug(f"HF API returned JSON instead of an image:\n{_format_json(parsed)}")
    return parsed


def _json_message(data: dict[str, Any] | None) -> str:
    """Extract a readable message from Hugging Face JSON."""
    if not data:
        return ""
    for key in ("error", "message", "detail"):
        value = data.get(key)
        if value:
            return str(value)
    return _format_json(data)


def _is_retryable_status(status_code: int) -> bool:
    """Return True for temporary HTTP statuses worth retrying."""
    return status_code in {408, 409, 425, 429, 500, 502, 503, 504}


def _is_model_loading(data: dict[str, Any] | None) -> bool:
    """Detect Hugging Face model-loading responses."""
    if not data:
        return False

    message = _json_message(data).lower()
    return "loading" in message or "estimated_time" in data


def _should_retry_json(status_code: int, data: dict[str, Any] | None) -> bool:
    """Decide whether a JSON response should be retried."""
    if _is_model_loading(data):
        estimated = data.get("estimated_time") if data else None
        _debug(f"Model is loading. Estimated time: {estimated or 'unknown'} seconds.")
        return True
    return _is_retryable_status(status_code)


def _log_actionable_http_error(status_code: int, data: dict[str, Any] | None) -> None:
    """Print useful guidance for common Hugging Face failures."""
    message = _json_message(data) or "No JSON error details returned."

    if status_code in {401, 403}:
        _error(f"HF authentication/permission error ({status_code}): {message}")
    elif status_code == 404:
        _error(f"HF model endpoint was not found or unsupported ({status_code}): {message}")
    elif status_code == 429:
        _error(f"HF rate limit error ({status_code}): {message}")
    elif 500 <= status_code <= 599:
        _error(f"HF temporary server error ({status_code}): {message}")
    else:
        _error(f"HF HTTP error ({status_code}): {message}")


def _read_http_error(error: urllib.error.HTTPError) -> tuple[dict[str, str], str, bytes]:
    """Safely read details from urllib HTTPError."""
    headers = dict(error.headers.items()) if error.headers else {}
    content_type = error.headers.get("Content-Type", "") if error.headers else ""
    try:
        body = error.read()
    except Exception as exc:
        _error("Failed to read HF HTTP error body", exc)
        body = b""
    return headers, content_type, body


def _generate_request(
    endpoint: str,
    headers: dict[str, str],
    payload: dict[str, Any],
) -> tuple[int, dict[str, str], str, bytes]:
    """Execute one Hugging Face request and return response details."""
    req_body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        endpoint,
        data=req_body,
        headers=headers,
        method="POST",
    )

    with urllib.request.urlopen(
        request,
        context=ssl_context,
        timeout=DEFAULT_TIMEOUT,
    ) as response:
        body = response.read()
        response_headers = dict(response.headers.items())
        content_type = response.headers.get("Content-Type", "")
        status_code = getattr(response, "status", response.getcode())
        return status_code, response_headers, content_type, body


def _handle_response(
    status_code: int,
    response_headers: dict[str, str],
    content_type: str,
    body: bytes,
) -> tuple[bytes | None, bool]:
    """
    Validate a Hugging Face response.

    Returns:
        A tuple of (image bytes or None, should_retry).
    """
    _log_response(status_code, response_headers, content_type, body)

    if _is_image_response(content_type):
        if _looks_like_image(body, content_type):
            _debug(
                "\nImage Size:\n"
                f"{len(body)} bytes\n\n"
                "Avatar generation successful. Returning image bytes to Django."
            )
            return body, False
        return None, False

    if _is_json_content_type(content_type):
        data = _parse_json_error(body)
        _log_actionable_http_error(status_code, data)
        return None, _should_retry_json(status_code, data)

    _error(
        "HF API returned an unsupported content type: "
        f"{content_type or 'unknown'} ({len(body)} bytes)."
    )
    return None, _is_retryable_status(status_code)


def _generate_with_retry(
    model_id: str,
    endpoint: str,
    prompt: str,
    headers: dict[str, str],
    payload: dict[str, Any],
) -> bytes | None:
    """Generate an avatar with retry handling for temporary failures."""
    started_at = time.monotonic()

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            _log_request(model_id, endpoint, prompt, payload, headers, attempt)
            status_code, response_headers, content_type, body = _generate_request(
                endpoint,
                headers,
                payload,
            )
            image_bytes, should_retry = _handle_response(
                status_code,
                response_headers,
                content_type,
                body,
            )

            if image_bytes is not None:
                elapsed = time.monotonic() - started_at
                _debug(f"Execution Time:\n{elapsed:.2f} seconds")
                _debug("Save Status:\nReady for Django view to save in media/avatars.")
                return image_bytes

            if not should_retry:
                break

        except urllib.error.HTTPError as exc:
            response_headers, content_type, body = _read_http_error(exc)
            _log_response(exc.code, response_headers, content_type, body)
            data = _parse_json_error(body) if _is_json_content_type(content_type) else None
            _log_actionable_http_error(exc.code, data)
            if not (_is_retryable_status(exc.code) or _is_model_loading(data)):
                break

        except urllib.error.URLError as exc:
            _error("HF network/URL error", exc)

        except (socket.timeout, TimeoutError) as exc:
            _error(f"HF request timed out after {DEFAULT_TIMEOUT} seconds", exc)

        except ssl.SSLError as exc:
            _error("HF SSL error", exc)
            break

        except PermissionError as exc:
            _error("HF permission error", exc)
            break

        except Exception as exc:
            _error("Unexpected HF API request failure", exc)
            break

        if attempt < MAX_RETRIES:
            _debug(f"Retrying HF request in {RETRY_DELAY_SECONDS} seconds...")
            time.sleep(RETRY_DELAY_SECONDS)

    elapsed = time.monotonic() - started_at
    _error(f"Avatar generation failed after {elapsed:.2f} seconds.")
    return None


def generate_avatar_image(prompt: str, image_bytes: bytes | None = None) -> bytes | None:
    """
    Generate an avatar image using the configured Hugging Face backend.

    Args:
        prompt: A detailed fashion prompt describing the avatar and outfit.
        image_bytes: Optional uploaded image bytes. Required for Qwen Image Edit.

    Returns:
        Raw JPEG/PNG bytes on success, or None on failure.
    """
    backend, model_id, api_token = _get_hf_model_spec()

    if backend == "diffusers" or model_id == DEFAULT_MODEL_ID:
        _debug("Using Qwen Image Edit Diffusers backend for avatar generation.")
        return generate_avatar_image_diffusers(prompt, image_bytes=image_bytes)

    if not api_token:
        _error("HF_API_TOKEN is not configured in Django settings.")
        return None

    if backend != INFERENCE_API_BACKEND:
        _error(
            "Unsupported HF_GENERATION_BACKEND configured: "
            f"{backend}. Expected '{INFERENCE_API_BACKEND}' or 'diffusers'."
        )
        return None

    endpoint = _build_endpoint(model_id)
    headers = _build_headers(api_token)
    payload = _build_payload(prompt)

    return _generate_with_retry(model_id, endpoint, prompt, headers, payload)


def generate_avatar_image_diffusers(
    prompt: str,
    image_bytes: bytes | None = None,
) -> bytes | None:
    """
    Generate an avatar image with Qwen/Qwen-Image-Edit through Diffusers.

    Qwen Image Edit is an image-editing model, so it needs the uploaded image
    bytes plus the fashion prompt. The returned bytes are PNG image data.
    """
    backend, model_id, _api_token = _get_hf_model_spec()
    started_at = time.monotonic()

    _debug(
        "\n========== QWEN IMAGE EDIT ==========\n"
        f"Backend:\n{backend}\n\n"
        f"Model:\n{model_id}\n\n"
        f"Prompt:\n{prompt}\n\n"
        f"Input Image Size:\n{len(image_bytes or b'')} bytes"
    )

    if not image_bytes:
        _error("Qwen Image Edit requires uploaded image bytes, but none were provided.")
        return None

    try:
        from PIL import Image, UnidentifiedImageError
    except ImportError as exc:
        _error("Pillow is required for Qwen Image Edit. Install it with: pip install Pillow", exc)
        return None

    try:
        import torch
    except ImportError as exc:
        _error("Torch is required for Qwen Image Edit. Install it with the correct CUDA/CPU wheel.", exc)
        return None

    try:
        from diffusers import QwenImageEditPipeline
    except ImportError as exc:
        _error("Diffusers with QwenImageEditPipeline is required. Install/upgrade diffusers.", exc)
        return None

    try:
        input_image = Image.open(BytesIO(image_bytes)).convert("RGB")
    except UnidentifiedImageError as exc:
        _error("Uploaded file is not a valid image for Qwen Image Edit.", exc)
        return None
    except Exception as exc:
        _error("Failed to load uploaded image for Qwen Image Edit.", exc)
        return None

    try:
        device = "cuda" if torch.cuda.is_available() else "cpu"
        dtype = torch.bfloat16 if device == "cuda" else torch.float32

        _debug(
            "Loading Qwen Image Edit pipeline...\n"
            f"Device:\n{device}\n\n"
            f"DType:\n{dtype}\n\n"
            f"Parameters:\n"
            f"true_cfg_scale={QWEN_TRUE_CFG_SCALE}, "
            f"num_inference_steps={QWEN_STEPS}, seed={QWEN_SEED}"
        )

        pipeline = QwenImageEditPipeline.from_pretrained(model_id)
        pipeline.to(dtype)
        pipeline.to(device)
        pipeline.set_progress_bar_config(disable=None)

        generator_device = device if device == "cuda" else "cpu"
        generator = torch.Generator(device=generator_device).manual_seed(QWEN_SEED)

        inputs = {
            "image": input_image,
            "prompt": prompt,
            "generator": generator,
            "true_cfg_scale": QWEN_TRUE_CFG_SCALE,
            "negative_prompt": QWEN_NEGATIVE_PROMPT,
            "num_inference_steps": QWEN_STEPS,
        }

        with torch.inference_mode():
            output = pipeline(**inputs)

        output_image = output.images[0]
        buffer = BytesIO()
        output_image.save(buffer, format="PNG")
        generated_bytes = buffer.getvalue()

        if not _looks_like_image(generated_bytes, "image/png"):
            return None

        elapsed = time.monotonic() - started_at
        _debug(
            "\nQwen avatar generation successful.\n"
            f"Output Image Size:\n{len(generated_bytes)} bytes\n\n"
            f"Execution Time:\n{elapsed:.2f} seconds\n\n"
            "Save Status:\nReady for Django view to save in media/avatars."
        )
        return generated_bytes

    except RuntimeError as exc:
        _error("Qwen Image Edit runtime error. Check CUDA memory, Torch, and Diffusers versions.", exc)
        return None
    except Exception as exc:
        _error("Unexpected Qwen Image Edit failure.", exc)
        return None


def _profile_value(profile: dict[str, Any], key: str, default: str) -> str:
    """Read a user profile field without allowing None or empty strings."""
    value = profile.get(key) if profile else None
    if value is None:
        return default
    text = str(value).strip()
    return text or default


def _item_text(item: dict[str, Any] | None, fallback: str) -> str:
    """Build a compact clothing item description with safe defaults."""
    if not item:
        return fallback

    color = str(item.get("primary_color") or item.get("color") or "").strip()
    name = str(item.get("name") or item.get("subcategory") or fallback).strip()
    category = str(item.get("category") or "").strip()
    pattern = str(item.get("pattern") or "").strip()
    material = str(item.get("material") or "").strip()
    fit = str(item.get("fit") or "").strip()

    parts = [color, pattern, fit, material, name]
    description = " ".join(part for part in parts if part).strip()
    if category:
        description = f"{description} ({category})"
    return description or fallback


def _normalize_category(category: str) -> str:
    """Normalize project category names into prompt outfit slots."""
    cat_map = {
        "Top": "top",
        "Top Wear": "top",
        "topwear": "top",
        "top": "top",
        "Bottom": "bottom",
        "Bottom Wear": "bottom",
        "bottomwear": "bottom",
        "bottom": "bottom",
        "Footwear": "footwear",
        "Foot Wear": "footwear",
        "footwear": "footwear",
        "foot": "footwear",
        "Layer": "layer",
        "outerwear": "layer",
        "Accessory": "accessory",
    }
    return cat_map.get(category, "top")


def build_avatar_prompt(
    uploaded_item_desc: str,
    uploaded_category: str,
    recommended_bundle: dict | None,
    user_profile: dict | None = None,
) -> str:
    """
    Construct a detailed Qwen Image Edit fashion prompt for the avatar.

    Args:
        uploaded_item_desc: Human-readable description of the uploaded item.
        uploaded_category: Top, Bottom, Footwear, or related project category.
        recommended_bundle: Mapping of slot keys to wardrobe item dicts.
        user_profile: Optional dict with skin_tone, hair_color and body_type.

    Returns:
        A rich prompt string for Qwen image generation.
    """
    profile = user_profile or {}

    body_type = _profile_value(profile, "body_type", "athletic")
    skin = _profile_value(profile, "skin_tone", "medium")
    hair = _profile_value(profile, "hair_color", "dark brown")
    gender = _profile_value(profile, "gender", "professional")
    preferred_style = _profile_value(profile, "preferred_style", "modern")
    occasion = _profile_value(profile, "occasion", "ecommerce fashion catalog")
    season = _profile_value(profile, "season", "all-season")

    outfit_parts = {
        "top": "a clean white fitted T-shirt",
        "bottom": "slim fit dark blue jeans",
        "footwear": "clean white sneakers",
    }

    uploaded_slot = _normalize_category(uploaded_category)
    if uploaded_slot in outfit_parts:
        outfit_parts[uploaded_slot] = uploaded_item_desc or outfit_parts[uploaded_slot]

    bundle = recommended_bundle or {}
    slot_map = {
        "topwear": "top",
        "top": "top",
        "bottomwear": "bottom",
        "bottom": "bottom",
        "footwear": "footwear",
        "shoes": "footwear",
        "outerwear": "layer",
        "layer": "layer",
    }

    for slot_name, item in bundle.items():
        if not item:
            continue
        normalized_slot = slot_map.get(str(slot_name), _normalize_category(item.get("category", "")))
        if normalized_slot in outfit_parts and normalized_slot != uploaded_slot:
            outfit_parts[normalized_slot] = _item_text(item, outfit_parts[normalized_slot])
        elif normalized_slot == "layer":
            outfit_parts["layer"] = _item_text(item, "a tailored lightweight jacket")

    layer_line = ""
    if outfit_parts.get("layer"):
        layer_line = f"\nLayer: {outfit_parts['layer']}."

    prompt = (
        "Ultra realistic full body fashion photography of a professional fashion model. "
        f"The model has an {body_type} build, {skin} skin tone, and {hair} hair. "
        f"Gender presentation: {gender}. Styling direction: {preferred_style}. "
        f"Occasion: {occasion}. Season: {season}. "
        "Natural standing pose, confident relaxed posture, sharp facial features, "
        "natural proportions, realistic hands, premium ecommerce catalog quality, "
        "studio lighting, soft shadows, white seamless background, fashion editorial, "
        "photorealistic, high detail, detailed fabric textures, color coordinated outfit, "
        "modern styling, luxury fashion photography, 8k.\n\n"
        "Wearing:\n"
        f"Top: {outfit_parts['top']}.\n"
        f"Bottom: {outfit_parts['bottom']}.\n"
        f"Footwear: {outfit_parts['footwear']}."
        f"{layer_line}\n\n"
        "Avoid distorted anatomy, extra fingers, missing limbs, blurry face, bad proportions, "
        "cartoon style, illustration, watermark, text, logo, cropped body."
    )

    _debug(f"Built Qwen prompt:\n{prompt}")
    return prompt
