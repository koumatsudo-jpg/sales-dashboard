"""営業管理ダッシュボード — SFA Dashboard B案（ストーリーフロー）実装。

Salesforce Lightning 配色 + ナラティブ構成:
1. ステータスバナー（1文で今月を要約）
2. 7セル KPI ストリップ（ペース基準マーカー入り進捗バー）
3. 累積線（実績/理想ペース/着地予測） + 週別バー
"""
from __future__ import annotations

import calendar
import json
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import altair as alt
import pandas as pd
import streamlit as st


# ──────────────────────────────────────────────
# Streamlit Cloud secrets → os.environ ブリッジ
# ローカルでは .env、クラウドでは st.secrets を使えるように両対応
# ──────────────────────────────────────────────
def _bridge_secrets() -> None:
    try:
        secrets = dict(st.secrets)  # ファイル無いと例外
    except Exception:
        return
    for key, value in secrets.items():
        if key in ("GOOGLE_OAUTH_CREDENTIALS_JSON", "GOOGLE_OAUTH_TOKEN_JSON"):
            # JSON 内容を /tmp に書き出してパスを env に通す
            target_dir = Path("/tmp/sales-dashboard")
            target_dir.mkdir(parents=True, exist_ok=True)
            filename = "credentials.json" if "CREDENTIALS" in key else "token.json"
            path = target_dir / filename
            content = value if isinstance(value, str) else json.dumps(dict(value))
            path.write_text(content)
            env_key = "GOOGLE_OAUTH_CREDENTIALS" if "CREDENTIALS" in key else "GOOGLE_OAUTH_TOKEN"
            os.environ.setdefault(env_key, str(path))
        elif isinstance(value, str):
            os.environ.setdefault(key, value)


_bridge_secrets()

from core.aliases import AliasMap
from core.analytics import aggregate_member, aggregate_team
from core.calendar_client import fetch_events
from core.config import load_config
from core.dismissals import (
    dismiss_missing,
    dismiss_stagnant,
    get_dismissed,
    missing_log_id,
    restore_missing,
    restore_stagnant,
    stagnant_id,
)
from core.matcher import find_data_inconsistencies, find_missing_logs, find_stagnant_deals
from core.models import deal_to_activity_logs
from core.period_kpi import compute_period_kpi, daily_series, month_periods
from core.sheets import fetch_deals, update_current_status
from core.target_overrides import (
    apply_overrides,
    load_overrides,
    save_overrides,
    upsert_member,
)
from core.targets import Targets, fetch_targets


# ──────────────────────────────────────────────
# Theme tokens (Salesforce Lightning 配色)
# ──────────────────────────────────────────────
SF_BLUE = "#0070d2"
SF_BLUE_BG = "#eaf5fe"
SF_GREEN = "#2e844a"
SF_GREEN_SOFT = "#e8f5e9"
SF_GREEN_BG = "#cdefc4"
SF_YELLOW = "#fe9339"
SF_YELLOW_BG = "#fff5e7"
SF_RED = "#ea001e"
SF_RED_SOFT = "#fce8e7"
SF_RED_BG = "#fdd9d7"
SF_INK = "#16191e"
SF_TEXT2 = "#3e3e3c"
SF_TEXT3 = "#5e6a72"
SF_BORDER = "#dddbda"
SF_BORDER_LIGHT = "#ecebea"
SF_BG_PANEL = "#fafaf9"
SF_TEAM_NAVY = "#16325c"

THRESHOLDS = {
    "default": [(1.00, SF_GREEN), (0.70, SF_BLUE), (0.40, SF_YELLOW), (0.0, SF_RED)],
    "strict": [(1.00, SF_GREEN), (0.85, SF_BLUE), (0.60, SF_YELLOW), (0.0, SF_RED)],
    "loose": [(0.90, SF_GREEN), (0.60, SF_BLUE), (0.30, SF_YELLOW), (0.0, SF_RED)],
}

st.set_page_config(page_title="SFA Dashboard", layout="wide", initial_sidebar_state="collapsed")
config = load_config()
tz = ZoneInfo(config.timezone)
aliases = AliasMap.load(config.aliases_path)
RO = config.read_only  # 閲覧専用モード（クラウドデプロイ時に True）


# ──────────────────────────────────────────────
# CSS
# ──────────────────────────────────────────────
st.markdown(f"""
<style>
  .block-container {{ padding-top: 3rem; padding-bottom: 2rem; max-width: 1440px; }}
  body, .stApp {{ background: #f3f3f3; color: {SF_INK}; }}
  .sfa-header {{
    background: {SF_TEAM_NAVY}; color: #fff; padding: 12px 20px; border-radius: 6px;
    display: flex; align-items: center; gap: 16px; margin-bottom: 14px;
  }}
  .sfa-logo {{
    width: 28px; height: 28px; border-radius: 6px; background: #fff;
    display: flex; align-items: center; justify-content: center;
    color: {SF_TEAM_NAVY}; font-weight: 800; font-size: 13px;
  }}
  .sfa-card {{
    background: #fff; border: 1px solid {SF_BORDER}; border-radius: 8px;
    padding: 18px 20px; box-shadow: 0 1px 2px rgba(0,0,0,.04);
    margin-bottom: 14px;
  }}
  .sfa-card-title {{ font-size: 13px; font-weight: 700; color: {SF_INK}; margin-bottom: 4px; }}
  .sfa-card-sub   {{ font-size: 11px; color: {SF_TEXT3}; margin-bottom: 14px; }}
  .sfa-banner {{
    border-radius: 8px; padding: 18px 22px; display: flex; align-items: center; gap: 22px;
    border: 1px solid; border-left-width: 4px; margin-bottom: 14px;
  }}
  .sfa-banner-pct {{
    width: 64px; height: 64px; border-radius: 32px; flex: 0 0 auto;
    display: flex; align-items: center; justify-content: center;
    font-size: 24px; font-weight: 800;
  }}
  .sfa-banner-text {{ font-size: 17px; font-weight: 700; line-height: 1.45; color: {SF_INK}; }}
  .sfa-banner-meta {{ font-size: 12px; color: {SF_TEXT3}; margin-top: 6px; }}
  .sfa-kpi-strip {{
    background: #fff; border: 1px solid {SF_BORDER}; border-radius: 8px; overflow: hidden;
    display: grid; grid-template-columns: repeat(7, 1fr); margin-bottom: 14px;
  }}
  .sfa-kpi-cell {{ padding: 14px 16px; border-right: 1px solid {SF_BORDER_LIGHT}; }}
  .sfa-kpi-cell.hl {{ background: {SF_BG_PANEL}; }}
  .sfa-kpi-cell:last-child {{ border-right: none; }}
  .sfa-kpi-row1 {{
    display: flex; justify-content: space-between; align-items: center;
    font-size: 11px; color: {SF_TEXT3}; font-weight: 600; margin-bottom: 6px;
  }}
  .sfa-kpi-pct  {{ font-size: 10px; font-weight: 700; }}
  .sfa-kpi-num  {{ font-size: 22px; font-weight: 700; color: {SF_INK}; line-height: 1.1; letter-spacing: -.02em; }}
  .sfa-kpi-tgt  {{ font-size: 10px; color: {SF_TEXT3}; margin-top: 3px; }}
  .sfa-kpi-bar  {{
    height: 4px; background: {SF_BORDER_LIGHT}; border-radius: 2px;
    margin-top: 8px; position: relative; overflow: visible;
  }}
  .sfa-kpi-bar-fill {{ height: 100%; border-radius: 2px; }}
  .sfa-kpi-bar-pace {{ position: absolute; top: -2px; bottom: -2px; width: 2px; background: {SF_TEXT2}; }}
  .sfa-warn-card {{
    background: #fff; border: 1px solid {SF_BORDER}; border-radius: 8px;
    padding: 16px 18px; box-shadow: 0 1px 2px rgba(0,0,0,.04);
  }}
  #MainMenu, footer {{ visibility: hidden; }}
</style>
""", unsafe_allow_html=True)


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────
def _color_for(actual: float, target: float, threshold_key: str = "default", pace_ratio: float | None = None) -> str:
    if not target:
        return SF_TEXT3
    base = actual / target
    ratio = base / pace_ratio if pace_ratio else base
    for thr, c in THRESHOLDS[threshold_key]:
        if ratio >= thr:
            return c
    return SF_RED


