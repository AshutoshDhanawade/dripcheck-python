# Dripcheck Bundle Generation API

This service is a specialized FastAPI-based application designed to handle the core logic for outfit recommendations and marketplace inspiration within the Dripcheck ecosystem.

## Overview

The Bundle Generation API leverages the Dripcheck Compatibility Engine to analyze a user's wardrobe and generate optimized outfit combinations (bundles). It also serves curated marketplace content that matches the user's stylistic preferences.

**Service Port:** `8001`

---

## API Endpoints

### 1. Generate/Fetch Bundles
`GET /api/bundles/{user_id}`

Retrieves a list of recommended outfit bundles for a specific user.
- **Path Parameters:**
    - `user_id`: Unique identifier for the user.
- **Query Parameters:**
    - `occasion` (optional): Filter bundles by occasion (e.g., "Casual", "Formal", "Date Night").
- **Response:** A list of `OutfitBundle` objects.

### 2. Save Bundle
`POST /api/bundles/{user_id}/save`

Saves a generated bundle to the user's permanent collection.
- **Path Parameters:**
    - `user_id`: Unique identifier for the user.
- **Request Body:** An `OutfitBundle` object.
- **Response:** The saved `OutfitBundle` object with `is_saved=True`.

### 3. Marketplace Discovery
`GET /api/marketplace`

Fetches curated marketplace bundles for style inspiration or purchase.
- **Query Parameters:**
    - `occasion` (optional): Filter by occasion tag.
    - `style` (optional): Filter by style tag (e.g., "Streetwear", "Minimalist").
- **Response:** A list of `MarketplaceBundle` objects.

---

## Data Models

The API uses shared Pydantic models defined in `models/types.py`:

- **OutfitBundle**: Contains `bundle_id`, `items` (list of item IDs), `compatibility_score`, `style_tags`, and `source`.
- **MarketplaceBundle**: Contains `title`, `description`, `items` (list of `MarketplaceItem`), and `match_percentage`.

---

## Technical Details

- **Framework:** FastAPI
- **Server:** Uvicorn (ASGI)
- **Integration:** Directly imports from `services.data_service` and `engine.compatibility_engine`.

---

## Getting Started

### Prerequisites
- Python 3.12+
- Dependencies installed via `pip install -r requirements.txt`

### Running the API
From the `dripcheck-api` directory, execute:

```bash
python bundlegeneration.py
```

The API will be available at `http://localhost:8001`. You can access the interactive documentation (Swagger UI) at `http://localhost:8001/docs`.
