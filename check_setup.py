"""設定確認用スクリプト。
.venv/bin/python check_setup.py で実行する。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from core.config import load_config


def mask(s: str, head: int = 8) -> str:
    if not s:
        return "(未設定)"
    if len(s) <= head:
        return s
    return f"{s[:head]}...({len(s)}文字)"


def main() -> int:
    cfg = load_config()

    print("=" * 50)
    print("  営業管理ダッシュボード セットアップ確認")
    print("=" * 50)
    print()
    print(f"登録メンバー数: {len(cfg.members)}")
    print()

    if not cfg.members:
        print("⚠️  メンバーが0件です。.env で OWNER_NAME と SHEET_ID_OWNER の両方を埋めてください。")
        return 1

    for m in cfg.members:
        print(f"▶ {m.name}")
        print(f"    sheet_id     = {mask(m.sheet_id, 12)}")
        print(f"    calendar_id  = {m.calendar_id or '(未設定)'}")
        print(f"    line_user_id = {mask(m.line_user_id)}")
        sheet_name = m.yomi_sheet_name or cfg.yomi_sheet_name_template.replace("{name}", m.name)
        print(f"    yomi sheet   = {sheet_name}")
        print()

    print("--- 認証ファイル ---")
    cred = Path(cfg.google_credentials_path) if cfg.google_credentials_path else None
    token = Path(cfg.google_token_path) if cfg.google_token_path else None
    print(f"  credentials.json: {'✅ 存在' if cred and cred.exists() else '❌ 未配置'}  ({cred})")
    print(f"  token.json      : {'✅ 存在' if token and token.exists() else '❌ 未生成（初回起動で生成される）'}")
    print()
    print("--- 列マッピング ---")
    cols = cfg.columns
    print(f"  顧客名(B->1)              : {cols.customer}")
    print(f"  初回アポ日(H->7)          : {cols.first_appt_date}")
    print(f"  契約額(税込)(AB->27)      : {cols.contract_amount_inclusive}")
    print()
    print("=" * 50)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
