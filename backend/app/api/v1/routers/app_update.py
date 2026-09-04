"""Lets the Android app ask "is there a newer native build than mine?"
without needing a cable — see docs/ANDROID_APP.md for the full picture.
The APK itself still can't self-install (Android requires an explicit tap
from the user, no app can silently install another APK over itself), but
everything up to that point — checking, prompting, downloading — can run
from inside the app the same way any other page does, since this is a
plain unauthenticated GET the WebView can call on every launch.

Unconfigured (no ANDROID_LATEST_VERSION_CODE set) means "no update
tracked yet" — same graceful-degradation shape as every other optional
feature in this app (SMTP/Claude/Firebase/the keyed job-search
providers): the frontend just never shows the update banner.
"""

from fastapi import APIRouter

from app.core.config import settings
from app.schemas.app_update import AndroidUpdateInfo

router = APIRouter(prefix="/app", tags=["app"])


@router.get("/android-update", response_model=AndroidUpdateInfo)
async def get_android_update_info() -> AndroidUpdateInfo:
    return AndroidUpdateInfo(
        version_code=settings.ANDROID_LATEST_VERSION_CODE,
        version_name=settings.ANDROID_LATEST_VERSION_NAME,
        apk_url=settings.ANDROID_UPDATE_APK_URL,
        notes=settings.ANDROID_UPDATE_NOTES,
    )
