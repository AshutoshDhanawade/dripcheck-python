# DripCheck — Bundle Generation, Recommendation Engines & Compatibility Score

This document explains the full logic behind outfit bundle generation, the
recommendation engines, and the compatibility scoring system.

---

## 1. Architecture Overview

Everything funnels through **one shared scoring function**,
`calculate_compatibility_score()`. The different engines (user-wardrobe,
anchor-based, AI-based, avatar) only differ in *how they enumerate
combinations* and *what they rank*.

```
Upload / Wardrobe item
        │
        ▼
Gemini vision  ──►  extract_product_metadata()   ──►  WardrobeItem
        │              (gemini_service.py:98)                │
        ▼ failure                                           ▼
infer_metadata_locally()  ◄── rule-based fallback     Compatibility Engine
(gemini_service.py:176)                                    │
                                                           ▼
        ┌──────────────────────────────────────────────────┐
        │ calculate_compatibility_score()                  │
        │   • Hard rejects (R1–R4)                         │
        │   • Weighted scoring (max 100)                   │
        └──────────────────────────────────────────────────┘
                          │
        ┌─────────────────┼─────────────────┐
        ▼                 ▼                 ▼
 generate_bundles   recommend_bundle_      generate_ai_bundles
 (wardrobe search)  for_anchor (avatar)    (AI item search)
```

## 2. Data Model

Every `WardrobeItem` (api/models.py:86) carries the attributes the engines
read:

| Field | Values / Notes |
|---|---|
| `category` | `Top`, `Bottom`, `Footwear`, `Layer`, `Accessory` |
| `primary_color` / `secondary_color` | Free text color names |
| `color_family` | `Neutral`, `Earth`, `Dark`, `Bold`, `Pastel`, `Warm` |
| `pattern` | `Solid`, `Stripes`, `Checks`, `Graphic`, `Floral`, `Abstract` |
| `fit` | `Slim`, `Regular`, `Relaxed`, `Oversized`, `Cropped`, `Baggy`, `Tapered` |
| `formality_level` | Integer 1 (casual) – 10 (extremely formal) |
| `season` | `Summer`, `Winter`, `Monsoon`, `All-season` |
| `occasion_type` | JSON array, e.g. `["Casual", "Weekend"]` |
| `style_tags`, `mood_tags` | JSON arrays of derived labels |
| `material`, `brand`, `wear_count`, `last_worn` | Auxiliary / feedback signals |

These attributes are populated automatically at upload time by Gemini vision
(`extract_product_metadata`, services/gemini_service.py:98) or, on failure, by
the rule-based local fallback (`infer_metadata_locally`,
services/gemini_service.py:176).

## 3. Color System

### 3.1 Color families (`PRIMARY_COLOR_TO_FAMILY`, engine/compatibility_engine.py:10)

Free-text colors are normalized into six families:

- **Neutral**: White, Black, Grey, Beige, Ivory, Off-White, Charcoal
- **Earth**: Brown, Camel, Khaki, Olive, Tan, Rust, Terracotta
- **Dark**: Navy, Dark Green, Burgundy, Slate, Midnight Blue
- **Bold**: Red, Yellow, Cobalt Blue, Fuchsia, Orange, Neon Green, Purple
- **Pastel**: Baby Pink, Mint, Lavender, Baby Blue, Blush, Peach
- **Warm**: Mustard, Sage Green, Dusty Rose, Mauve, Warm Beige

### 3.2 Harmony tiers (`get_harmony_tier`, engine/compatibility_engine.py:31)

Every unordered color *pair* is scored on a tier 0–3:

| Tier | Meaning | Example pairs |
|---|---|---|
| 3 | Great match | Bold+Neutral, Dark+Neutral, Earth+Neutral, Neutral+Pastel |
| 2 | Good match | Neutral+Neutral, Earth+Earth, Dark+Dark, Pastel+Pastel, Neutral+Warm |
| 1 | Risky | Dark+Earth, Earth+Warm |
| 0 | Blocked | Bold+Bold, Bold+Pastel |

## 4. Compatibility Score — `calculate_compatibility_score()` (engine/compatibility_engine.py:95)

Requires at least 2 items; otherwise returns `score: 0, is_valid: False`.

### 4.1 Hard rejections (score 0, `is_valid: False`, with a reason)

| Rule | Condition | Rejection reason |
|---|---|---|
| R1 | `max(formality) − min(formality) >= 3` | `formality_gap` |
| R2 | More than one *specific* season (ignoring `All-season`) | `season_mismatch` |
| R3 | ≥2 non-solid items AND (any `Graphic`, or ≥2 of `{Stripes, Checks, Floral, Abstract}`) | `pattern_conflict` |
| R4 | Any color pair has harmony tier 0 | `color_clash` |

### 4.2 Scoring components (max 100, clamped)

| Component | Points | Logic |
|---|---|---|
| Occasion match | +25 | All items share ≥1 occasion tag (set intersection) |
| Color harmony | +30 / +20 / +10 | Based on the *weakest* pair tier (1 / 2 / 3) |
| Pattern balance | +15 / +10 / 0 | 1 patterned item → +15; 0 patterned → +10; ≥2 → 0 |
| Fit harmony | +10 / −10 | Oversized top + Slim/Tapered bottom → +10; Oversized top + Baggy/Oversized bottom → −10 |
| Brand cohesion | +5 | Any brand appears ≥2 times |
| Footwear presence | +5 | At least one Footwear item |
| Formality penalty | −15 | Gap of exactly 2 between non-`versatile`/`smart casual` items |

## 5. Bundle Generator — `generate_bundles()` (engine/compatibility_engine.py:344)

