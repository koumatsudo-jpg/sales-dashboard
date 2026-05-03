"""LINE 通知のテスト送信。

Usage:
    python jobs/test_line.py

LINE_CHANNEL_ACCESS_TOKEN と LINE_GROUP_ID（または LINE_USER_ID_OWNER）が
.env に設定されていれば、テストメッセージを送信する。
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import _runner  # noqa: F401

from core.config import load_config
from core.notify import resolve_recipient, send_line


def main() -> int:
    config = load_config()
    if not config.line_channel_access_token:
        print("[test_line] LINE_CHANNEL_ACCESS_TOKEN が未設定です（.env を確認）")
        return 1

    target = resolve_recipient(
        config,
        fallback_user_id=config.members[0].line_user_id if config.members else "",
    )
    if not target:
        print("[test_line] 送信先が空です（LINE_GROUP_ID か LINE_USER_ID_OWNER を .env に設定してください）")
        return 1

    tz = ZoneInfo(config.timezone)
    now = datetime.now(tz)
    body = (
        f"✅ 営業管理ダッシュボード 接続テスト\n"
        f"時刻: {now.strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"宛先: {'グループ' if config.line_group_id else '個人'}\n\n"
        f"このメッセージが届いていれば LINE 連携は正常です。"
    )
    ok = send_line(config, target, body)
    if ok:
        print(f"[test_line] 送信成功 → {target[:6]}…")
        return 0
    print("[test_line] 送信失敗（Token / 宛先IDを確認）")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
