"""通知モジュール: LINE Messaging API + メールフォールバック。

LINE Channel Access Token と User ID が設定されていれば LINE 送信、
なければ（または失敗時は）SMTP メール送信を試みる。
"""
from __future__ import annotations

import smtplib
import sys
from email.mime.text import MIMEText
from email.utils import formatdate

import requests

from .config import Config

LINE_PUSH_URL = "https://api.line.me/v2/bot/message/push"


def send_line(config: Config, user_id: str, message: str) -> bool:
    if not config.line_channel_access_token or not user_id:
        return False
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {config.line_channel_access_token}",
    }
    payload = {"to": user_id, "messages": [{"type": "text", "text": message[:4900]}]}
    try:
        resp = requests.post(LINE_PUSH_URL, headers=headers, json=payload, timeout=10)
        if resp.status_code == 200:
            return True
        print(f"[notify] LINE failed: {resp.status_code} {resp.text}", file=sys.stderr)
    except requests.RequestException as e:
        print(f"[notify] LINE error: {e}", file=sys.stderr)
    return False


def send_email(config: Config, subject: str, body: str, to: str | None = None) -> bool:
    target = to or config.notify_email_to
    if not target or not config.smtp_host or not config.smtp_user or not config.smtp_password:
        return False
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = config.smtp_user
    msg["To"] = target
    msg["Date"] = formatdate(localtime=True)
    try:
        with smtplib.SMTP(config.smtp_host, config.smtp_port, timeout=10) as srv:
            srv.starttls()
            srv.login(config.smtp_user, config.smtp_password)
            srv.send_message(msg)
        return True
    except smtplib.SMTPException as e:
        print(f"[notify] email error: {e}", file=sys.stderr)
        return False


def resolve_recipient(config: Config, fallback_user_id: str = "") -> str:
    """LINE 宛先を解決。グループID が設定されていれば優先、なければ個人 user_id。"""
    return config.line_group_id or fallback_user_id


def notify(config: Config, user_id: str, subject: str, body: str) -> bool:
    """LINE → メールの順で送信を試みる。どちらか1つでも届けば True。

    user_id が空でも config.line_group_id が設定されていればグループ送信。
    """
    target = resolve_recipient(config, user_id)
    if send_line(config, target, body):
        return True
    return send_email(config, subject, body)
