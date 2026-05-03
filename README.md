# 営業管理ダッシュボード + 通知システム

営業代行チーム（プレイヤー兼マネージャー）向けの自社製管理ツール。

## 機能

- **記入漏れ通知**: Google Calendar に商談予定があるのに Sheets に活動ログがない場合、本人に LINE / メールで通知
- **停滞案件アラート**: 最終接触から N 日以上動きのない案件を抽出して通知
- **日次/週次サマリ**: 個人とチームの活動・パイプラインを定期通知
- **ダッシュボード**: ローカルで起動する Streamlit。期間切替、ステージ別パイプライン、警告ビュー

## 前提

- macOS / Linux + Python 3.11 以上推奨
- Google アカウント（Sheets と Calendar への読み取り権限）
- LINE Bot（Messaging API のチャネル）
- GitHub アカウント（cron 実行用、無料枠で OK）

## セットアップ

### 1. クローン & インストール

```bash
git clone <repo-url> ~/sales-dashboard
cd ~/sales-dashboard
./install.sh
```

### 2. Google OAuth クライアント作成

1. https://console.cloud.google.com/ で新規プロジェクト
2. APIs & Services → Library で **Google Sheets API** と **Google Calendar API** を有効化
3. APIs & Services → Credentials → Create Credentials → OAuth client ID → **Desktop app**
4. 作成された JSON をダウンロードし、以下に配置:
   ```
   ~/.config/sales-dashboard/credentials.json
   ```

### 3. .env を編集

```bash
cp .env.example .env  # （install.sh が既にやっている場合は不要）
$EDITOR .env
```

最低限埋める項目:
- `OWNER_NAME`, `SHEET_ID_OWNER`, `CALENDAR_ID_OWNER`
- 部下も使う場合: `SUBORDINATE_NAME`, `SHEET_ID_SUBORDINATE`, `CALENDAR_ID_SUBORDINATE`
- シートの実列名: `COL_DATE`, `COL_CUSTOMER`, `COL_OWNER`, `COL_STAGE`, `COL_AMOUNT`, `COL_LAST_CONTACT_DATE`, `COL_NEXT_ACTION_DATE`
- `ACTIVITY_SHEET_NAME`, `DEAL_SHEET_NAME`（実シートのタブ名）

> **シート ID の取得方法**: スプレッドシート URL の `/d/<ここ>/edit` 部分

### 4. LINE Bot 作成

1. https://developers.line.biz/console/ でプロバイダ作成
2. Messaging API のチャネルを作成
3. **Channel access token (long-lived)** を発行
4. 自分・部下が Bot を友達追加
5. Webhook で User ID を取得（または公式の検証ツール）
6. `.env` の `LINE_CHANNEL_ACCESS_TOKEN`, `LINE_USER_ID_OWNER`, `LINE_USER_ID_SUBORDINATE` を埋める

### 5. ダッシュボード起動

デスクトップの「営業ダッシュボード.command」をダブルクリック。
または:

```bash
cd ~/sales-dashboard
.venv/bin/streamlit run dashboard/app.py
```

初回起動時にブラウザが開き、Google 認証 → token.json が保存される。

### 6. cron（クラウド常駐通知）の設定

GitHub にこのリポジトリを push し、以下の Secrets を設定:

| Secret | 内容 |
|---|---|
| `GOOGLE_OAUTH_CREDENTIALS_JSON` | credentials.json の中身を貼る |
| `GOOGLE_OAUTH_TOKEN_JSON` | token.json の中身（ローカル初回認証後に生成される） |
| `SHEET_ID_OWNER`, `SHEET_ID_SUBORDINATE` | シートID |
| `CALENDAR_ID_OWNER`, `CALENDAR_ID_SUBORDINATE` | カレンダーID |
| `OWNER_NAME`, `SUBORDINATE_NAME` | 担当者名 |
| `ACTIVITY_KEYWORDS` | 商談識別キーワード（カンマ区切り） |
| `ACTIVITY_SHEET_NAME`, `DEAL_SHEET_NAME` | シートタブ名 |
| `COL_DATE`, `COL_CUSTOMER`, `COL_OWNER`, `COL_STAGE`, `COL_AMOUNT`, `COL_LAST_CONTACT_DATE`, `COL_NEXT_ACTION_DATE` | 列名 |
| `LINE_CHANNEL_ACCESS_TOKEN`, `LINE_USER_ID_OWNER`, `LINE_USER_ID_SUBORDINATE` | LINE 認証 |
| `NOTIFY_EMAIL_TO`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD` | メール（フォールバック） |

GitHub Actions が JST 9:00 に毎日通知ジョブを実行する。
手動実行は GitHub の **Actions タブ** → workflow_dispatch から。

## 使い方

### ダッシュボード

- サイドバーで期間（今日/今週/先週/今月/カスタム）を選択
- **警告タブ**: 記入漏れ・停滞案件を最上位表示
- **個人タブ**: メンバー別の数字
- **チームタブ**: チーム合計

### 手動でジョブ実行（テスト用）

```bash
.venv/bin/python jobs/missing_logs_check.py
.venv/bin/python jobs/stagnant_deals_check.py
.venv/bin/python jobs/daily_summary.py
.venv/bin/python jobs/weekly_summary.py
```

### テスト

```bash
.venv/bin/python -m pytest tests/ -v
```

## ディレクトリ

```
sales-dashboard/
├── core/              # 共通モジュール（Sheets/Calendar/突合/集計/通知）
├── dashboard/         # Streamlit
├── jobs/              # 定時ジョブスクリプト
├── tests/             # ユニットテスト
└── .github/workflows/ # GitHub Actions cron
```

## 注意

- 部下のカレンダー・スプレッドシートは、本人から閲覧権限の共有を受けてください
- LINE Notify は 2025/3 でサービス終了したため、本ツールは LINE Messaging API を使用
- Google OAuth の token はローカルに保存されます（`~/.config/sales-dashboard/`）。GitHub Secrets に登録する場合は信頼できるリポジトリ（Private）でのみ実施してください
