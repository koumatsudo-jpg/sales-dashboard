"""Google OAuth フロー：Sheets と Calendar 共通。

初回はブラウザが立ち上がって認可 → token.json 保存。
2回目以降は token.json から自動でリフレッシュ。
"""
from __future__ import annotations

from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",  # 書き込み権限（ステータス更新用）
    "https://www.googleapis.com/auth/calendar.readonly",
]


def get_credentials(credentials_path: str, token_path: str) -> Credentials:
    """OAuth credentials を取得・更新する。"""
    cred_file = Path(credentials_path).expanduser()
    token_file = Path(token_path).expanduser()
    token_file.parent.mkdir(parents=True, exist_ok=True)

    creds: Credentials | None = None
    if token_file.exists():
        creds = Credentials.from_authorized_user_file(str(token_file), SCOPES)

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        token_file.write_text(creds.to_json())
        return creds

    if not cred_file.exists():
        raise FileNotFoundError(
            f"Google OAuth credentials not found at {cred_file}.\n"
            "Google Cloud Console で OAuth client (Desktop App) を作り、"
            "credentials.json を配置してください。"
        )

    flow = InstalledAppFlow.from_client_secrets_file(str(cred_file), SCOPES)
    creds = flow.run_local_server(port=0)
    token_file.write_text(creds.to_json())
    return creds
