from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from datetime import datetime, timedelta
import requests as http_requests
import pytz
from backend.config import UPSTOX_API_KEY, UPSTOX_API_SECRET, UPSTOX_REDIRECT_URI
from backend.database.connection import SessionLocal
from backend.database.models import UpstoxToken
from backend.utils.logger import get_logger

router = APIRouter(prefix="/auth")
logger = get_logger(__name__)
IST = pytz.timezone("Asia/Kolkata")


@router.get("/login")
def login():
    """Redirect to Upstox OAuth login page. Open this URL in browser every morning."""
    auth_url = (
        f"https://api.upstox.com/v2/login/authorization/dialog"
        f"?response_type=code"
        f"&client_id={UPSTOX_API_KEY}"
        f"&redirect_uri={UPSTOX_REDIRECT_URI}"
    )
    return RedirectResponse(url=auth_url)


@router.get("/callback")
def callback(code: str = None, error: str = None):
    """Upstox redirects here after login. Exchanges auth code for access token."""
    if error or not code:
        logger.error(f"Upstox OAuth error: {error}")
        return HTMLResponse(content=_page("Login Failed", f"Error: {error}", success=False))

    try:
        response = http_requests.post(
            "https://api.upstox.com/v2/login/authorization/token",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={
                "code": code,
                "client_id": UPSTOX_API_KEY,
                "client_secret": UPSTOX_API_SECRET,
                "redirect_uri": UPSTOX_REDIRECT_URI,
                "grant_type": "authorization_code",
            },
        )
        response.raise_for_status()
        token_data = response.json()
        access_token = token_data["access_token"]

        # Save to DB — delete old tokens first
        db = SessionLocal()
        try:
            db.query(UpstoxToken).delete()
            db.add(UpstoxToken(
                access_token=access_token,
                expires_at=datetime.now(IST) + timedelta(hours=23),
            ))
            db.commit()
        finally:
            db.close()

        # Reload the client singleton so it picks up the new token
        from backend.data.upstox_client import reload_token
        reload_token(access_token)

        logger.info("Upstox token refreshed successfully via /callback")
        return HTMLResponse(content=_page(
            "Login Successful",
            "Upstox token saved. The system will now use real market data. You can close this tab.",
            success=True,
        ))

    except Exception as e:
        logger.error(f"Token exchange failed: {e}")
        return HTMLResponse(content=_page("Token Exchange Failed", str(e), success=False))


@router.get("/status")
def auth_status():
    """Check if a valid token exists."""
    db = SessionLocal()
    try:
        token = db.query(UpstoxToken).order_by(UpstoxToken.id.desc()).first()
        if not token:
            return {"authenticated": False, "message": "No token found. Visit /auth/login"}
        now = datetime.now(IST)
        expires_at = token.expires_at.astimezone(IST)
        if expires_at < now:
            return {"authenticated": False, "message": "Token expired. Visit /auth/login"}
        return {
            "authenticated": True,
            "expires_at": expires_at.isoformat(),
            "expires_in_minutes": int((expires_at - now).total_seconds() / 60),
        }
    finally:
        db.close()


def _page(title: str, message: str, success: bool) -> str:
    color = "#22c55e" if success else "#ef4444"
    icon = "✓" if success else "✗"
    return f"""
    <html><head><title>{title}</title></head>
    <body style="background:#0f1117;color:#e2e8f0;font-family:system-ui;
                 display:flex;align-items:center;justify-content:center;height:100vh;margin:0">
      <div style="text-align:center;padding:40px;background:#1a1f2e;border-radius:16px;
                  border:1px solid #2d3748;max-width:480px">
        <div style="font-size:48px;color:{color};margin-bottom:16px">{icon}</div>
        <h2 style="color:{color};margin:0 0 12px">{title}</h2>
        <p style="color:#94a3b8;line-height:1.6">{message}</p>
      </div>
    </body></html>
    """
