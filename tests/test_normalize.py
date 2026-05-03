from core.normalize import normalize, normalize_status


class TestNormalize:
    def test_old_kanji_to_new(self):
        # 旧字 → 新字
        assert normalize("瀧澤吉徳") == normalize("滝沢吉徳")
        assert normalize("邊見") == normalize("辺見")

    def test_decorative_unicode(self):
        # 装飾Unicode → 標準英字
        assert normalize("𝓐𝓴𝓪𝓷𝓮") == normalize("Akane")

    def test_full_width_to_half(self):
        assert normalize("ＡＢＣ１２３") == normalize("abc123")

    def test_katakana_hiragana(self):
        assert normalize("ツグミ") == normalize("つぐみ")

    def test_whitespace_removed(self):
        assert normalize("田中 太郎") == normalize("田中太郎")
        assert normalize("田中　太郎") == normalize("田中太郎")

    def test_punctuation_removed(self):
        assert normalize("megumi.k") == normalize("megumik")

    def test_case_insensitive(self):
        assert normalize("AYANE") == normalize("ayane")

    def test_empty(self):
        assert normalize("") == ""


class TestNormalizeStatus:
    def test_keiyaku_variants(self):
        assert normalize_status("契約済") == "契約済"
        assert normalize_status("契約済み") == "契約済"
        assert normalize_status("契約完了") == "契約済"

    def test_cooling_off_variants(self):
        # 中黒の有無
        a = normalize_status("クーリングオフ")
        b = normalize_status("クーリング・オフ")
        assert a == b

    def test_half_width_kana(self):
        # 半角カナ → 全角カナ（NFKC）で同一化
        assert normalize_status("ｸｰﾘﾝｸﾞｵﾌ") == normalize_status("クーリングオフ")

    def test_blank(self):
        assert normalize_status("") == ""
