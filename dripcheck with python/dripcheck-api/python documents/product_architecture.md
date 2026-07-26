# Dripcheck Product Architecture

This document provides a high-level overview of the architectural components and technical design of the Dripcheck application.

## 1. System Overview

Dripcheck is an AI-powered digital wardrobe and fashion styling platform. It allows users to upload clothing items, digitize their wardrobe, generate personalized outfit bundles using a custom compatibility engine, and visualize outfits through AI-generated avatars. The architecture is primarily divided into a Frontend client and a Django-based backend API.

## 2. Core Backend Modules (Django)

The backend is composed of the following distinct Django apps:

*   **`dripcheck_django`**: The core configuration module, handling project settings, media configurations, and root URL routing.
*   **`accounts`**: Manages user authentication, Twilio SMS OTP logic, JWT token generation, and the user onboarding flow (questionnaires and profiling).
*   **`api`**: The central app handling Wardrobe management (CRUD), image uploads, avatar generation, user analytics, and wear logs.
*   **`bundle_generate`**: Manages merchant products and handles the dynamic generation of outfit bundles (recommendations based on anchor items, either from the user's wardrobe or the merchant catalog).

## 3. The Compatibility Engine

Located in `engine/compatibility_engine.py`, this is the proprietary logic that evaluates fashion rules. 
When building outfit bundles, it processes combinations through:

1.  **Hard Rejection Rules**: Immediately discards outfits with formality gaps (>= 3 levels), seasonal mismatches, pattern conflicts (e.g., clashing complex patterns), or severe color clashes.
2.  **Scoring System (0-100)**: Awards points based on Occasion Match (+25), Color Harmony (up to +30 based on color families), Pattern Balance, Fit Harmony, Brand Cohesion, and Footwear Presence. It applies penalties for minor formality gaps.
3.  **Dominant Color & Style Tagging**: Assigns the dominant outfit color based on category weights and intelligently applies 15 predefined style profiles (e.g., Streetwear, Minimalist, Techwear, Y2K) if enough rules are matched.

## 4. AI & External Services Integrations

The system heavily utilizes AI for automation and enhancement, orchestrated through the `services/` directory:

*   **`gemini_service`**: 
    *   Extracts highly detailed metadata (color, pattern, fit, occasion) from clothing images using Gemini 2.0 Flash.
    *   Generates enhanced, background-removed e-commerce quality product images using the Nano Banana (Gemini 2.5 Flash Image) API.
*   **`huggingface_service`**: 
    *   Integrates with Qwen/Qwen-Image-Edit to generate personalized avatars wearing the recommended outfit bundles. It builds dynamic prompts based on the user's profile characteristics (skin tone, body type) and the selected clothing items.
*   **`product_link_scraper`**: 
    *   Scrapes public e-commerce URLs to seamlessly import clothing items directly into a user's digital wardrobe, parsing out images and basic text data before passing it to Gemini for inference.
*   **Twilio**: Used for sending OTP SMS messages during the signup and login authentication flows.

## 5. Database Schema (SQLite3)

The primary database entities include:

*   **User & UserProfile**: Stores authentication data, user preferences, avoided colors, and physical attributes.
*   **WardrobeItem**: Represents a digitized piece of clothing. Stores rich metadata (color family, formality, pattern, material) and paths to the original and AI-processed images.
*   **OutfitBundle**: Stores a generated combination of `WardrobeItem`s along with its compatibility score, occasion tags, and style tags.
*   **WearLog**: Tracks which items and bundles the user wears on specific dates, driving the analytics engine.
*   **MerchantProduct**: Represents clothing items sold on the marketplace, which can be recommended to users to complete outfits.

## 6. Media Management

Images are processed through a two-stage pipeline:
1.  **`/media/temp/`**: When a user uploads a product, the original image and the AI-generated preview are saved temporarily.
2.  **`/media/wardrobe/`**: Once the user approves the upload and metadata, the files are moved here permanently.
3.  **`/media/avatars/`**: Stores the AI-generated avatars of users wearing their outfits.