def _color_bg(actual: float, target: float) -> str:
    if not target:
        return SF_BG_PANEL
    r = actual / target
    if r >= 1.0:
        return SF_GREEN_BG
    if r >= 0.7:
        return SF_BLUE_BG
    if r >= 0.4:
        return SF_YELLOW_BG
    return SF_RED_BG


def _yen_short(v: float) -> str:
    v = v or 0
    if v >= 100_000_000:
        return f"¥{v/100_000_000:.2f}億"
    if v >= 10_000:
        return f"¥{v/10_000:,.1f}万"
    return f"¥{v:,.0f}"


def _progress_bar_html(actual: float, target: float, pace_ratio: float | None, threshold_key: str, height: int = 4) -> str:
    pct = min(actual / target * 100, 100) if target else 0
    pace_pct = (pace_ratio * 100) if pace_ratio is not None else None
    c = _color_for(actual, target, threshold_key, pace_ratio)
    html = f'<div class="sfa-kpi-bar" style="height:{height}px;">'
    html += f'<div class="sfa-kpi-bar-fill" style="width:{pct}%;background:{c};"></div>'
    if pace_pct is not None:
        html += f'<div class="sfa-kpi-bar-pace" style="left:{pace_pct}%;"></div>'
    html += "</div>"
    return html


# ──────────────────────────────────────────────
# Cached loaders
# ──────────────────────────────────────────────
@st.cache_data(ttl=300, show_spinner=False)
def _load(name: str, sheet_id: str, calendar_id: str, start: date, end: date):
    member = next((m for m in config.members if m.name == name), None)
    if not member:
        return [], [], None
    deals = fetch_deals(config, member)
    events = fetch_events(config, member, start, end) if calendar_id else []
    return deals, events, member


@st.cache_data(ttl=600, show_spinner=False)
def _load_targets_raw(name: str) -> Targets:
    """分析タブからの生の目標値（上書き未適用）。"""
    member = next((m for m in config.members if m.name == name), None)
    if not member:
        return Targets()
    try:
        return fetch_targets(config, member)
    except Exception:
        return Targets()


def _load_targets(name: str) -> Targets:
    """上書き適用後の目標値。"""
    raw = _load_targets_raw(name)
    overrides = load_overrides()
    return apply_overrides(raw, name, overrides)


def _aggregate_team_targets(target_list: list[Targets]) -> Targets:
    out = Targets()
    for t in target_list:
        out.appointments += t.appointments
        out.seated += t.seated
        out.contract_amount += t.contract_amount
        out.contract_count += t.contract_count
        out.closed_amount += t.closed_amount
        out.closed_count += t.closed_count
        out.meeting_slots += t.meeting_slots
        out.second_appt_count += t.second_appt_count
        out.second_seated += t.second_seated
        out.second_contract_count += t.second_contract_count
    return out


# ──────────────────────────────────────────────
# Sidebar tweaks
# ──────────────────────────────────────────────
with st.sidebar:
    st.markdown("### 🎛️ Tweaks")
    threshold_key = st.selectbox(
        "達成率しきい値",
        options=["default", "strict", "loose"],
        format_func=lambda k: {
            "default": "標準: 緑≥100/青70/黄40",
            "strict": "厳しめ: 緑≥100/青85/黄60",
            "loose": "緩め: 緑≥90/青60/黄30",
        }[k],
    )
    if st.button("🔄 キャッシュクリア"):
        st.cache_data.clear()
        st.rerun()


today = datetime.now(tz).date()
month_start = today.replace(day=1)
month_days = calendar.monthrange(today.year, today.month)[1]
month_end_full = today.replace(day=month_days)
day_in_month = today.day
pace_ratio = day_in_month / month_days


# ──────────────────────────────────────────────
# Header
# ──────────────────────────────────────────────
header_html = (
    f'<div class="sfa-header">'
    f'<div class="sfa-logo">SFA</div>'
    f'<div style="font-size:14px;font-weight:600;">営業ダッシュボード</div>'
    f'<div style="font-size:12px;opacity:.7;">{today.year}年{today.month}月</div>'
    f'<div style="margin-left:auto;font-size:12px;opacity:.85;">'
    f'本日 {today.month}/{today.day} · {day_in_month}/{month_days}日経過 ({round(pace_ratio*100)}%)'
    f'</div></div>'
)
st.markdown(header_html, unsafe_allow_html=True)

if not config.members:
    st.warning(".env が未設定です。OWNER_NAME と SHEET_ID_OWNER を埋めてください。")
    st.stop()


