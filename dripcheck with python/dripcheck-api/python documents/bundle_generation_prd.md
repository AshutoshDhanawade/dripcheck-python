# Bundle Generation API - Product Requirements Document (PRD)

## Overview
The Bundle Generation API is the core intelligence of the Dripcheck application. It programmatically generates personalized outfit combinations (bundles) from a user's wardrobe and merchant products. The engine evaluates thousands of combinations and scores them based on established fashion rules, ensuring that users receive stylish, harmonious, and situation-appropriate outfit suggestions.

## Core Endpoints

1.  **Generate Personal Bundles** (`GET /api/bundles/<user_id>`)
    *   **Purpose**: Delivers the top 10 best-scoring outfit bundles tailored to the user.
    *   **Mechanism**: Merges any previously saved bundles with newly generated ones. It dynamically runs the Compatibility Engine on the user's current wardrobe, filtering out colors the user prefers to avoid, and filtering by `occasion` if requested.

2.  **Generate Recommendation from Merchant Product** (`POST /api/bundle-generate/recommend/`)
    *   **Purpose**: Creates outfits centered around a specific merchant product.
    *   **Mechanism**: The engine takes the selected product as an "anchor." It identifies missing categories (e.g., if the anchor is a Top, it looks for Bottoms and Footwear) from the merchant database and generates complete outfits.

3.  **Generate Recommendation from Wardrobe Item** (`POST /api/bundle-generate/recommend-from-wardrobe/`)
    *   **Purpose**: Helps a user figure out how to style a specific item they already own.
    *   **Mechanism**: Uses the user's wardrobe item as the anchor and completes the outfit using items from the merchant catalog.

---

## Compatibility Engine Logic & Rules

The magic behind the bundle generation lies in the `compatibility_engine.py`. When forming an outfit (Top, Bottom, Footwear, and an optional Layer), the engine applies a series of **Hard Rejections** (immediate disqualification) followed by a **Scoring System** (0 to 100).

### 1. Hard Rejection Rules
If any of these conditions are met, the outfit combination is immediately discarded (Score = 0):

*   **R1: Formality Gap**: 
    *   *Rule*: The difference between the highest and lowest formality levels of items in the outfit cannot be 3 or greater (e.g., formal dress shoes with sweatpants).
*   **R2: Season Mismatch**: 
    *   *Rule*: An outfit cannot mix items meant for specifically different seasons (e.g., a heavy winter coat with summer shorts). Items marked as "All-season" are exempt.
*   **R3: Pattern Conflict**: 
    *   *Rule*: An outfit cannot have more than one "Graphic" patterned item. Additionally, an outfit cannot have 2 or more "complex" patterns (Stripes, Checks, Floral, Abstract) clashing with each other.
*   **R4: Color Clash**: 
    *   *Rule*: Colors are categorized into families (Neutral, Earth, Dark, Bold, Pastel, Warm). The engine pairs these families to determine harmony. A "Bold + Bold" or "Bold + Pastel" combination results in an immediate hard reject (Tier 0 harmony).

### 2. Scoring System (Max 100 points)
If an outfit passes the hard rejections, it starts with a base score and earns points based on the following criteria:

*   **Occasion Match (+25 points)**: 
    *   Awarded if all items in the outfit share at least one common occasion tag (e.g., they are all suitable for "Casual" or "Night Out").
*   **Color Harmony (Up to +30 points)**: 
    *   **+30 points** for Tier 1 combinations (e.g., Earth + Warm, Dark + Earth).
    *   **+20 points** for Tier 2 combinations (e.g., Neutral + Neutral, Earth + Earth, Monochrome).
    *   **+10 points** for Tier 3 combinations (e.g., Bold + Neutral, Pastel + Neutral).
*   **Pattern Balance (Up to +15 points)**: 
    *   **+15 points** if exactly one item has a pattern (providing a focal point).
    *   **+10 points** if all items are solid (minimalist balance).
*   **Fit Harmony (+10 or -10 points)**: 
    *   **+10 points** for pairing an Oversized top with a Slim/Tapered bottom (balanced silhouette).
    *   **-10 points penalty** for pairing an Oversized top with a Baggy/Oversized bottom (unless overridden by a specific streetwear style).
*   **Brand Cohesion (+5 points)**: 
    *   Awarded if at least two items in the outfit share the same brand.
*   **Footwear Presence (+5 points)**: 
    *   Awarded simply for including footwear, ensuring the outfit is complete.
*   **Minor Formality Penalty (-15 points)**: 
    *   If the formality gap between items is exactly 2, a 15-point penalty is applied. However, items tagged as "versatile" or "smart casual" are exempt from this penalty, allowing for stylish high-low fashion mixing.

### 3. Dominant Color & Style Tagging
After an outfit is successfully generated and scored, the engine applies descriptive metadata:

*   **Dominant Color Calculation**: Weights are assigned by category (Tops and Bottoms carry a weight of 3, Layers 2, Footwear 1, Accessories 0.5). The color with the highest cumulative weight becomes the outfit's dominant color.
*   **Style Tag Assignment**: The engine evaluates the outfit against 15 predefined style profiles (e.g., Minimalist, Streetwear, Vintage/Retro, Techwear). If an outfit meets at least 50% of a style's rules (based on color, fit, pattern, and material), that style tag is assigned to the bundle.

## Summary of the User Flow

1.  **Request**: The client requests bundles (e.g., for a "Date Night").
2.  **Filter**: The engine filters the user's wardrobe, removing colors the user hates and items not suitable for "Date Night".
3.  **Combine**: It generates every possible combination of Tops, Bottoms, and Shoes.
4.  **Evaluate**: It runs the combinations through the Hard Rejects and Scoring Rules. It then tries adding a Layer to see if it improves the score.
5.  **Rank & Return**: The combinations are sorted by score. The top 10 are tagged with dominant colors and style names, assigned a unique ID, and returned to the client as beautiful, ready-to-wear outfit recommendations.
