from datetime import date, datetime

from core.matcher import (
    extract_customer,
    extract_customers,
    find_missing_logs,
    find_stagnant_deals,
    is_business_event,
)
from core.models import ActivityLog, CalendarEvent, Deal, deal_to_activity_logs


KEYWORDS = ["無料カウンセリング", "商談", "アポ", "訪問", "面談", "初回", "2回目", "契約"]


def _event(title: str, d: date = date(2026, 5, 1), hour: int = 14) -> CalendarEvent:
    return CalendarEvent(
        id=title,
        title=title,
        start=datetime(d.year, d.month, d.day, hour),
        end=datetime(d.year, d.month, d.day, hour + 1),
    )


class TestIsBusinessEvent:
    def test_with_sama(self):
        assert is_business_event("田中太郎様 松戸さん 無料カウンセリング", KEYWORDS)

    def test_sama_only_no_keyword(self):
        # キーワード無しでも 様 があれば営業活動
        assert is_business_event("田中太郎様 松戸さん", KEYWORDS)

    def test_no_sama_with_keyword_excluded(self):
        # 商談報告のような内部メモは除外（様なし）
        assert not is_business_event("商談報告", KEYWORDS)

    def test_cancelled_excluded(self):
        assert not is_business_event("[キャンセル済み]田中太郎様 松戸さん", KEYWORDS)

    def test_no_sama(self):
        assert not is_business_event("社内MTG", KEYWORDS)

    def test_empty(self):
        assert not is_business_event("", KEYWORDS)


class TestExtractCustomers:
    def test_simple_sama(self):
        assert extract_customers("本多将大様 無料カウンセリング", KEYWORDS) == ["本多将大"]

    def test_sama_with_san_salesperson(self):
        assert extract_customers("宮村栄一郎様 松戸さん 無料カウンセリング", KEYWORDS) == ["宮村栄一郎"]

    def test_sama_with_full_name_salesperson(self):
        assert extract_customers("田中太郎様 松戸 好誠 無料カウンセリング", KEYWORDS) == ["田中太郎"]

    def test_full_name_with_space(self):
        # "あさだ こうすけ様" のスペース区切り姓名 → 全部取れる
        assert extract_customers("あさだ こうすけ様 松戸 好誠", KEYWORDS) == ["あさだ こうすけ"]

    def test_english_name(self):
        assert extract_customers("Ayane Toyoda様 松戸 好誠", KEYWORDS) == ["Ayane Toyoda"]

    def test_bracket_prefix_removed(self):
        # 角括弧プレフィックスは無視されて顧客抽出される
        # （ただしキャンセルは is_business_event で別途除外）
        assert extract_customers("[キャンセル済み]小西 厚子様 松戸 好誠", KEYWORDS) == ["小西 厚子"]

    def test_no_sama(self):
        assert extract_customers("社内MTG", KEYWORDS) == []


class TestFindMissingLogs:
    def test_no_logs_returns_missing(self):
        events = [_event("田中太郎様 松戸さん 無料カウンセリング")]
        result = find_missing_logs(events, [], KEYWORDS, owner="松戸", target_date=date(2026, 5, 1))
        assert len(result) == 1
        assert result[0].extracted_customer == "田中太郎"

    def test_log_present_no_missing(self):
        events = [_event("田中太郎様 松戸さん 無料カウンセリング")]
        logs = [ActivityLog(owner="松戸", customer="田中太郎", log_date=date(2026, 5, 1), stage="初回")]
        result = find_missing_logs(events, logs, KEYWORDS, owner="松戸", target_date=date(2026, 5, 1))
        assert len(result) == 0

    def test_partial_customer_match(self):
        # 抽出された顧客名がシートの顧客名に部分一致でマッチ
        events = [_event("田中太郎様 松戸さん")]
        logs = [ActivityLog(owner="松戸", customer="田中", log_date=date(2026, 5, 1), stage="初回")]
        result = find_missing_logs(events, logs, KEYWORDS, owner="松戸", target_date=date(2026, 5, 1))
        assert len(result) == 0

    def test_different_owner_does_not_match(self):
        events = [_event("田中太郎様 松戸さん")]
        logs = [ActivityLog(owner="他人", customer="田中太郎", log_date=date(2026, 5, 1), stage="初回")]
        result = find_missing_logs(events, logs, KEYWORDS, owner="松戸", target_date=date(2026, 5, 1))
        assert len(result) == 1

    def test_non_business_event_ignored(self):
        events = [_event("社内ランチ"), _event("田中太郎様 松戸さん")]
        result = find_missing_logs(events, [], KEYWORDS, owner="松戸", target_date=date(2026, 5, 1))
        assert len(result) == 1
        assert "田中太郎" in result[0].extracted_customer

    def test_cancelled_event_ignored(self):
        events = [_event("[キャンセル済み]田中太郎様 松戸さん")]
        result = find_missing_logs(events, [], KEYWORDS, owner="松戸", target_date=date(2026, 5, 1))
        assert len(result) == 0

    def test_other_day_event_ignored(self):
        events = [_event("田中太郎様 松戸さん", d=date(2026, 4, 30))]
        result = find_missing_logs(events, [], KEYWORDS, owner="松戸", target_date=date(2026, 5, 1))
        assert len(result) == 0