# ──────────────────────────────────────────────
# Pre-load all members once
# ──────────────────────────────────────────────
member_data: dict[str, dict] = {}
for m in config.members:
    deals_m, events_m, _ = _load(m.name, m.sheet_id, m.calendar_id, today - timedelta(days=14), today + timedelta(days=14))
    targets_m = _load_targets(m.name)
    member_data[m.name] = {"member": m, "deals": deals_m, "events": events_m, "targets": targets_m}


# ──────────────────────────────────────────────
# Tabs
# ──────────────────────────────────────────────
if RO:
    tab_warning, tab_progress, tab_individual, tab_team = st.tabs([
        "⚠️ 警告", "📈 進捗推移", "👤 個人", "👥 チーム",
    ])
    tab_targets = None
else:
    tab_warning, tab_progress, tab_individual, tab_team, tab_targets = st.tabs([
        "⚠️ 警告", "📈 進捗推移", "👤 個人", "👥 チーム", "🎯 目標設定",
    ])


# ═════════════════════════════════════════════════════════
# Tab 1 · 警告
# ═════════════════════════════════════════════════════════
with tab_warning:
    period_start = today - timedelta(days=6)
    all_missing: list[dict] = []
    all_stagnant: list[dict] = []
    all_inconsistency: list[dict] = []

    dismissed_missing, dismissed_stagnant = get_dismissed()

    for m in config.members:
        d = member_data[m.name]
        logs = []
        for deal in d["deals"]:
            logs.extend(deal_to_activity_logs(deal))

        cur = period_start
        while cur <= today:
            missing = find_missing_logs(
                d["events"], logs, config.activity_keywords, m.name, cur,
                aliases=aliases,
                date_tolerance_days=config.missing_log_date_tolerance_days,
                excluded_keywords=config.excluded_event_keywords,
            )
            for ms in missing:
                mid = missing_log_id(m.name, ms.event.event_date, ms.event.id, ms.event.title)
                if mid in dismissed_missing:
                    continue
                all_missing.append({
                    "担当": m.name,
                    "日付": ms.event.event_date,
                    "予定": ms.event.title,
                    "顧客（推定）": ms.extracted_customer,
                    "_id": mid,
                })
            cur += timedelta(days=1)

        # データ不整合（失注理由 vs ステータス）— 過去1週間の活動分のみ
        inconsistencies = find_data_inconsistencies(
            d["deals"],
            period_start=period_start,
            period_end=today,
        )
        for inc in inconsistencies:
            deal = inc["deal"]
            all_inconsistency.append({
                "担当": m.name,
                "顧客": deal.customer,
                "種別": "A: 未着地/NA空" if inc["type"] == "A" else "B: 失注/理由空",
                "現況ステータス": deal.current_status or "(未設定)",
                "NA(V列)": (deal.na_memo[:30] + "…") if deal.na_memo and len(deal.na_memo) > 30 else (deal.na_memo or "(空)"),
                "失注理由(O列)": (deal.lost_reason[:30] + "…") if deal.lost_reason and len(deal.lost_reason) > 30 else (deal.lost_reason or "(空)"),
                "メッセージ": inc["message"],
                "_sheet_id": deal.sheet_id,
                "_sheet_tab": deal.sheet_tab,
                "_row_number": deal.row_number,
            })

        stagnant = find_stagnant_deals(
            d["deals"], today=today, threshold_days=config.stagnant_days_threshold,
            stagnant_statuses=config.stagnant_statuses,
        )
        for s in stagnant:
            sid = stagnant_id(s.sheet_id, s.sheet_tab, s.row_number, s.customer)
            if sid in dismissed_stagnant:
                continue
            all_stagnant.append({
                "担当": m.name,
                "顧客": s.customer,
                "現況ステータス": s.current_status or "(未設定)",
                "進捗": s.current_stage,
                "見込み": s.second_appt_forecast or s.first_appt_forecast,
                "最終活動": s.latest_activity_date,
                "_sheet_id": s.sheet_id,
                "_sheet_tab": s.sheet_tab,
                "_row_number": s.row_number,
                "_id": sid,
            })

    # 上部 4 カード
    c1, c2, c3, c4 = st.columns(4)
    for col, icon, color, title, count, desc in [
        (c1, "📝", SF_RED, "記入漏れ", len(all_missing), "カレンダーにあるがヨミ表に記入されていない予定"),
        (c2, "⏸", SF_YELLOW, "停滞案件", len(all_stagnant), f"{config.stagnant_days_threshold}日以上動きがなく、現況が活動中ステータスの案件"),
        (c3, "🔍", SF_BLUE, "データ不整合", len(all_inconsistency), "失注理由とステータスの食い違い"),
        (c4, "✅", SF_GREEN, "対象メンバー", len(config.members), "登録メンバー数"),
    ]:
        html = (
            f'<div class="sfa-warn-card" style="border-left:4px solid {color};">'
            f'<div style="display:flex;gap:14px;align-items:flex-start;">'
            f'<div style="font-size:22px;">{icon}</div>'
            f'<div style="flex:1;">'
            f'<div style="display:flex;justify-content:space-between;align-items:baseline;">'
            f'<div style="font-size:13px;font-weight:700;">{title}</div>'
            f'<div style="font-size:24px;font-weight:800;color:{color};">'
            f'{count}<span style="font-size:11px;font-weight:500;color:{SF_TEXT3};margin-left:4px;">件</span>'
            f'</div></div>'
            f'<div style="font-size:11px;color:{SF_TEXT3};margin-top:6px;line-height:1.4;">{desc}</div>'
            f'</div></div></div>'
        )
        col.markdown(html, unsafe_allow_html=True)

    st.markdown("### 📝 記入漏れアラート")
    if all_missing:
        if RO:
            df_m = pd.DataFrame([{k: v for k, v in r.items() if not k.startswith("_")} for r in all_missing])
            st.dataframe(df_m, hide_index=True, use_container_width=True)
        else:
            # data_editor で「削除」チェックボックスを足す
            df_m = pd.DataFrame([{**{k: v for k, v in r.items() if not k.startswith("_")}, "削除": False, "_id": r["_id"]} for r in all_missing])
            edited_m = st.data_editor(
                df_m,
                hide_index=True,
                use_container_width=True,
                column_config={
                    "削除": st.column_config.CheckboxColumn("削除", help="チェックして「削除を反映」を押すと非表示に"),
                    "_id": None,  # 非表示
                },
                key="missing_editor",
            )
            if st.button("🗑 チェックした記入漏れを削除", key="dismiss_missing_btn"):
                ids_to_dismiss = edited_m[edited_m["削除"] == True]["_id"].tolist()
                if ids_to_dismiss:
                    dismiss_missing(ids_to_dismiss)
                    st.success(f"✓ {len(ids_to_dismiss)}件を削除しました")
                    st.rerun()
                else:
                    st.warning("削除対象が選択されていません")
    else:
        st.success("記入漏れはありません。")

    st.markdown(f"### 🔍 データ不整合（失注理由 vs ステータス・過去7日の活動分）")
    if all_inconsistency:
        df_i = pd.DataFrame([{k: v for k, v in r.items() if not k.startswith("_")} for r in all_inconsistency])
        st.dataframe(df_i, hide_index=True, use_container_width=True)
        st.caption(
            "**A**: まだ着地していない（活動中）AND V列(NA)が空欄"
            " — 進捗メモを記入してください。"
            "  \n"
            "**B**: ステータスが「失注」なのに、O列(失注理由)が空欄"
            " — 失注理由を記入してください。"
        )
    else:
        st.success("データ不整合はありません。")

    st.markdown(f"### ⏸ 停滞案件（{config.stagnant_days_threshold}日以上動きなし）")
    if all_stagnant:
        if RO:
            df_s = pd.DataFrame([{k: v for k, v in r.items() if not k.startswith("_")} for r in all_stagnant])
            st.dataframe(df_s, hide_index=True, use_container_width=True)
        else:
            df_s = pd.DataFrame([{**{k: v for k, v in r.items() if not k.startswith("_")}, "削除": False, "_id": r["_id"]} for r in all_stagnant])
            edited_s = st.data_editor(
                df_s,
                hide_index=True,
                use_container_width=True,
                column_config={
                    "削除": st.column_config.CheckboxColumn("削除", help="チェックして「削除を反映」を押すと非表示に（シートのデータは残る）"),
                    "_id": None,
                },
                key="stagnant_editor",
            )
            cols_action = st.columns([1, 1, 3])
            if cols_action[0].button("🗑 チェックした停滞案件を削除", key="dismiss_stagnant_btn"):
                ids_to_dismiss = edited_s[edited_s["削除"] == True]["_id"].tolist()
                if ids_to_dismiss:
                    dismiss_stagnant(ids_to_dismiss)
                    st.success(f"✓ {len(ids_to_dismiss)}件を削除しました")
                    st.rerun()
                else:
                    st.warning("削除対象が選択されていません")

            st.markdown("**ステージを変更してシートに書き戻し**")
            STATUS_OPTIONS = ["長期追客", "失注", "クーリングオフ", "SP", "リスケ", "契約済"]
            with st.form("change_status_form", clear_on_submit=True):
                col1, col2 = st.columns([3, 2])
                with col1:
                    target_idx = st.selectbox(
                        "対象案件",
                        options=list(range(len(all_stagnant))),
                        format_func=lambda i: (
                            f"{all_stagnant[i]['担当']} / {all_stagnant[i]['顧客']} "
                            f"（{all_stagnant[i]['現況ステータス']}・最終{all_stagnant[i]['最終活動']}）"
                        ),
                    )
                with col2:
                    new_status = st.selectbox("新ステータス", STATUS_OPTIONS)
                submitted = st.form_submit_button("反映（シートに書き戻し）")
                if submitted:
                    target = all_stagnant[target_idx]
                    try:
                        update_current_status(
                            config,
                            target["_sheet_id"],
                            target["_sheet_tab"],
                            int(target["_row_number"]),
                            new_status,
                        )
                        st.success(f"✓ {target['顧客']}（{target['担当']}）を「{new_status}」に更新しました")
                        st.cache_data.clear()
                        st.rerun()
                    except Exception as e:
                        st.error(f"更新失敗: {e}")
    else:
        st.success("停滞案件はありません。")

    # 削除済みの復活（編集可能モードのみ）
    if not RO and (dismissed_missing or dismissed_stagnant):
        with st.expander(f"🔁 削除済みアラート ({len(dismissed_missing)} 記入漏れ / {len(dismissed_stagnant)} 停滞案件)"):
            if dismissed_missing:
                st.markdown("**削除済み記入漏れ**")
                if st.button("全て復活", key="restore_missing_all"):
                    restore_missing(list(dismissed_missing))
                    st.success("復活しました")
                    st.rerun()
                for mid in sorted(dismissed_missing)[:50]:
                    st.text(f"・{mid}")
            if dismissed_stagnant:
                st.markdown("**削除済み停滞案件**")
                if st.button("全て復活", key="restore_stagnant_all"):
                    restore_stagnant(list(dismissed_stagnant))
                    st.success("復活しました")
                    st.rerun()
                for sid in sorted(dismissed_stagnant)[:50]:
                    st.text(f"・{sid}")