Used by:
- `BundleListView` (bundlegeneration.py:31) — user's wardrobe
- `GenerateFromProductView` / `GenerateFromWardrobeItemView` (bundle_generate/views.py:60, 115) — merchant catalogue around a chosen anchor

Algorithm:

1. **Filter the pool**
   - Remove items whose `primary_color` or color family matches `avoided_colors` (from `UserProfile.avoided_colors`).
   - If an `occasion_filter` is set, keep only items tagged with that occasion.
2. **Split into category pools** — tops, bottoms, shoes, layers.
3. **Brute-force combinations**
   - For every `Top × Bottom × Footwear` triple:
     - Score the trio; skip if invalid.
     - Try adding *each* Layer and greedily keep the single layer that improves the score.
4. **Augment each valid combo**
   - `compute_dominant_color()` (engine/compatibility_engine.py:57) — weighted color voting: Top=3, Bottom=3, Layer=2, Footwear=1, Accessory=0.5; ties joined with `" / "`; family looked up from the winner.
   - `assign_style_tags()` (engine/compatibility_engine.py:206) — see §7.
5. **Sort by score descending** and build `OutfitBundle` rows
   - `bundle_id = "GEN-xxxxxxx"`, `source = 'user_generated'`, occasion/style/mood tags, `compatibility_score`.

## 6. Anchor-Based Recommendation — `recommend_bundle_for_anchor()` (engine/compatibility_engine.py:444)

Used in the avatar flow (api/views_avatar.py:332) to dress a single uploaded item with the rest of the user's wardrobe.

- Missing complement categories are filled from the wardrobe (max 6 items per category), e.g. a **Top** anchor needs `Bottom + Footwear` (+ optional `Layer`).
- Enumerates all combinations, scores each with the shared engine, optionally extends with a Layer, and picks the highest-scoring combo.
- Returns:
  - `recommended_bundle` — `topwear / bottomwear / footwear / outerwear` slots
  - `matching_score` — raw score / 100
  - `items` — the winning items
  - `has_recommendations` — whether any valid combo existed

## 7. Style Tag Assignment — `assign_style_tags()` (engine/compatibility_engine.py:206)

15 hard-coded styles are evaluated against rule lambdas:

`Minimalist, Streetwear, Sporty/Athleisure, Vintage/Retro, Bohemian/Boho, Classic/Timeless, Business Casual, Y2K, Preppy, Grunge, Monochrome, Techwear, Cottagecore, Bold/Statement, Layered`

For each style: `confidence = matched_rules / total_rules`. A tag is kept when
`confidence >= 0.5`, and the results are sorted by confidence descending.
Bundles keep the top 2 style tags.

## 8. AI Recommendation Engine — `generate_ai_bundles()` (ai_generation/services.py:129)

A separate engine for suggesting AI-generated items to fill wardrobe gaps.

1. **Fetch AI candidates** — up to 20 items from
   `TopwearAiRecommendation` / `BottomwearAiGeneration` /
   `FootwearAiRecommendation` (bundle_generate/models.py), filtered by
   occasion/season, excluding items the user already owns.
2. **Rank the user's real wardrobe** per complement category by
   `wear_count` descending / `last_worn`.
3. **Build valid pairs** from the user's items, then for each AI candidate
   evaluate `[ai_item, first, second]` combos with the shared engine.
4. **Keep the best AI item** (highest top score) as `recommended_item`.
5. **Assemble 5–8 deduplicated bundles**, each with a human-readable
   `explanation` (`build_explanation`, ai_generation/services.py:87) covering
   color harmony tier, shared occasions, and formality alignment.

## 9. End-to-End Flow — Upload → Avatar (api/views_avatar.py:194)

1. User uploads a clothing photo; `_detect_garment_color` reads the true color from pixels.
2. Gemini extracts metadata → a temporary `_FakeItem`.
3. `recommend_bundle_for_anchor` finds the best matching outfit from the user's wardrobe.
4. `build_avatar_prompt()` (services/huggingface_service.py:909) converts the bundle into a natural-language prompt; Qwen Image Edit (diffusers) or the HF Inference API renders a model wearing the outfit.
5. Gemini Nano Banana (`generate_ecommerce_image`, services/gemini_service.py:15) separately cleans uploaded product shots onto white backgrounds.

## 10. Feedback Loops (Analytics)

- **WearLogView** (api/views.py:93) — logging a wear increments the bundle's and each item's `wear_count` / `last_worn`, feeding back into AI candidate ranking.
- **AnalyticsView** (api/views.py:64) — utilization %, most-worn item, average compatibility score of saved bundles, occasion distribution.
- **Deleting an item** marks dependent bundles `has_missing_item=True` (api/views.py:41).

## 11. Marketplace (bundlegeneration.py:123)

Static, pre-seeded `MarketplaceBundle` rows filterable by occasion/style.
`match_percentage` is stored data, **not** computed by the engine.

## 12. Key Files

| Concern | File |
|---|---|
| Scoring, color, styles, bundle & anchor engines | `engine/compatibility_engine.py` |
| AI bundle engine | `ai_generation/services.py`, `ai_generation/views.py` |
| Bundle list / save / marketplace endpoints | `bundlegeneration.py` |
| Merchant / wardrobe anchor endpoints | `bundle_generate/views.py` |
| Avatar + upload flow | `api/views_avatar.py`, `api/views_upload.py` |
| Gemini metadata + image cleaning | `services/gemini_service.py` |
| Avatar image generation (Qwen / HF) | `services/huggingface_service.py` |
| Core models / enums | `api/models.py` |
