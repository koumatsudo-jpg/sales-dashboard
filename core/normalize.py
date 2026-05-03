"""文字列正規化ユーティリティ。

人名の表記ゆれを吸収するための関数群。
- Unicode NFKC（装飾文字を標準形に）
- 旧字 → 新字 マッピング
- カタカナ → ひらがな統一
- 空白・記号除去
"""
from __future__ import annotations

import re
import unicodedata


# 旧字 → 新字 マッピング（人名で頻出するもの）
_OLD_TO_NEW = str.maketrans({
    "瀧": "滝",
    "澤": "沢",
    "邊": "辺",
    "邉": "辺",
    "廣": "広",
    "齋": "斎",
    "齊": "斉",
    "髙": "高",
    "﨑": "崎",
    "嶋": "島",
    "槇": "槙",
    "靑": "青",
    "黑": "黒",
    "與": "与",
    "桒": "桑",
    "圓": "円",
    "兒": "児",
    "桒": "桑",
    "藝": "芸",
    "假": "仮",
    "經": "経",
    "舊": "旧",
    "舍": "舎",
    "賣": "売",
    "鐵": "鉄",
    "陷": "陥",
    "靜": "静",
    "靈": "霊",
    "驗": "験",
    "讀": "読",
    "竝": "並",
    "卷": "巻",
    "圖": "図",
    "國": "国",
    "壽": "寿",
    "學": "学",
    "實": "実",
    "寶": "宝",
    "對": "対",
    "屬": "属",
    "盡": "尽",
    "劍": "剣",
    "縣": "県",
    "歲": "歳",
    "歷": "歴",
    "燈": "灯",
    "獸": "獣",
    "畫": "画",
    "當": "当",
    "稻": "稲",
    "聲": "声",
    "肅": "粛",
    "舊": "旧",
    "藥": "薬",
    "蟲": "虫",
    "證": "証",
    "辭": "辞",
    "處": "処",
    "豐": "豊",
    "醫": "医",
    "釋": "釈",
    "鄕": "郷",
    "雙": "双",
    "亂": "乱",
    "戀": "恋",
})


_NOISE_RE = re.compile(r"[\s　・\.\,，、_\-‐ー―〜~（）\(\)\[\]【】「」『』]")
_KATAKANA_RE = re.compile(r"[ァ-ヶ]")


def _katakana_to_hiragana(s: str) -> str:
    out = []
    for ch in s:
        code = ord(ch)
        if 0x30A1 <= code <= 0x30F6:
            out.append(chr(code - 0x60))
        else:
            out.append(ch)
    return "".join(out)


def normalize(s: str) -> str:
    """人名比較用の正規化。

    1. Unicode NFKC（装飾Unicode、全/半角統一）
    2. 旧字 → 新字
    3. カタカナ → ひらがな
    4. 大文字 → 小文字
    5. 空白・記号除去
    """
    if not s:
        return ""
    out = unicodedata.normalize("NFKC", s)
    out = out.translate(_OLD_TO_NEW)
    out = _katakana_to_hiragana(out)
    out = out.lower()
    out = _NOISE_RE.sub("", out)
    return out


def normalize_status(s: str) -> str:
    """ステータス値の正規化。

    - NFKC（半角カナ→全角）
    - 「契約済み」「契約済」「契約完了」「契約完了済」のような語尾揺れを統一
    - 中黒・空白・記号除去
    """
    if not s:
        return ""
    out = unicodedata.normalize("NFKC", s)
    out = _NOISE_RE.sub("", out)
    # 「契約済み」「契約完了」→ "契約済"
    if out.startswith("契約"):
        return "契約済"
    return out