# ═════════════════════════════════════════════════════════
# Tab 2 · 進捗推移 (B案 — ストーリーフロー)
# ═════════════════════════════════════════════════════════
with tab_progress:
    member_names = [m.name for m in config.members]
    scope_options = member_names + (["チーム全体"] if len(member_names) > 1 else [])

    cols = st.columns([1, 4])
    with cols[0]:
        scope = st.radio("対象", scope_options, horizontal=False, key="progress_scope")

    if scope == "チーム全体":
        deals_combined = []
        target_list = []
        for m in config.members:
            deals_combined.extend(member_data[m.name]["deals"])
            target_list.append(member_data[m.name]["targets"])
        targets = _aggregate_team_targets(target_list)
        scope_label = "チーム全体"
    else:
        d = member_data[scope]
        deals_combined = d["deals"]
        targets = d["targets"]
        scope_label = scope

    periods = month_periods(today)
    period_kpis = [
        compute_period_kpi(deals_combined, targets, lbl, s, e, ratio)
        for (lbl, s, e, ratio) in periods
    ]
    month_kpi = period_kpis[0]
    week_kpis = period_kpis[1:5]

    # ── SECTION 1: ステータスバナー ──
    sei_a = month_kpi.closed_amount_actual
    sei_t = month_kpi.closed_amount_target
    sei_pct = round((sei_a / sei_t) * 100) if sei_t else 0
    expected = sei_t * pace_ratio
    overall_color = _color_for(sei_a, sei_t, threshold_key, pace_ratio)
    bg_soft = {SF_GREEN: SF_GREEN_SOFT, SF_RED: SF_RED_SOFT, SF_YELLOW: SF_YELLOW_BG, SF_BLUE: SF_BLUE_BG}.get(overall_color, "#fff")

    # 着地予測 = 直近5日傾斜から
    daily_closed = daily_series(deals_combined, month_start, month_end_full, "closed_amount")
    cum_actual = []
    s_cum = 0
    for d_, v in daily_closed:
        s_cum += v
        cum_actual.append((d_, s_cum))
    if len(cum_actual) >= 2:
        recent = cum_actual[-5:] if len(cum_actual) >= 5 else cum_actual
        slope = (recent[-1][1] - recent[0][1]) / max(1, len(recent) - 1)
        days_remaining = max(0, month_days - day_in_month)
        forecast = max(0, cum_actual[-1][1] + slope * days_remaining) if cum_actual else sei_a
    else:
        forecast = sei_a
    forecast_pct = round((forecast / sei_t) * 100) if sei_t else 0
    forecast_color = _color_for(forecast, sei_t, threshold_key)

    if sei_a >= expected:
        msg = (f"<strong style='color:{overall_color};'>{_yen_short(sei_a)}</strong>。"
               "順調なペースで進んでいます。")
    else:
        msg = (f"<strong style='color:{overall_color};'>{_yen_short(sei_a)}</strong>。"
               f"本日のペース基準（{_yen_short(expected)}）に対し "
               f"<strong style='color:{SF_RED};'>{_yen_short(max(0, expected - sei_a))} 不足</strong>しています。")

    banner_html = (
        f'<div class="sfa-banner" style="background:{bg_soft};border-color:{overall_color}40;border-left-color:{overall_color};">'
        f'<div class="sfa-banner-pct" style="background:{overall_color}22;color:{overall_color};">'
        f'{sei_pct}<span style="font-size:11px;">%</span></div>'
        f'<div style="flex:1;">'
        f'<div class="sfa-banner-text">{scope_label} の今月の成約額は {msg}</div>'
        f'<div class="sfa-banner-meta">'
        f'目標 {_yen_short(sei_t)} · 残 {_yen_short(max(0, sei_t - sei_a))} · '
        f'このペースの着地予測 '
        f'<strong style="color:{forecast_color};">{_yen_short(forecast)} ({forecast_pct}%)</strong>'
        f'</div></div></div>'
    )
    st.markdown(banner_html, unsafe_allow_html=True)

    # ── SECTION 2: 7セル KPI ストリップ ──
    kpi_cells = [
        ("アポ数", month_kpi.appointments_actual, month_kpi.appointments_target, False, False),
        ("着座数", month_kpi.seated_actual, month_kpi.seated_target, False, False),
        ("2回目アポ実施", month_kpi.second_appt_done_actual, month_kpi.second_appt_done_target, False, False),
        ("契約数", month_kpi.contract_count_actual, month_kpi.contract_count_target, False, False),
        ("成約数", month_kpi.closed_count_actual, month_kpi.closed_count_target, False, False),
        ("契約額", month_kpi.contract_amount_actual, month_kpi.contract_amount_target, True, False),
        ("成約額", month_kpi.closed_amount_actual, month_kpi.closed_amount_target, True, True),
    ]
    cells_html = []
    for label, a, t, is_yen, hl in kpi_cells:
        c = _color_for(a, t, threshold_key, pace_ratio)
        pct = round(a / t * 100) if t else 0
        val = _yen_short(a) if is_yen else f"{int(a):,}"
        tval = _yen_short(t) if is_yen else f"{int(t):,}"
        cls = "sfa-kpi-cell hl" if hl else "sfa-kpi-cell"
        bar = _progress_bar_html(a, t, pace_ratio, threshold_key, height=4)
        cell = (
            f'<div class="{cls}">'
            f'<div class="sfa-kpi-row1"><span>{label}</span>'
            f'<span class="sfa-kpi-pct" style="color:{c};">{pct}%</span></div>'
            f'<div class="sfa-kpi-num">{val}</div>'
            f'<div class="sfa-kpi-tgt">/ {tval}</div>'
            f'{bar}'
            f'</div>'
        )
        cells_html.append(cell)
    st.markdown(
        '<div class="sfa-kpi-strip">' + "".join(cells_html) + '</div>',
        unsafe_allow_html=True,
    )

    # ── SECTION 3: 累積線 + 週別バー ──
    metric_options = [
        ("成約額", "closed_amount", True),
        ("契約額", "contract_amount", True),
        ("アポ数", "appointments", False),
        ("着座数", "seated", False),
        ("契約数", "contracts", False),
        ("成約数", "closed", False),
    ]
    selected_metric = st.selectbox(
        "推移グラフの指標",
        metric_options,
        format_func=lambda x: x[0],
        key="trend_metric",
    )
    metric_label, metric_key, metric_is_yen = selected_metric

    def _pick(kpi, key):
        return {
            "appointments": (kpi.appointments_actual, kpi.appointments_target),
            "seated": (kpi.seated_actual, kpi.seated_target),
            "contracts": (kpi.contract_count_actual, kpi.contract_count_target),
            "contract_amount": (kpi.contract_amount_actual, kpi.contract_amount_target),
            "closed": (kpi.closed_count_actual, kpi.closed_count_target),
            "closed_amount": (kpi.closed_amount_actual, kpi.closed_amount_target),
        }.get(key, (0, 0))

    metric_actual, metric_target = _pick(month_kpi, metric_key)

    col1, col2 = st.columns([1.3, 1])

    with col1:
        st.markdown(f'<div class="sfa-card-title">{metric_label} の累積推移</div>'
                    '<div class="sfa-card-sub">実績 vs 理想ペース vs 着地予測</div>',
                    unsafe_allow_html=True)
        # 累積データ
        daily_data = daily_series(deals_combined, month_start, month_end_full, metric_key)
        cum = 0
        cum_rows = []
        for d_, v in daily_data:
            cum += v
            cum_rows.append({"日付": d_, "実績": cum})
        # 理想ペース line
        for i, r in enumerate(cum_rows):
            r["理想ペース"] = metric_target * (i + 1) / month_days
        # 着地予測線 (今日以降)
        cum_actual_today = cum_rows[day_in_month - 1]["実績"] if day_in_month <= len(cum_rows) and cum_rows else 0
        if len(cum_rows) >= 2:
            r5 = cum_rows[max(0, day_in_month - 5):day_in_month]
            slope_m = (r5[-1]["実績"] - r5[0]["実績"]) / max(1, len(r5) - 1) if r5 else 0
        else:
            slope_m = 0
        forecast_m = max(0, cum_actual_today + slope_m * (month_days - day_in_month))

        df_cum = pd.DataFrame(cum_rows)
        df_fc = pd.DataFrame([
            {"日付": cum_rows[day_in_month - 1]["日付"] if cum_rows and day_in_month <= len(cum_rows) else month_start, "着地予測": cum_actual_today},
            {"日付": cum_rows[-1]["日付"] if cum_rows else month_end_full, "着地予測": forecast_m},
        ])

        line_actual = alt.Chart(df_cum).mark_line(color=SF_BLUE, strokeWidth=2.5, point=alt.OverlayMarkDef(filled=True, color=SF_BLUE, size=40)).encode(
            x=alt.X("日付:T", axis=alt.Axis(format="%-d", title=None, grid=False, labelFontSize=10)),
            y=alt.Y("実績:Q", axis=alt.Axis(title=None, format="~s", labelFontSize=10)),
            tooltip=[alt.Tooltip("日付:T"), alt.Tooltip("実績:Q", format=",.0f")],
        )
        area = alt.Chart(df_cum).mark_area(color=SF_BLUE, opacity=0.10).encode(x="日付:T", y="実績:Q")
        line_ideal = alt.Chart(df_cum).mark_line(color=SF_TEXT3, strokeDash=[5, 4], strokeWidth=1.5).encode(
            x="日付:T", y="理想ペース:Q",
        )
        line_fc = alt.Chart(df_fc).mark_line(color=forecast_color, strokeDash=[3, 3], strokeWidth=2).encode(
            x="日付:T", y="着地予測:Q",
        )
        st.altair_chart(
            (area + line_ideal + line_fc + line_actual).properties(height=240).configure_view(strokeWidth=0),
            use_container_width=True,
        )
        st.caption(f"<span style='color:{SF_BLUE}'>━ 実績</span> &nbsp; "
                   f"<span style='color:{SF_TEXT3}'>┄ 理想ペース</span> &nbsp; "
                   f"<span style='color:{forecast_color}'>┄ 着地予測</span>",
                   unsafe_allow_html=True)

    with col2:
        st.markdown(f'<div class="sfa-card-title">週別 — {metric_label}</div>'
                    '<div class="sfa-card-sub">今月のリズム</div>',
                    unsafe_allow_html=True)
        wk_rows = []
        wk_target = metric_target / 4 if metric_target else 0
        for kpi in week_kpis:
            actual, _ = _pick(kpi, metric_key)
            wk_rows.append({
                "週": kpi.label.replace(f"{today.month}月 ", ""),
                "実績": float(actual),
                "目標": wk_target,
            })
        df_wk = pd.DataFrame(wk_rows)
        df_wk["color"] = df_wk.apply(lambda r: _color_for(r["実績"], r["目標"], threshold_key), axis=1)
        bars = alt.Chart(df_wk).mark_bar(size=42, cornerRadius=2).encode(
            x=alt.X("週:N", sort=None, axis=alt.Axis(title=None, labelAngle=0, labelFontSize=11)),
            y=alt.Y("実績:Q", axis=alt.Axis(title=None, format="~s", labelFontSize=10)),
            color=alt.Color("color:N", scale=None, legend=None),
            tooltip=[alt.Tooltip("週:N"), alt.Tooltip("実績:Q", format=",.0f"), alt.Tooltip("目標:Q", format=",.0f")],
        )
        target_tick = alt.Chart(df_wk).mark_tick(thickness=2, size=46, color=SF_TEXT2).encode(
            x="週:N", y="目標:Q",
        )
        st.altair_chart(
            (bars + target_tick).properties(height=240).configure_view(strokeWidth=0),
            use_container_width=True,
        )
        st.caption(f"<span style='color:{SF_GREEN}'>■達成</span> &nbsp;"
                   f"<span style='color:{SF_BLUE}'>■順調</span> &nbsp;"
                   f"<span style='color:{SF_YELLOW}'>■注意</span> &nbsp;"
                   f"<span style='color:{SF_RED}'>■未達</span> &nbsp;"
                   f"<span style='color:{SF_TEXT2}'>┃週目標</span>",
                   unsafe_allow_html=True)


