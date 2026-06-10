# Human-readable errors for Gemini Live connection failures.

import socket


def format_gemini_connect_error(err: BaseException) -> str:
    msg = str(err)
    name = type(err).__name__

    if isinstance(err, OSError) and getattr(err, "errno", None) == 8:
        return (
            "Cannot reach generativelanguage.googleapis.com (DNS lookup failed). "
            "Check your internet connection and VPN. If this only happens while "
            "uvicorn is running, restart with: "
            "uvicorn backend.main:app --port 8000 --loop asyncio"
        )

    if "nodename nor servname" in msg or "Name or service not known" in msg:
        return (
            "Cannot resolve generativelanguage.googleapis.com. "
            "Check network/DNS, disable VPN, or restart uvicorn with --loop asyncio."
        )

    if "1008" in msg or "BidiGen" in msg or "policy violation" in msg.lower():
        return (
            "Gemini Live API rejected the connection (policy violation). "
            "Your API key may not have Live API access yet. "
            "Test the same key at https://aistudio.google.com/live — if that fails, "
            "enable billing / Live API on your Google AI project and try a fresh key."
        )

    if "API key" in msg or "api key" in msg.lower() or "401" in msg or "403" in msg:
        return f"Gemini authentication failed: {msg}. Check GEMINI_API in .env."

    return f"Gemini Live connection failed ({name}): {msg}"


def check_dns() -> None:
    """Raise OSError if Gemini API host cannot be resolved."""
    socket.getaddrinfo("generativelanguage.googleapis.com", 443)