class TestDealToActivityLogs:
    def test_first_only(self):
        deal = Deal(owner="松戸", customer="ABC", first_appt_date=date(2026, 5, 1), first_appt_done=True)
        logs = deal_to_activity_logs(deal)
        assert len(logs) == 1
        assert logs[0].stage == "初回"

    def test_first_and_second(self):
        deal = Deal(
            owner="松戸", customer="ABC",
            first_appt_date=date(2026, 4, 20), first_appt_done=True,
            second_appt_date=date(2026, 5, 1), second_appt_done=True,
        )
        logs = deal_to_activity_logs(deal)
        assert len(logs) == 2
        assert {log.stage for log in logs} == {"初回", "2回目"}

    def test_contract(self):
        deal = Deal(
            owner="松戸", customer="ABC",
            first_appt_date=date(2026, 4, 1),
            second_appt_date=date(2026, 4, 15),
            contract_date=date(2026, 5, 1),
            contract_amount_inclusive=300000,
        )
        logs = deal_to_activity_logs(deal)
        contract_logs = [l for l in logs if l.stage == "契約"]
        assert len(contract_logs) == 1
        assert contract_logs[0].amount == 300000

    def test_empty_deal(self):
        deal = Deal(owner="松戸", customer="ABC")
        assert deal_to_activity_logs(deal) == []


STAGNANT_STATUSES = ["検討中", "長期追客", "2回目商談日程確定", "2回目商談日程調整中"]


class TestFindStagnantDeals:
    """ホワイトリスト方式: 指定ステータスのみが停滞対象。"""

    def test_status_in_whitelist_old_returned(self):
        deals = [Deal(
            owner="松戸", customer="A",
            first_appt_date=date(2026, 4, 20), first_appt_done=True,
            current_status="検討中",
        )]
        result = find_stagnant_deals(deals, today=date(2026, 5, 1), threshold_days=7, stagnant_statuses=STAGNANT_STATUSES)
        assert len(result) == 1

    def test_status_choki_tsuikyaku(self):
        deals = [Deal(owner="松戸", customer="A",
            first_appt_date=date(2026, 4, 1), first_appt_done=True, current_status="長期追客")]
        result = find_stagnant_deals(deals, today=date(2026, 5, 1), threshold_days=7, stagnant_statuses=STAGNANT_STATUSES)
        assert len(result) == 1

    def test_status_2nd_appt_pending(self):
        deals = [Deal(owner="松戸", customer="A",
            first_appt_date=date(2026, 4, 1), first_appt_done=True, current_status="2回目商談日程確定")]
        result = find_stagnant_deals(deals, today=date(2026, 5, 1), threshold_days=7, stagnant_statuses=STAGNANT_STATUSES)
        assert len(result) == 1

    def test_status_2nd_appt_arranging(self):
        deals = [Deal(owner="松戸", customer="A",
            first_appt_date=date(2026, 4, 1), first_appt_done=True, current_status="2回目商談日程調整中")]
        result = find_stagnant_deals(deals, today=date(2026, 5, 1), threshold_days=7, stagnant_statuses=STAGNANT_STATUSES)
        assert len(result) == 1

    def test_status_not_in_whitelist_excluded(self):
        # 契約済/失注/SP/リスケ/クーリングオフ などは停滞対象外
        for s in ["失注", "クーリングオフ", "SP", "リスケ", "契約済"]:
            deals = [Deal(owner="松戸", customer="A",
                first_appt_date=date(2026, 4, 1), first_appt_done=True, current_status=s)]
            result = find_stagnant_deals(deals, today=date(2026, 5, 1), threshold_days=7, stagnant_statuses=STAGNANT_STATUSES)
            assert len(result) == 0, f"status={s} should not be in whitelist"

    def test_empty_status_excluded_when_whitelist_set(self):
        # ステータス未設定でも、ホワイトリスト適用時は対象外
        deals = [Deal(owner="松戸", customer="A",
            first_appt_date=date(2026, 4, 1), first_appt_done=True, current_status="")]
        result = find_stagnant_deals(deals, today=date(2026, 5, 1), threshold_days=7, stagnant_statuses=STAGNANT_STATUSES)
        assert len(result) == 0

    def test_recent_deal_filtered(self):
        deals = [Deal(
            owner="松戸", customer="A",
            first_appt_date=date(2026, 4, 30), first_appt_done=True,
            current_status="検討中",
        )]
        result = find_stagnant_deals(deals, today=date(2026, 5, 1), threshold_days=7, stagnant_statuses=STAGNANT_STATUSES)
        assert len(result) == 0

    def test_contracted_deal_excluded(self):
        deals = [Deal(
            owner="松戸", customer="A",
            first_appt_date=date(2026, 3, 1),
            contract_date=date(2026, 3, 10),
            current_status="検討中",  # ホワイトリストに入っていても契約済なら除外
        )]
        result = find_stagnant_deals(deals, today=date(2026, 5, 1), threshold_days=7, stagnant_statuses=STAGNANT_STATUSES)
        assert len(result) == 0

    def test_uses_latest_activity(self):
        deals = [Deal(
            owner="松戸", customer="A",
            first_appt_date=date(2026, 3, 1),
            second_appt_date=date(2026, 4, 30),
            second_appt_done=True,
            current_status="検討中",
        )]
        result = find_stagnant_deals(deals, today=date(2026, 5, 1), threshold_days=7, stagnant_statuses=STAGNANT_STATUSES)
        assert len(result) == 0

    def test_no_whitelist_includes_all(self):
        # ホワイトリスト未指定 or 空なら従来挙動（ステータス無関係）
        deals = [Deal(owner="松戸", customer="A",
            first_appt_date=date(2026, 4, 1), first_appt_done=True, current_status="任意")]
        result = find_stagnant_deals(deals, today=date(2026, 5, 1), threshold_days=7, stagnant_statuses=None)
        assert len(result) == 1