# ═════════════════════════════════════════════════════════
# Tab 3 · 個人
# ═════════════════════════════════════════════════════════
with tab_individual:
    cols_top = st.columns([1.2, 2])
    with cols_top[0]:
        person = st.radio("メンバー", member_names, horizontal=True, key="ind_member")
    with cols_top[1]:
        period_choice = st.radio(
            "期間",
            ["今月", "今週", "先週", "先月", "全期間"],
            horizontal=True,
            key="ind_period",
            index=0,
        )
    d = member_data[person]
    deals_p = d["deals"]
    targets_p = d["targets"]
    color = SF_BLUE if list(member_data.keys()).index(person) == 0 else "#7b4cc7"

    # 期間範囲を解決
    if period_choice == "今月":
        p_start, p_end = month_start, month_end_full
    elif period_choice == "今週":
        p_start = today - timedelta(days=today.weekday())
        p_end = p_start + timedelta(days=6)
    elif period_choice == "先週":
        this_monday = today - timedelta(days=today.weekday())
        p_start = this_monday - timedelta(days=7)
        p_end = p_start + timedelta(days=6)
    elif period_choice == "先月":
        first_this = month_start
        last_prev = first_this - timedelta(days=1)
        p_start = last_prev.replace(day=1)
        p_end = last_prev
    else:  # 全期間
        p_start, p_end = date(1900, 1, 1), date(2999, 12, 31)

    profile_html = (
        f'<div class="sfa-card" style="display:flex;align-items:center;gap:24px;">'
        f'<div style="width:64px;height:64px;border-radius:32px;background:{color};color:#fff;'
        f'display:flex;align-items:center;justify-content:center;font-size:28px;font-weight:800;">'
        f'{person[0]}</div>'
        f'<div><div style="font-size:22px;font-weight:700;">{person} さん</div>'
        f'<div style="font-size:12px;color:{SF_TEXT3};margin-top:4px;">'
        f'{period_choice}（{p_start} 〜 {p_end}） · 担当案件 {len(deals_p)}件</div></div></div>'
    )
    st.markdown(profile_html, unsafe_allow_html=True)

    # 期間フィルタつきファネル
    def _in(d_, s, e):
        return d_ is not None and s <= d_ <= e

    if period_choice == "全期間":
        deals_in_period = deals_p
    else:
        deals_in_period = [
            deal for deal in deals_p
            if _in(deal.first_appt_date, p_start, p_end)
            or _in(deal.second_appt_date, p_start, p_end)
            or _in(deal.contract_date, p_start, p_end)
            or _in(deal.closed_date, p_start, p_end)
        ]

    f_leads = len(deals_in_period)
    f_first_sched = sum(1 for d in deals_in_period if _in(d.first_appt_date, p_start, p_end) or period_choice == "全期間" and d.first_appt_date)
    f_first_done = sum(1 for d in deals_in_period if (period_choice == "全期間" or _in(d.first_appt_date, p_start, p_end)) and d.first_appt_done)
    f_second_sched = sum(1 for d in deals_in_period if (period_choice == "全期間" and d.second_appt_date) or _in(d.second_appt_date, p_start, p_end))
    f_second_done = sum(1 for d in deals_in_period if ((period_choice == "全期間" and d.second_appt_date) or _in(d.second_appt_date, p_start, p_end)) and d.second_appt_done)
    f_contract = sum(1 for d in deals_in_period if (period_choice == "全期間" and d.contract_date) or _in(d.contract_date, p_start, p_end))
    f_closed = sum(1 for d in deals_in_period if (period_choice == "全期間" and d.closed_date) or _in(d.closed_date, p_start, p_end))

    funnel_stages = [
        ("リード", f_leads),
        ("初回予定", f_first_sched),
        ("初回実施", f_first_done),
        ("2回目予定", f_second_sched),
        ("2回目実施", f_second_done),
        ("契約", f_contract),
        ("成約", f_closed),
    ]
    df_f = pd.DataFrame(funnel_stages, columns=["stage", "value"])

    col1, col2 = st.columns([1.4, 1])
    with col1:
        st.markdown('<div class="sfa-card-title">コンバージョンファネル</div>', unsafe_allow_html=True)
        chart_f = alt.Chart(df_f).mark_bar(color=color, height=28, cornerRadius=4).encode(
            y=alt.Y("stage:N", sort=None, axis=alt.Axis(title=None, labelFontSize=12)),
            x=alt.X("value:Q", axis=alt.Axis(title=None, grid=False, labelFontSize=10)),
            tooltip=[alt.Tooltip("stage:N", title="ステージ"), alt.Tooltip("value:Q", title="件数")],
        )
        labels = alt.Chart(df_f).mark_text(align="left", dx=6, fontWeight="bold", color=SF_INK, fontSize=12).encode(
            y=alt.Y("stage:N", sort=None), x="value:Q", text="value:Q",
        )
        st.altair_chart((chart_f + labels).properties(height=280).configure_view(strokeWidth=0), use_container_width=True)

    with col2:
        st.markdown('<div class="sfa-card-title">見込み別件数（期間内）</div>', unsafe_allow_html=True)
        yomi_counts = {"A": 0, "B": 0, "C": 0, "D": 0}
        for deal in deals_in_period:
            v = (deal.second_appt_forecast or deal.first_appt_forecast or "").strip().upper()[:1]
            if v in yomi_counts:
                yomi_counts[v] += 1
        weighted = yomi_counts["A"]*0.9 + yomi_counts["B"]*0.6 + yomi_counts["C"]*0.3 + yomi_counts["D"]*0.1

        cols = st.columns(4)
        yomi_meta = [("A", "90%", SF_GREEN, SF_GREEN_BG),
                     ("B", "60%", SF_BLUE, SF_BLUE_BG),
                     ("C", "30%", SF_YELLOW, SF_YELLOW_BG),
                     ("D", "10%", SF_TEXT3, SF_BORDER_LIGHT)]
        for c, (k, p, fg, bg) in zip(cols, yomi_meta):
            box = (
                f'<div style="background:{bg};border:1px solid {fg}33;border-radius:6px;padding:12px 14px;margin-bottom:6px;">'
                f'<div style="font-size:10px;font-weight:700;color:{fg};letter-spacing:.05em;">{k} · {p}</div>'
                f'<div style="font-size:24px;font-weight:700;color:{SF_INK};margin-top:4px;line-height:1;">'
                f'{yomi_counts[k]}<span style="font-size:11px;color:{SF_TEXT3};font-weight:500;"> 件</span>'
                f'</div></div>'
            )
            c.markdown(box, unsafe_allow_html=True)
        st.caption(f"加重期待値: **{weighted:.1f}件** (A×90% + B×60% + C×30% + D×10%)")


