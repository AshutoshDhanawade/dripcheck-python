# Authentication App Implementation Plan

This plan details the creation of a new authentication app with custom mobile-number-based signup and login flows, utilizing OTP validation and Bearer tokens.

## User Review Required

- **User Model Approach**: You mentioned keeping `auth.user`. Because you want to login using `mobile_no` instead of `username`, the cleanest approach in Django is to create a Custom User model (extending `AbstractUser`) and set `AUTH_USER_MODEL = 'authentication.User'`. This requires a fresh database if you have already applied migrations for the default `User` model (which appears to be the case since `db.sqlite3` exists). Are you okay with dropping the existing sqlite database and running migrations from scratch to accommodate this? (Or would you prefer to keep the default `User` model, link it to an `AccountProfile` model, and handle the `mobile_no` login through a custom authentication backend?)
- **Token Storage**: You requested to store the Bearer token in the database. Django REST Framework's built-in `TokenAuthentication` does exactly this. I propose using DRF's built-in Token (`rest_framework.authtoken`). Is this acceptable?
- **Login Flow**: For login, should the user provide a **password** along with their mobile number, or should it be an **OTP-based login** (send OTP to mobile, verify OTP to login) again? You didn't mention a password during signup.
- **OTP Provider**: Do you have a specific SMS provider in mind (like Twilio, MSG91, AWS SNS), or should I just print the OTP to the console for development purposes for now?

## Proposed Changes

### `authentication` (New Django App)

Create a new app named `authentication` to handle all auth logic.

#### [NEW] `authentication/models.py`
- Create a `User` model extending `AbstractUser`.
- Add fields:
  - `mobile_no`: `CharField` (Unique, max length 15)
  - `ip_address`: `GenericIPAddressField` (null=True, blank=True)
- Set `is_active = False` by default.
- Set `USERNAME_FIELD = 'mobile_no'`.
- Remove `username` as required field, or manage it automatically.
- Apply `models.Index` on `is_active`, `mobile_no`, and `id`.
- Create an `OTPRecord` model to store temporary OTPs for validation.
  - Fields: `mobile_no`, `otp`, `created_at`.

#### [NEW] `authentication/serializers.py`
- `SignupSerializer`: Validates mobile number format using the `phonenumbers` library to ensure correct length/country code based on the region.
- `VerifyOTPSerializer`: Takes `mobile_no` and `otp`.
- `LoginSerializer`: Takes `mobile_no` (and password/OTP depending on your preference).

#### [NEW] `authentication/views.py`
- `SignupView`: Receives mobile number, validates format, generates an OTP, saves it to the `OTPRecord` model, and "sends" it.
- `VerifyOTPView`: Receives mobile number and OTP. If valid:
  - Creates the User or updates `is_active=True`.
  - Captures the request's IP address and saves it to the user.
  - Deletes the used OTP.
- `LoginView`: Receives mobile number, verifies user exists and `is_active=True`. Generates or retrieves the DRF Auth Token and returns it.

#### [NEW] `authentication/urls.py`
- `POST /auth/signup/`
- `POST /auth/verify-otp/`
- `POST /auth/login/`

### `dripcheck_django/settings.py`

#### [MODIFY] `dripcheck_django/settings.py`
- Add `'authentication'` and `'rest_framework.authtoken'` to `INSTALLED_APPS`.
- Set `AUTH_USER_MODEL = 'authentication.User'`.
- Configure DRF `DEFAULT_AUTHENTICATION_CLASSES` to use `TokenAuthentication`.

## Verification Plan

### Automated Tests
- N/A at this stage.

### Manual Verification
- Attempt to sign up with an invalid mobile number -> Expect validation error from `phonenumbers`.
- Attempt to sign up with a valid mobile number -> Expect success message and OTP generation (printed to console).
- Verify OTP with correct details -> Expect user creation, `is_active=True`, IP address saved. Check DB indexes.
- Login with mobile number -> Expect to receive a Bearer token.
- Test the Bearer token by making a request to a dummy protected endpoint.
