# Dripcheck API Documentation

This document provides a comprehensive overview of all the available APIs in the Dripcheck application. It is organized by functional modules, with detailed payload and behavior information for all features.

## Authentication APIs (`accounts/urls.py`)

*   **POST `/auth/signup/`**
    *   **Description**: Registers a new user account.
    *   **Payload**: `mobile_no` (String).
    *   **Behavior**: Generates a 6-digit OTP, saves it in the database, and sends it to the user via Twilio SMS.
*   **POST `/auth/verify-otp/`**
    *   **Description**: Verifies the OTP sent to the user during signup or login.
    *   **Payload**: `mobile_no` (String), `otp` (String).
    *   **Behavior**: Validates the OTP. On success, it creates/activates the user, generates JWT access and refresh tokens, stores them, deletes the OTP record, and returns the tokens alongside a `show_onboarding` flag.
*   **POST `/auth/login/`**
    *   **Description**: Authenticates a user and returns a token or session.
    *   **Payload**: `mobile_no` (String).
    *   **Behavior**: Retrieves the user, generates JWT tokens, and returns them along with the user's previously submitted onboarding data.
*   **GET `/auth/onboarding/questions/`**
    *   **Description**: Retrieves the onboarding questionnaire for new users.
    *   **Payload**: None (Requires Authentication via Bearer token).
    *   **Behavior**: Returns all active onboarding questions that the user has not yet answered.
*   **POST `/auth/onboarding/submit/`**
    *   **Description**: Submits the user's answers to the onboarding questions (requires authentication).
    *   **Payload**: `responses` (Dictionary of answers), `full_name` (optional String), `email` (optional String).
    *   **Behavior**: Normalizes and saves the answers. Updates the user profile. If all questions are answered, marks the user as fully onboarded.
*   **POST `/auth/onboarding/public-submit/`**
    *   **Description**: Submits the onboarding answers for public/unauthenticated users.
    *   **Payload**: `mobile_no` (String), `responses` (Dictionary), `full_name` (optional), `email` (optional).
    *   **Behavior**: Looks up the user by mobile number and saves their onboarding responses without requiring a prior login token. Marks the user as onboarded.

## Wardrobe & User APIs (`api/urls.py`)

*   **POST `/api/wardrobe/upload-product`**
    *   **Description**: Uploads a new product image and details to the wardrobe as a preliminary step.
    *   **Payload**: `image` (File), `name` (String), `color` (String), `type` (String), `category` (String), `product_url` (optional), `user_id` (optional).
    *   **Behavior**: Returns a preview containing the original image, an AI-enhanced/background-removed generated image (via Nano Banana API), temporary filenames, and inferred metadata (via Gemini). Does not save to the database yet.
*   **POST `/api/wardrobe/add-product-link`**
    *   **Description**: Scrapes a public product page link to automatically extract the image and details, and adds it to the user's wardrobe.
    *   **Payload**: `url` (String, required), `user_id` (optional).
    *   **Behavior**: Automatically scrapes the URL for images and details, infers wardrobe metadata (using Gemini heuristic fallback), and creates the wardrobe item directly in the database.
*   **POST `/api/wardrobe/approve-product`**
    *   **Description**: Approves or rejects a pending product upload (from the `/upload-product` endpoint).
    *   **Payload**: `approved` (Boolean), `temp_orig_name` (String), `temp_gen_name` (String), `fallback_used` (Boolean), `user_id` (optional), `product` (Dict with metadata).
    *   **Behavior**: If `approved` is true, moves temporary images to permanent storage and creates the WardrobeItem DB entry. If false, cleans up the temporary files from the disk.
*   **POST `/api/wardrobe/generate-avatar`**
    *   **Description**: Generates an avatar wearing a recommended outfit based on a user-uploaded item.
    *   **Payload**: `image` (File), `name`, `color`, `type`, `category`, and optional profile fields (`gender`, `age`, `preferred_style`, `occasion`, `season`, `budget`).
    *   **Behavior**: Extracts metadata, runs the compatibility engine to find matching items from the user's wardrobe, builds a Qwen Image Edit prompt, generates the avatar image (via Hugging Face), saves it to media, and returns the image URL along with the bundle recommendations and compatibility score.