# ═════════════════════════════════════════════════════════
# Tab 4 · チーム
# ═════════════════════════════════════════════════════════
with tab_team:
    st.markdown("### チーム合計 KPI")
    deals_all = []
    target_list = []
    member_kpis = []
    for m in config.members:
        d = member_data[m.name]
        deals_all.extend(d["deals"])
        target_list.append(d["targets"])
        member_kpis.append(aggregate_member(m.name, d["deals"], month_start, month_end_full))

    targets_t = _aggregate_team_targets(target_list)
    team_kpi = compute_period_kpi(deals_all, targets_t, "チーム", month_start, month_end_full, 1.0)

    cols = st.columns(4)
    cards = [
        ("アポ数 (合計)", team_kpi.appointments_actual, team_kpi.appointments_target, False),
        ("着座数 (合計)", team_kpi.seated_actual, team_kpi.seated_target, False),
        ("契約数 (合計)", team_kpi.contract_count_actual, team_kpi.contract_count_target, False),
        ("成約額 (合計)", team_kpi.closed_amount_actual, team_kpi.closed_amount_target, True),
    ]
    for col, (label, a, t, is_yen) in zip(cols, cards):
        c = _color_for(a, t, threshold_key, pace_ratio)
        pct = round(a / t * 100) if t else 0
        val = _yen_short(a) if is_yen else f"{int(a):,}"
        tval = _yen_short(t) if is_yen else f"{int(t):,}"
        bar = _progress_bar_html(a, t, pace_ratio, threshold_key, 8)
        card_html = (
            f'<div class="sfa-card" style="border-left:4px solid {c};margin-bottom:0;">'
            f'<div style="display:flex;justify-content:space-between;align-items:baseline;">'
            f'<div style="font-size:11px;color:{SF_TEXT3};font-weight:600;">{label}</div>'
            f'<div style="font-size:11px;color:{c};font-weight:700;'
            f'background:{_color_bg(a,t)};padding:2px 8px;border-radius:10px;">{pct}%</div>'
            f'</div>'
            f'<div style="font-size:32px;font-weight:700;letter-spacing:-.02em;margin-top:6px;line-height:1;">{val}</div>'
            f'<div style="font-size:11px;color:{SF_TEXT3};margin-top:4px;">/ 目標 {tval}</div>'
            f'<div style="margin-top:10px;">{bar}</div>'
            f'</div>'
        )
        col.markdown(card_html, unsafe_allow_html=True)

    st.markdown("### メンバー別貢献度 — 成約額")
    palette = [SF_BLUE, "#7b4cc7", SF_GREEN, SF_YELLOW, SF_RED]
    for i, m in enumerate(config.members):
        d = member_data[m.name]
        kpi_m = compute_period_kpi(d["deals"], d["targets"], m.name, month_start, month_end_full, 1.0)
        a = kpi_m.closed_amount_actual
        t = kpi_m.closed_amount_target
        pct_label = f"{round(a/t*100) if t else 0}%"
        c = palette[i % len(palette)]
        bar = _progress_bar_html(a, t, pace_ratio, threshold_key, 10)
        rate_color = _color_for(a, t, threshold_key, pace_ratio)
        contrib_html = (
            f'<div style="margin-bottom:16px;">'
            f'<div style="display:flex;justify-content:space-between;font-size:12px;margin-bottom:6px;">'
            f'<span><span style="display:inline-block;width:8px;height:8px;border-radius:4px;'
            f'background:{c};margin-right:8px;"></span><strong>{m.name}</strong></span>'
            f'<span>'
            f'<strong style="font-size:15px;">{_yen_short(a)}</strong>'
            f'<span style="color:{SF_TEXT3};"> / {_yen_short(t)}</span>'
            f'<strong style="color:{rate_color};margin-left:8px;">{pct_label}</strong>'
            f'</span></div>'
            f'{bar}'
            f'</div>'
        )
        st.markdown(contrib_html, unsafe_allow_html=True)


