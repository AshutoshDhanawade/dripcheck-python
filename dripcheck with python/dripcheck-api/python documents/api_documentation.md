# Dripcheck API Documentation

This document provides a comprehensive overview of all the available APIs in the Dripcheck application. It is organized by functional modules.

## Authentication APIs (`accounts/urls.py`)

*   **POST `/auth/signup/`**
    *   **Description**: Registers a new user account.
*   **POST `/auth/verify-otp/`**
    *   **Description**: Verifies the OTP sent to the user during signup or login.
*   **POST `/auth/login/`**
    *   **Description**: Authenticates a user and returns a token or session.
*   **GET `/auth/onboarding/questions/`**
    *   **Description**: Retrieves the onboarding questionnaire for new users.
*   **POST `/auth/onboarding/submit/`**
    *   **Description**: Submits the user's answers to the onboarding questions (requires authentication).
*   **POST `/auth/onboarding/public-submit/`**
    *   **Description**: Submits the onboarding answers for public/unauthenticated users.

## Wardrobe & User APIs (`api/urls.py`)

*   **POST `/api/wardrobe/upload-product`**
    *   **Description**: Uploads a new product image/details to the wardrobe.
*   **POST `/api/wardrobe/add-product-link`**
    *   **Description**: Adds a product to the wardrobe via a product link.
*   **POST `/api/wardrobe/approve-product`**
    *   **Description**: Approves a pending product addition.
*   **POST `/api/wardrobe/generate-avatar`**
    *   **Description**: Generates an avatar based on user inputs.
*   **GET `/api/wardrobe/<str:user_id>`**
    *   **Description**: Retrieves the complete wardrobe list for a specific user.
*   **POST `/api/wardrobe/<str:user_id>`**
    *   **Description**: Creates a new wardrobe item for the specified user.
*   **GET `/api/wardrobe/<str:user_id>/<str:item_id>`**
    *   **Description**: Retrieves details of a specific wardrobe item.
*   **GET `/api/users/<str:user_id>`**
    *   **Description**: Retrieves the profile details of a specific user.
*   **GET `/api/analytics/<str:user_id>`**
    *   **Description**: Retrieves analytics data (e.g., wardrobe usage, preferred colors) for a specific user.
*   **GET `/api/wearlog/<str:user_id>`**
    *   **Description**: Retrieves the wear history/log for a specific user.

## Bundle Generation APIs (`api/urls.py` & `bundle_generate/urls.py`)

*   **GET `/api/bundles/<str:user_id>`**
    *   **Description**: Retrieves up to 10 deduplicated outfit bundles for a user. Merges previously stored bundles with freshly generated ones using the compatibility engine. Accepts an optional `occasion` query parameter.
*   **POST `/api/bundles/<str:user_id>/save`**
    *   **Description**: Saves a specific outfit bundle to the user's profile.
*   **GET `/api/marketplace`**
    *   **Description**: Retrieves marketplace bundles. Supports filtering via `occasion` and `style` query parameters.
*   **GET `/api/bundle-generate/homepage/`**
    *   **Description**: Returns a list of all products from the merchant database to be displayed on the homepage. Supports an optional `category` filter.
*   **GET `/api/bundle-generate/homepage/best-selling/`**
    *   **Description**: Returns the top 10 best-selling products from the merchant database based on sales count.
*   **POST `/api/bundle-generate/recommend/`**
    *   **Description**: Generates outfit bundles centered around a selected merchant product (provided via `product_id`). It selects complementary items from missing categories to create a full outfit.
*   **POST `/api/bundle-generate/recommend-from-wardrobe/`**
    *   **Description**: Generates outfit bundles centered around a user's selected wardrobe item (provided via `item_id`). It fills the rest of the outfit using merchant products.

## System APIs

*   **GET `/api/logs`**
    *   **Description**: Retrieves frontend logs for debugging or monitoring.
