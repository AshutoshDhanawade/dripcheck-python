# Bundle Generation Logic

The Bundle Generation Engine is the core intelligence of Dripcheck. It programmatically generates personalized, harmonious outfit combinations by evaluating thousands of potential permutations of a user's wardrobe (and merchant products) against strict fashion rules. 

Here is a detailed, step-by-step explanation of how the algorithm works, followed by a concrete example to illustrate the process.

---

## 1. How the Engine Works (Step-by-Step)

### Phase 1: Filtering & Preparation
1. **User Preferences**: The engine looks at the user's profile and immediately filters out any wardrobe items that match the user's "avoided colors" (both exact colors and broad color families).
2. **Occasion Filtering**: If the request specifies an occasion (e.g., "Date Night" or "Casual"), the engine filters the pool to only include items tagged appropriately.
3. **Categorization**: The remaining valid items are grouped into `Tops`, `Bottoms`, `Footwear`, and `Layers`.

### Phase 2: Base Combination & Hard Rejections
The engine generates all possible 3-piece combinations (`Top` + `Bottom` + `Footwear`). For every combination, it runs a gauntlet of **Hard Rejection Rules**. If a combination fails *any* of these, it is immediately discarded (Score = 0):
*   **Formality Gap (R1)**: The difference between the highest and lowest formality levels of items cannot be 3 or greater (e.g., formal dress shoes [Level 5] with sweatpants [Level 1]).
*   **Season Mismatch (R2)**: Cannot mix items meant for strictly different seasons (e.g., a heavy winter coat with summer shorts). "All-season" items are exempt.
*   **Pattern Conflict (R3)**: Discards outfits with more than one "Graphic" item, or outfits with 2 or more clashing complex patterns (Stripes, Checks, Floral, Abstract).
*   **Color Clash (R4)**: Color families (Neutral, Earth, Dark, Bold, Pastel, Warm) are paired. Known terrible combinations like "Bold + Bold" or "Bold + Pastel" result in immediate rejection.

### Phase 3: Scoring System (Max 100 points)
If an outfit survives the hard rejections, it starts with 0 points and earns points based on fashion harmony:
*   **Occasion Match (+25 points)**: Awarded if *all* items in the outfit share at least one common occasion tag.
*   **Color Harmony (Up to +30 points)**: 
    *   **Tier 1 (+30)**: Exceptional combinations (e.g., Earth + Warm, Dark + Earth).
    *   **Tier 2 (+20)**: Safe/Solid combinations (e.g., Neutral + Neutral, Monochrome).
    *   **Tier 3 (+10)**: Acceptable combinations (e.g., Bold + Neutral).
*   **Pattern Balance (Up to +15 points)**: Exactly 1 patterned item (+15) provides a focal point. 0 patterned items (+10) provides minimalist balance.
*   **Fit Harmony (+10 or -10 points)**: (+10) for Oversized top + Slim/Tapered bottom. (-10) for Oversized top + Baggy bottom.
*   **Brand Cohesion (+5 points)**: If at least two items share the same brand.
*   **Footwear Presence (+5 points)**: For successfully including shoes.
*   **Minor Formality Penalty (-15 points)**: If the formality gap is exactly 2, it applies a penalty *unless* the items are tagged as "versatile" or "smart casual" (allowing for stylish high-low fashion).

### Phase 4: Layer Optimization
After scoring the 3-piece outfit, the engine iterates through available `Layer` items (jackets, hoodies, overshirts). It temporarily adds a layer to the outfit and recalculates the score. If adding a specific layer increases the overall score (e.g., by introducing a Tier 1 color match or brand cohesion), that layer is permanently added to the bundle.