*   **GET `/api/wardrobe/<uuid:user_id>`**
    *   **Description**: Retrieves the complete wardrobe list for a specific user.
    *   **Payload**: None.
    *   **Behavior**: Returns an array of serialized WardrobeItems belonging to the user.
*   **POST `/api/wardrobe/<uuid:user_id>`**
    *   **Description**: Creates a new wardrobe item for the specified user.
    *   **Payload**: Wardrobe item fields (name, category, primary_color, etc.).
    *   **Behavior**: Instantiates and saves a new WardrobeItem with a generated UUID.
*   **PUT `/api/wardrobe/<uuid:user_id>/<str:item_id>`**
    *   **Description**: Updates details of a specific wardrobe item.
    *   **Payload**: Partial WardrobeItem fields.
    *   **Behavior**: Updates the matching item and returns the new data.
*   **DELETE `/api/wardrobe/<uuid:user_id>/<str:item_id>`**
    *   **Description**: Deletes a specific wardrobe item.
    *   **Payload**: None.
    *   **Behavior**: Deletes the item and flags any existing OutfitBundles containing it as having a missing item.
*   **GET `/api/users/<uuid:user_id>`**
    *   **Description**: Retrieves the profile details of a specific user.
*   **PUT `/api/users/<uuid:user_id>`**
    *   **Description**: Updates the user profile details (e.g., skin_tone, body_type, style_vibes).
*   **GET `/api/analytics/<uuid:user_id>`**
    *   **Description**: Retrieves analytics data.
    *   **Behavior**: Calculates and returns `total_items`, `never_worn_count`, `most_worn_item`, `utilization_percentage`, `average_compatibility_score`, and `occasion_distribution`.
*   **GET `/api/wearlog/<uuid:user_id>`**
    *   **Description**: Retrieves the wear history/log for a specific user.
*   **POST `/api/wearlog/<uuid:user_id>`**
    *   **Description**: Records a new wear event.
    *   **Payload**: `bundle_id` (optional), `worn_date`, `occasion_tag`.
    *   **Behavior**: Creates a WearLog entry and increments the `wear_count` for the relevant OutfitBundle and individual WardrobeItems.
*   **POST `/api/logs`**
    *   **Description**: Remote logging endpoint for the frontend.
    *   **Payload**: `level` (String), `message` (String), `url` (String), `stack` (String).
    *   **Behavior**: Logs the frontend messages directly to the backend Python logger.

## Bundle Generation APIs (`api/urls.py` & `bundle_generate/urls.py`)

*   **GET `/api/bundles/<uuid:user_id>`**
    *   **Description**: Retrieves deduplicated outfit bundles for a user.
    *   **Behavior**: Merges previously stored bundles with freshly generated ones using the compatibility engine. Accepts an optional `occasion` query parameter.
*   **POST `/api/bundles/<uuid:user_id>/save`**
    *   **Description**: Saves a specific outfit bundle to the user's profile.
*   **GET `/api/marketplace`**
    *   **Description**: Retrieves marketplace bundles. Supports filtering via `occasion` and `style` query parameters.
*   **GET `/api/bundle-generate/homepage/`**
    *   **Description**: Returns a list of all products from the merchant database to be displayed on the homepage.
    *   **Payload**: Supports an optional `category` query parameter filter.
*   **GET `/api/bundle-generate/homepage/best-selling/`**
    *   **Description**: Returns the top 10 best-selling products from the merchant database based on `sales_count`.
*   **POST `/api/bundle-generate/recommend/`**
    *   **Description**: Generates outfit bundles centered around a selected merchant product.
    *   **Payload**: `product_id` (String), `user_id` (String).
    *   **Behavior**: Identifies missing categories and dynamically completes the outfit using other merchant products. Passes the items through the compatibility engine.
*   **POST `/api/bundle-generate/recommend-from-wardrobe/`**
    *   **Description**: Generates outfit bundles centered around a user's selected wardrobe item.
    *   **Payload**: `item_id` (String), `user_id` (String).
    *   **Behavior**: Uses the user's existing wardrobe item as an anchor and fills the rest of the outfit using merchant products.
