#!/bin/bash
set -e

cd "$(dirname "$0")"
TOOL_DIR="$(pwd)"

echo "================================="
echo "  営業管理ダッシュボード セットアップ"
echo "================================="
echo ""

# Python 確認
PYTHON=""
for cmd in python3.12 python3.11 python3.10 python3; do
    if command -v "$cmd" &>/dev/null; then
        PYTHON="$cmd"
        break
    fi
done
if [ -z "$PYTHON" ]; then
    echo "❌ Python 3 が見つかりません。Homebrew 等でインストールしてください。"
    exit 1
fi
echo "✓ Python: $($PYTHON --version)"

# venv 作成
if [ ! -d ".venv" ]; then
    echo "▶ 仮想環境を作成中..."
    "$PYTHON" -m venv .venv
fi
source .venv/bin/activate

# 失敗をサイレント化しない（whisper-tool の教訓）
echo "▶ pip 更新..."
python -m pip install --upgrade pip

echo "▶ 依存パッケージをインストール中..."
pip install -r requirements.txt

# import 検証
echo "▶ インストール検証..."
python -c "import streamlit, gspread, googleapiclient, requests, dotenv" || {
    echo "❌ 依存パッケージの import に失敗しました。エラー内容を確認してください。"
    exit 1
}
echo "✓ 依存パッケージ: OK"

# .env がなければテンプレからコピー
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo ""
    echo "📝 .env を作成しました。エディタで開いて値を埋めてください。"
fi

# ランチャーを Desktop に作成
LAUNCHER="$HOME/Desktop/営業ダッシュボード.command"
cat > "$LAUNCHER" << EOF
#!/bin/bash
source "$TOOL_DIR/.venv/bin/activate"
cd "$TOOL_DIR"
streamlit run dashboard/app.py
EOF
chmod +x "$LAUNCHER"
xattr -d com.apple.quarantine "$LAUNCHER" 2>/dev/null || true
echo "✓ デスクトップに「営業ダッシュボード.command」を作成しました"

echo ""
echo "================================="
echo "  セットアップ完了"
echo "================================="
echo ""
echo "次のステップ:"
echo "  1. .env を編集して各種ID・トークンを設定"
echo "  2. Google Cloud Console で OAuth client (Desktop) を作成し credentials.json を配置"
echo "  3. デスクトップの「営業ダッシュボード.command」をダブルクリックで起動"
echo ""