### Phase 5: Metadata Assignment & Ranking
*   **Dominant Color**: Weights are applied (Top=3, Bottom=3, Layer=2, Shoe=1). The color with the highest cumulative weight becomes the outfit's primary color.
*   **Style Tagging**: The engine evaluates the outfit against 15 predefined style profiles (e.g., *Minimalist*, *Streetwear*, *Techwear*). If an outfit meets the specific criteria for a profile, it is tagged.
*   **Ranking**: All valid combinations are sorted descending by their final score. The top configurations are assigned unique IDs and returned.

---

## 2. A Concrete Example Walkthrough

Let's assume a user requests a **"Casual"** outfit.

**The Wardrobe Pool (Filtered for "Casual"):**
1.  `Item A`: White Cotton T-Shirt (Top, Neutral, Solid, Regular fit, Formality 3)
2.  `Item B`: Navy Blue Chinos (Bottom, Dark, Solid, Slim fit, Formality 5, tagged "smart casual")
3.  `Item C`: Neon Green Board Shorts (Bottom, Bold, Solid, Relaxed fit, Formality 1)
4.  `Item D`: White Leather Sneakers (Shoe, Neutral, Solid, Regular fit, Formality 4)
5.  `Item E`: Camel Overcoat (Layer, Earth, Solid, Regular fit, Formality 4)

### Step 1: Evaluating Base Combinations
The engine tests combinations. Let's look at two specific ones:

**Combination 1: T-Shirt + Board Shorts + Sneakers (Items A + C + D)**
*   **Hard Rejection Check**:
    *   Formality Gap: Sneakers (4) - Board Shorts (1) = 3. 
    *   *Result*: **REJECTED**. Formality gap is >= 3. The outfit is immediately discarded.

**Combination 2: T-Shirt + Chinos + Sneakers (Items A + B + D)**
*   **Hard Rejection Check**:
    *   Formality Gap: Chinos (5) - T-Shirt (3) = 2. (Pass)
    *   Season/Pattern/Color: All solid, Neutral + Dark colors. (Pass)
*   **Scoring Combination 2**:
    *   *Occasion Match*: All are "Casual" -> **+25**
    *   *Color Harmony*: Neutral + Dark = Tier 3 -> **+10**
    *   *Pattern Balance*: 0 patterns -> **+10**
    *   *Fit Harmony*: None are oversized -> **0**
    *   *Brand Cohesion*: Different brands -> **0**
    *   *Footwear Presence*: Has sneakers -> **+5**
    *   *Formality Penalty*: Gap is 2 (5-3), but Chinos have the "smart casual" tag, exempting the penalty -> **0**
    *   **Base Score = 50 / 100**

### Step 2: Layer Optimization
The engine tries adding the **Camel Overcoat (Item E)** to Combination 2.
*   **New Combo**: T-Shirt + Chinos + Sneakers + Camel Overcoat
*   **Re-evaluating Color Harmony**: The Camel Overcoat is "Earth", and the Chinos are "Dark". Earth + Dark = Tier 1 Harmony!
*   **New Score Calculation**:
    *   Occasion Match -> **+25**
    *   Color Harmony (Tier 1) -> **+30** *(up from +10)*
    *   Pattern Balance (0 patterns) -> **+10**
    *   Footwear Presence -> **+5**
    *   **New Score = 70 / 100**
*   *Result*: Because 70 > 50, the engine selects the 4-piece layered outfit over the 3-piece version.

### Step 3: Metadata Assignment
*   **Dominant Color**: 
    *   White (Top=3 + Shoe=1 = 4 weight)
    *   Navy (Bottom=3 = 3 weight)
    *   Camel (Layer=2 = 2 weight)
    *   *Result*: **White** is assigned as the dominant color.
*   **Style Tagging**: The outfit consists entirely of solids, neutral/dark/earth colors, and no oversized fits. The engine evaluates this against its rule definitions and successfully assigns the **"Minimalist"** and **"Classic/Timeless"** tags.

### Final Output
The user is presented with a highly-rated (70/100) 4-piece outfit (T-Shirt, Chinos, Sneakers, Camel Overcoat) tagged as a *Minimalist* look with *White* as the dominant color.
