"""User-facing launcher strings (ages 9+). No jargon."""

from __future__ import annotations

from typing import Any

APP_TITLE = "Morsoul: World's Case"
SYNOPSIS = (
    "Centuries after a catastrophic mana disaster birthed the fantasy world of Agartha, "
    "the scattered consciousness of ancient detective Arthur Conan Doyle awakens inside "
    "an abandoned golem with no memory of his past."
)

# Auth
SIGN_IN = "Login"
REGISTER = "Register"
PLAY_OFFLINE = "Play offline"
USERNAME = "Username"
PASSWORD = "Password"
EMAIL_OPTIONAL = "Email (optional)"
CONFIRM_PASSWORD = "Confirm password"
FORGOT_PASSWORD = "Forgot password?"  # decorative; server has no reset
WRONG_CREDENTIALS = "Wrong username or password"
USERNAME_TAKEN = "That name is already used"
EMAIL_TAKEN = "That email is already used"
RATE_LIMITED = "Too many tries. Please wait {seconds} seconds."
SESSION_EXPIRED = "Please sign in again"
OFFLINE_BANNER = "You are offline. You can still play."
NETWORK_ERROR = "Can't reach the server. You can still play"

# Home
PLAY = "LAUNCH GAME"
SYNC = "Sync"
CHECK_UPDATES = "Check for updates"
GAME_RUNNING = "Running"
UP_TO_DATE = "Up to date"
UPDATE_AVAILABLE = "Update available"
UPDATING = "Updating"
SYNCED = "Synced"
SYNCING = "Syncing"
NEEDS_ATTENTION = "Needs attention"
NOT_SIGNED_IN = "Not signed in"

# Updates
UPDATE_FAILED = "Update failed, your game was not changed"
UPDATE_VERIFY_FAILED = "The update could not be verified. Your game was not changed"
RETRY = "Retry"
CANCEL = "Cancel"

# Progress / sync
MY_PROGRESS = "My Progress"
SYNC_ALL = "Sync all"
SYNC_NOW = "Sync now"
DOWNLOAD_TO_DEVICE = "Download to this device"
THIS_DEVICE_NEWER = "This device is newer"
CLOUD_NEWER = "Cloud is newer"
NEEDS_CHOICE = "Needs a choice"
THIS_DEVICE_ONLY = "This device only"
CLOUD_ONLY = "Cloud only"
LOCAL_INVALID = "This save looks damaged. Nothing was changed"
KEY_UNAVAILABLE = "This device cannot open the save"
PAYLOAD_TOO_LARGE = "This save is too large to upload"
FORBIDDEN_PROFILE = "This progress belongs to another account"
REVISION_CONFLICT = "Your progress differs on two devices. Choose which to keep"
EMPTY_PROFILES = "Your progress will appear here after you save in the game."
DELETE_CLOUD = "Delete cloud copy"
DELETE_CLOUD_CONFIRM = "Delete the cloud copy? This cannot be undone."
KEEP_LOCAL = "Keep this device"
KEEP_CLOUD = "Keep cloud"
DECIDE_LATER = "Decide later"
RESTORE_FROM_CLOUD = "Restore from the cloud"

# Account
ACCOUNT = "Account"
CHANGE_PASSWORD = "Change password"
SIGN_OUT = "Sign out"
SIGN_OUT_ALL = "Sign out of all devices"
PASSWORD_CHANGED = "Password changed. Your other devices were signed out"
WRONG_PASSWORD = "Your current password is not correct"
PASSWORD_MUST_DIFFER = "New password must be different"
OPEN_LOGS = "Open logs folder"
ABOUT = "About"
SERVER_ADDRESS = "Server address"
RESET_SERVER = "Reset to default"

ERRORS: dict[str, str] = {
    "INVALID_CREDENTIALS": WRONG_CREDENTIALS,
    "USERNAME_TAKEN": USERNAME_TAKEN,
    "EMAIL_TAKEN": EMAIL_TAKEN,
    "VALIDATION_ERROR": "Please check the highlighted fields",
    "RATE_LIMITED": RATE_LIMITED,
    "INVALID_SESSION": SESSION_EXPIRED,
    "WRONG_PASSWORD": WRONG_PASSWORD,
    "NETWORK": NETWORK_ERROR,
    "REVISION_CONFLICT": REVISION_CONFLICT,
    "FORBIDDEN_PROFILE": FORBIDDEN_PROFILE,
    "INVALID_SAVE": LOCAL_INVALID,
    "PAYLOAD_TOO_LARGE": PAYLOAD_TOO_LARGE,
    "MANIFEST_INVALID": UPDATE_VERIFY_FAILED,
    "key_unavailable": KEY_UNAVAILABLE,
    "local_invalid": LOCAL_INVALID,
}


def friendly_error(code: str, *, retry_after: int | None = None, details: Any = None) -> str:
    if code == "RATE_LIMITED":
        return RATE_LIMITED.format(seconds=retry_after or 60)
    if code == "VALIDATION_ERROR" and isinstance(details, list) and details:
        first = details[0]
        if isinstance(first, dict) and first.get("message"):
            return str(first["message"])
    return ERRORS.get(code, "Something went wrong. Please try again.")
