"""Email sender using Resend (https://resend.com).

Free tier: 100 emails/day, 3000/month. No passwords needed — just an API key.

Setup:
1. Sign up at https://resend.com (free, GitHub login works)
2. Add and verify your domain, OR use the free onboarding@resend.dev sender
3. Create an API key at https://resend.com/api-keys
4. Set RESEND_API_KEY as an environment variable (or GitHub Secret)
5. Set RECIPIENT_EMAIL to your email address
"""

from __future__ import annotations

import logging
import os

import resend

logger = logging.getLogger(__name__)


def send_digest(
    subject: str,
    html_body: str,
    config: dict,
) -> bool:
    """Send the digest email via Resend.

    Required environment variables:
        RESEND_API_KEY: Your Resend API key
        RECIPIENT_EMAIL: Where to send the digest
    """
    api_key = os.environ.get("RESEND_API_KEY")
    recipient = os.environ.get("RECIPIENT_EMAIL")

    if not api_key:
        logger.error(
            "Email not configured. Set RESEND_API_KEY.\n"
            "  1. Sign up at https://resend.com (free)\n"
            "  2. Create an API key at https://resend.com/api-keys\n"
            "  3. Set it as RESEND_API_KEY"
        )
        return False

    if not recipient:
        logger.error("No recipient. Set RECIPIENT_EMAIL environment variable.")
        return False

    resend.api_key = api_key

    # Use custom domain if set, otherwise use Resend's free onboarding sender
    sender = os.environ.get(
        "SENDER_EMAIL", "Econ Updater <onboarding@resend.dev>"
    )

    try:
        params: resend.Emails.SendParams = {
            "from": sender,
            "to": [recipient],
            "subject": subject,
            "html": html_body,
        }

        email = resend.Emails.send(params)
        logger.info(f"Digest sent to {recipient} (id: {email.get('id', '?')})")
        return True
    except Exception as e:
        logger.error(f"Failed to send email: {e}")
        return False