class TestMissingLogsDateTolerance:
    def test_log_one_day_off_with_tolerance(self):
        from core.matcher import find_missing_logs
        events = [_event("田中太郎様 松戸さん", d=date(2026, 5, 1))]
        # シート上の活動ログが 5/2（1日ずれ）
        logs = [ActivityLog(owner="松戸", customer="田中太郎", log_date=date(2026, 5, 2), stage="初回")]
        result = find_missing_logs(events, logs, KEYWORDS, owner="松戸", target_date=date(2026, 5, 1), date_tolerance_days=1)
        assert len(result) == 0  # 1日ずれは許容

    def test_log_two_days_off_no_tolerance(self):
        from core.matcher import find_missing_logs
        events = [_event("田中太郎様 松戸さん", d=date(2026, 5, 1))]
        logs = [ActivityLog(owner="松戸", customer="田中太郎", log_date=date(2026, 5, 3), stage="初回")]
        result = find_missing_logs(events, logs, KEYWORDS, owner="松戸", target_date=date(2026, 5, 1), date_tolerance_days=1)
        assert len(result) == 1  # 2日ずれは tolerance を超える


class TestMatcherWithAliases:
    def test_alias_handle_to_real_name(self):
        from core.aliases import AliasMap
        from core.matcher import find_missing_logs
        # 仮想エイリアス: カレンダー「大嶽恵理」 = シート「megumi.k」
        aliases = AliasMap()
        aliases._calendar_to_sheet[__import__("core.normalize", fromlist=["normalize"]).normalize("大嶽恵理")] = "megumi.k"
        aliases._sheet_to_calendar[__import__("core.normalize", fromlist=["normalize"]).normalize("megumi.k")] = "大嶽恵理"

        events = [_event("大嶽恵理様 松戸さん 無料カウンセリング")]
        logs = [ActivityLog(owner="松戸", customer="megumi.k", log_date=date(2026, 5, 1), stage="初回")]
        result = find_missing_logs(events, logs, KEYWORDS, owner="松戸", target_date=date(2026, 5, 1), aliases=aliases)
        assert len(result) == 0  # エイリアス経由でマッチ

    def test_old_kanji_normalized(self):
        from core.matcher import find_missing_logs
        # 旧字（瀧澤）vs 新字（滝沢）も自動でマッチ
        events = [_event("瀧澤吉徳様 松戸さん")]
        logs = [ActivityLog(owner="松戸", customer="滝沢吉徳", log_date=date(2026, 5, 1), stage="初回")]
        result = find_missing_logs(events, logs, KEYWORDS, owner="松戸", target_date=date(2026, 5, 1))
        assert len(result) == 0

    def test_decorative_unicode_normalized(self):
        from core.matcher import find_missing_logs
        events = [_event("𝓐𝓴𝓪𝓷𝓮様 松戸さん")]
        logs = [ActivityLog(owner="松戸", customer="Akane", log_date=date(2026, 5, 1), stage="初回")]
        result = find_missing_logs(events, logs, KEYWORDS, owner="松戸", target_date=date(2026, 5, 1))
        assert len(result) == 0


class TestColumnLetterToIndex:
    def test_basic(self):
        from core.config import column_letter_to_index
        assert column_letter_to_index("A") == 0
        assert column_letter_to_index("B") == 1
        assert column_letter_to_index("Z") == 25
        assert column_letter_to_index("AA") == 26
        assert column_letter_to_index("AC") == 28

    def test_lowercase(self):
        from core.config import column_letter_to_index
        assert column_letter_to_index("ab") == 27

    def test_invalid(self):
        from core.config import column_letter_to_index
        assert column_letter_to_index("") == -1
        assert column_letter_to_index("1") == -1