# ═════════════════════════════════════════════════════════
# Tab 5 · 目標設定（ローカル上書き）
# ═════════════════════════════════════════════════════════
if tab_targets is not None:
  with tab_targets:
    st.markdown("### 🎯 目標設定")
    st.caption(
        "分析タブから読み込んだ目標値が表示されます。"
        "上書きしたい項目だけ値を変えて「保存」してください。空欄のまま保存すると上書き解除（分析タブの値を使う）になります。"
    )

    overrides_current = load_overrides()
    target_member_name = st.radio("メンバー", member_names, horizontal=True, key="targets_member")

    raw = _load_targets_raw(target_member_name)
    current_override = overrides_current.get(target_member_name, {})

    # ステータスサマリ
    has_override = bool(current_override)
    if has_override:
        st.info(f"現在 **{len(current_override)}項目** が上書きされています")
    else:
        st.success("分析タブの値をそのまま使用しています（上書きなし）")

    # 編集対象フィールド
    field_specs = [
        ("appointments", "アポ数（件）", "int"),
        ("seated", "着座数（件）", "int"),
        ("contract_count", "契約数（件）", "int"),
        ("contract_amount", "契約額（円）", "float"),
        ("closed_count", "成約数（件）", "int"),
        ("closed_amount", "成約額（円）", "float"),
        ("second_appt_count", "2回目アポ数（件）", "int"),
        ("second_seated", "2回目着座数（件）", "int"),
        ("meeting_slots", "商談枠（件）", "int"),
    ]

    with st.form(f"target_form_{target_member_name}", clear_on_submit=False):
        st.markdown("#### KPI 目標値")
        cols = st.columns(3)
        new_values: dict[str, object] = {}
        for i, (field_key, label, dtype) in enumerate(field_specs):
            col = cols[i % 3]
            sheet_val = getattr(raw, field_key, 0)
            override_val = current_override.get(field_key)
            current = override_val if override_val not in (None, "") else sheet_val

            if dtype == "int":
                v = col.number_input(
                    f"{label}（分析タブ: {int(sheet_val):,}）",
                    min_value=0,
                    value=int(current) if current else 0,
                    step=1,
                    key=f"in_{field_key}_{target_member_name}",
                )
                new_values[field_key] = int(v) if v else None
            else:
                v = col.number_input(
                    f"{label}（分析タブ: {float(sheet_val):,.0f}）",
                    min_value=0.0,
                    value=float(current) if current else 0.0,
                    step=10000.0,
                    key=f"in_{field_key}_{target_member_name}",
                )
                new_values[field_key] = float(v) if v else None

        st.caption("※ 値が分析タブと同じ場合は上書きから除外されます（無駄な上書きを増やさないため）")

        c1, c2, c3 = st.columns([1, 1, 3])
        with c1:
            save_clicked = st.form_submit_button("💾 保存", type="primary")
        with c2:
            clear_clicked = st.form_submit_button("🗑 上書き解除", help="このメンバーの上書きを削除")

    if save_clicked:
        # 分析タブと同じ値は上書きから除外
        cleaned = {}
        for field_key, _, _ in field_specs:
            v = new_values.get(field_key)
            sheet_v = getattr(raw, field_key, 0)
            if v is not None and v != 0 and v != sheet_v:
                cleaned[field_key] = v
        new_overrides = upsert_member(overrides_current, target_member_name, cleaned)
        try:
            save_overrides(new_overrides)
            st.cache_data.clear()
            st.success(f"✓ {target_member_name} の目標値を保存しました（{len(cleaned)}項目を上書き）")
            st.rerun()
        except Exception as e:
            st.error(f"保存に失敗: {e}")

    if clear_clicked:
        new_overrides = upsert_member(overrides_current, target_member_name, {})
        try:
            save_overrides(new_overrides)
            st.cache_data.clear()
            st.success(f"✓ {target_member_name} の上書きを解除しました")
            st.rerun()
        except Exception as e:
            st.error(f"クリアに失敗: {e}")

    # 現在の上書き一覧
    if overrides_current:
        st.markdown("---")
        st.markdown("#### 現在の上書き一覧")
        rows = []
        for member_name, override in overrides_current.items():
            for k, v in override.items():
                label = next((l for fk, l, _ in field_specs if fk == k), k)
                rows.append({"メンバー": member_name, "項目": label, "上書き値": v})
        if rows:
            st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
