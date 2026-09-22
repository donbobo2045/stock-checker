from pathlib import Path

import pytest

from parser import SoldOutPostParser


BASE_DIR = Path(__file__).resolve().parents[1]
GOODS = BASE_DIR / "data" / "goods.csv"
EVENTS = BASE_DIR / "data" / "events.csv"


@pytest.fixture(scope="module")
def parser():
    return SoldOutPostParser.from_csv(GOODS, EVENTS)


SOLD_OUT_SAMPLES = [
    (
        """#ICEx
『ICEx Fourth Concert Tour 2026 ''FRESHest!!''』
@大阪・NHK大阪ホール Day2🧊🐙
【完売情報】
・トレカケース（千田）
本日分完売です！
ありがとうございます。""",
        "FRESHEST_OSAKA_0919",
        [("freshest_card_case", "千田波空斗")],
    ),
    (
        """『ICEx Fourth Concert Tour 2026 ''FRESHest!!''』
@大阪・NHK大阪ホール Day2🧊🐙
【完売情報】
・うちわ（竹野）
本日分完売です！
ありがとうございます。""",
        "FRESHEST_OSAKA_0919",
        [("freshest_uchiwa", "竹野世梛")],
    ),
    (
        """#ICEx
『ICEx Fourth Concert Tour 2026 ''FRESHest!!''』
@大阪・NHK大阪ホール Day1
【完売情報】
・ペンライト
・うちわ（阿久根）
・Tシャツ（M）
本日分完売です！
ありがとうございます。""",
        "FRESHEST_OSAKA_0918",
        [
            ("icex_penlight_ver4", ""),
            ("freshest_uchiwa", "阿久根温世"),
            ("freshest_tshirt", "M"),
        ],
    ),
    (
        """#ICEx
『ICEx Fourth Concert Tour 2026 ''FRESHest!!''』
@大阪・NHK大阪ホール Day1
【完売情報】
・アクリルスタンド（阿久根）
・アクリルスタンド（中村）
本日分完売です！
ありがとうございます。""",
        "FRESHEST_OSAKA_0918",
        [
            ("freshest_acrylic_stand", "阿久根温世"),
            ("freshest_acrylic_stand", "中村旺太郎"),
        ],
    ),
    (
        """#ICEx
『ICEx Fourth Concert Tour 2026 ''FRESHest!!''』
8/29(土) 福岡・福岡国際会議場メインホール Day1
【完売情報】
・ICEx FRESHest!! トレカケース (竹野)
本日分完売です！
ありがとうございます。""",
        "FRESHEST_FUKUOKA_0829",
        [("freshest_card_case", "竹野世梛")],
    ),
    (
        """#ICEx
『ICEx Fourth Concert Tour 2026 ''FRESHest!!''』
8/22(土) 愛知・COMTEC PORTBASE公演 Day2
【完売情報】
・ICEx FRESHest!! アクリルスタンド
種類：竹野世梛
本日分完売です！
ありがとうございます。""",
        "FRESHEST_AICHI_0822",
        [("freshest_acrylic_stand", "竹野世梛")],
    ),
    (
        """#ICEx
『ICEx Fourth Concert Tour 2026 ''FRESHest!!''』
8/21(金) 愛知・COMTEC PORTBASE公演 Day1
【完売情報】
・ICEx FRESHest!! Tシャツ
サイズ：M
本日分完売です！
ありがとうございます。""",
        "FRESHEST_AICHI_0821",
        [("freshest_tshirt", "M")],
    ),
]


@pytest.mark.parametrize("text,expected_session,expected_items", SOLD_OUT_SAMPLES)
def test_sold_out_samples(parser, text, expected_session, expected_items):
    result = parser.parse(text)
    assert result.is_relevant is True, result.reason
    assert result.sales_session_id == expected_session
    assert [(x.item_id, x.variant) for x in result.items] == expected_items
    assert all(x.status == "SOLD_OUT" for x in result.items)


IRRELEVANT_SAMPLES = [
    """#ICEx
本日開催！
🧊ICEx Fourth Concert Tour 2026 ''FRESHest!!''🧊
@大阪・NHK大阪ホール Day2
【共通先行販売】9/19(土)
⏰10:00～12:00
既存商品の販売もございます
ラインナップは既存商品一覧をご覧下さい""",
    """#Sakurashimeji
Sakurashimeji FREE LIVE TOUR 2026『あなたの声になれたら』
@千葉県・アリオ蘇我
フリーでグッズを販売中
※一部売り切れ商品ございます""",
    """【グッズ売り場 キャッシュレス決済のご案内】""",
    """#MILK
M!LK ARENA TOUR 2026-2027
シャカリキレボリューション
【9/26(土)、27(日)福岡公演】
会場販売＆整理券配布のお知らせ""",
]


@pytest.mark.parametrize("text", IRRELEVANT_SAMPLES)
def test_irrelevant_samples(parser, text):
    assert parser.parse(text).is_relevant is False


def test_unknown_item_is_not_auto_applied(parser):
    result = parser.parse("""#ICEx
『ICEx Fourth Concert Tour 2026 ''FRESHest!!''』
@大阪・NHK大阪ホール Day1
【完売情報】
・存在しない商品
本日分完売です！""")
    assert result.is_relevant is False
    assert "商品を特定できない" in result.reason


def test_variant_required_but_missing_is_not_auto_applied(parser):
    result = parser.parse("""#ICEx
『ICEx Fourth Concert Tour 2026 ''FRESHest!!''』
@大阪・NHK大阪ホール Day1
【完売情報】
・アクリルスタンド
本日分完売です！""")
    assert result.is_relevant is False
    assert "variantが必要" in result.reason


def test_alias_penra_maps_to_penlight(parser):
    result = parser.parse("""#ICEx
『ICEx Fourth Concert Tour 2026 ''FRESHest!!''』
@大阪・NHK大阪ホール Day1
【完売情報】
・ペンラ
本日分完売です！""")
    assert result.is_relevant is True, result.reason
    assert [(x.item_id, x.variant) for x in result.items] == [
        ("icex_penlight_ver4", "")
    ]


def test_alias_akusuta_maps_to_acrylic_stand(parser):
    result = parser.parse("""#ICEx
『ICEx Fourth Concert Tour 2026 ''FRESHest!!''』
@大阪・NHK大阪ホール Day1
【完売情報】
・アクスタ（中村）
本日分完売です！""")
    assert result.is_relevant is True, result.reason
    assert [(x.item_id, x.variant) for x in result.items] == [
        ("freshest_acrylic_stand", "中村旺太郎")
    ]


def test_specific_photo_alias_maps_to_vol30(parser):
    result = parser.parse("""#ICEx
『ICEx Fourth Concert Tour 2026 ''FRESHest!!''』
@大阪・NHK大阪ホール Day1
【完売情報】
・生写真セット vol.30
本日分完売です！""")
    assert result.is_relevant is True, result.reason
    assert [(x.item_id, x.variant) for x in result.items] == [
        ("photo_set_vol30", "")
    ]


def test_ambiguous_photo_alias_is_not_auto_applied(parser):
    result = parser.parse("""#ICEx
『ICEx Fourth Concert Tour 2026 ''FRESHest!!''』
@大阪・NHK大阪ホール Day1
【完売情報】
・生写真セット
本日分完売です！""")
    assert result.is_relevant is False
    assert "複数候補" in result.reason
    assert "photo_set_vol30" in result.reason
    assert "photo_set_vol31" in result.reason


def test_sold_out_without_heading_is_accepted(parser):
    text = """#ICEx

『ICEx Fourth Concert Tour 2026 ''FRESHest!!''』
@大阪・NHK大阪ホール Day1

・アクリルスタンド（阿久根）
・アクリルスタンド（八神）

本日分完売です！
ありがとうございます。"""

    result = parser.parse(text)

    assert result.is_relevant is True, result.reason
    assert result.sales_session_id == "FRESHEST_OSAKA_0918"
    assert [
        (item.item_id, item.variant)
        for item in result.items
    ] == [
        ("freshest_acrylic_stand", "阿久根温世"),
        ("freshest_acrylic_stand", "八神遼介"),
    ]


def test_other_tour_is_rejected_before_sold_out_wording_check(parser):
    text = """#ICEx
🧊 ICEx 3rd Anniversary Concert 2026 "ICEx School"
神奈川・パシフィコ横浜 国立大ホール公演

【完売情報】
・ミニフォトセット vol.1

完売です！
ありがとうございます。

#ICEx"""

    result = parser.parse(text)

    assert result.is_relevant is False
    assert result.reason == "対象ツアーを特定できない"


def test_prefecture_only_and_second_day_label(parser):
    text = """#ICEx

『ICEx Fourth Concert Tour 2026 ''FRESHest!!''』
@大阪 2日目

【完売情報】
・うちわ（山本）

本日分完売です！"""

    result = parser.parse(text)

    assert result.is_relevant is True, result.reason
    assert result.sales_session_id == "FRESHEST_OSAKA_0919"
    assert result.date == "2026-09-19"
    assert [(x.item_id, x.variant) for x in result.items] == [
        ("freshest_uchiwa", "山本龍人")
    ]


def test_fuzzy_tour_title_typo_and_abbreviation(parser):
    text = """#ICEx

『ICEx Forth Tour 2026 ''FRESH''』
@大阪 2日目

【完売情報】
・うちわ（山本）

本日分完売です！"""

    result = parser.parse(text)

    assert result.is_relevant is True, result.reason
    assert result.tour_id == "FRESHEST_2026"
    assert result.sales_session_id == "FRESHEST_OSAKA_0919"
    assert [(x.item_id, x.variant) for x in result.items] == [
        ("freshest_uchiwa", "山本龍人")
    ]


def test_japanese_second_day_label(parser):
    text = """#ICEx
『ICEx Fourth Concert Tour 2026 ''FRESHest!!''』
@大阪 二日目
【完売情報】
・うちわ（山本）
本日分完売です！"""

    result = parser.parse(text)
    assert result.is_relevant is True, result.reason
    assert result.sales_session_id == "FRESHEST_OSAKA_0919"


def test_prefecture_only_without_date_or_day_is_ambiguous(parser):
    text = """#ICEx
『ICEx Fourth Concert Tour 2026 ''FRESHest!!''』
@大阪
【完売情報】
・うちわ（山本）
本日分完売です！"""

    result = parser.parse(text)
    assert result.is_relevant is False
    assert result.reason == "公演を特定できない"


def test_day_label_without_region_is_rejected(parser):
    text = """#ICEx

『ICEx Forth Concert Tour 2026 ''FRESHest!!''』
@2日目

【完売情報】
・うちわ（山本）

本日分完売です！"""

    result = parser.parse(text)

    assert result.is_relevant is False
    assert result.reason == "公演を特定できない"


def test_region_and_second_day_is_accepted(parser):
    text = """#ICEx

『ICEx Forth Concert Tour 2026 ''FRESHest!!''』
@大阪 2日目

【完売情報】
・うちわ（山本）

本日分完売です！"""

    result = parser.parse(text)

    assert result.is_relevant is True, result.reason
    assert result.sales_session_id == "FRESHEST_OSAKA_0919"
    assert result.date == "2026-09-19"


def test_region_only_with_multiple_dates_is_rejected(parser):
    text = """#ICEx

『ICEx Fourth Concert Tour 2026 ''FRESHest!!''』
@大阪

【完売情報】
・うちわ（山本）

本日分完売です！"""

    result = parser.parse(text)

    assert result.is_relevant is False
    assert result.reason == "公演を特定できない"


def test_unique_region_without_day_is_accepted(parser):
    text = """#ICEx

『ICEx Fourth Concert Tour 2026 ''FRESHest!!''』
@東京

【完売情報】
・ペンラ

本日分完売です！"""

    result = parser.parse(text)

    assert result.is_relevant is True, result.reason
    assert result.sales_session_id == "FRESHEST_TOKYO_0923"
    assert result.date == "2026-09-23"


def test_tokyo_photo_set_32_is_available(parser):
    text = """#ICEx
『ICEx Fourth Concert Tour 2026 ''FRESHest!!''』
@東京
・PHOTO SET vol.32
本日分完売です！"""

    result = parser.parse(text)
    assert result.is_relevant is True, result.reason
    assert result.sales_session_id == "FRESHEST_TOKYO_0923"
    assert [(x.item_id, x.variant) for x in result.items] == [
        ("photo_set_vol32", "")
    ]


def test_osaka_photo_set_32_is_rejected_as_not_scheduled(parser):
    text = """#ICEx
『ICEx Fourth Concert Tour 2026 ''FRESHest!!''』
@大阪 Day1
・PHOTO SET vol.32
本日分完売です！"""

    result = parser.parse(text)
    assert result.is_relevant is False
    assert "販売予定商品ではありません" in result.reason


def test_aichi_bokunchi_existing_item_is_available(parser):
    text = """#ICEx
『ICEx Fourth Concert Tour 2026 ''FRESHest!!''』
8/21 愛知
・BOKUNCHI Mini Pouch
本日分完売です！"""

    result = parser.parse(text)
    assert result.is_relevant is True, result.reason
    assert [(x.item_id, x.variant) for x in result.items] == [
        ("icex_bokunchi_mini_pouch", "")
    ]


def test_osaka_sutapii_sticker_is_available(parser):
    text = """#ICEx
『ICEx Fourth Concert Tour 2026 ''FRESHest!!''』
@大阪 Day1
・すたぴぃのしーる
本日分完売です！"""

    result = parser.parse(text)
    assert result.is_relevant is True, result.reason
    assert [(x.item_id, x.variant) for x in result.items] == [
        ("sutapii_sticker", "")
    ]


def test_aichi_sutapii_sticker_is_rejected(parser):
    text = """#ICEx
『ICEx Fourth Concert Tour 2026 ''FRESHest!!''』
8/21 愛知
・すたぴぃのしーる
本日分完売です！"""

    result = parser.parse(text)
    assert result.is_relevant is False
    assert "販売予定商品ではありません" in result.reason


def test_generic_random_acrylic_keychain_alias_is_ambiguous(parser):
    text = """#ICEx
『ICEx Fourth Concert Tour 2026 ''FRESHest!!''』
8/21 愛知
・ランダムアクキー
本日分完売です！"""

    result = parser.parse(text)
    assert result.is_relevant is False
    assert "曖昧" in result.reason


def test_fukuoka_wrong_date_but_day2_prefers_day_label_yagami(parser):
    text = """#ICEx

『ICEx Fourth Concert Tour 2026 ''FRESHest!!''』
8/29(土) 福岡・福岡国際会議場メインホール Day2

【完売情報】
・ICEx FRESHest!! トレカケース (八神)

本日分完売です！
ありがとうございます。"""

    result = parser.parse(text)

    assert result.is_relevant is True, result.reason
    assert result.sales_session_id == "FRESHEST_FUKUOKA_0830"
    assert result.date == "2026-08-30"
    assert [(x.item_id, x.variant) for x in result.items] == [
        ("freshest_card_case", "八神遼介")
    ]


def test_fukuoka_wrong_date_but_day2_prefers_day_label_takeno(parser):
    text = """#ICEx

『ICEx Fourth Concert Tour 2026 ''FRESHest!!''』
8/29(土) 福岡・福岡国際会議場メインホール Day2

【完売情報】
・ICEx FRESHest!! トレカケース (竹野)

本日分完売です！
ありがとうございます。"""

    result = parser.parse(text)

    assert result.is_relevant is True, result.reason
    assert result.sales_session_id == "FRESHEST_FUKUOKA_0830"
    assert result.date == "2026-08-30"
    assert [(x.item_id, x.variant) for x in result.items] == [
        ("freshest_card_case", "竹野世梛")
    ]


def test_fukuoka_day1_still_maps_to_first_day(parser):
    text = """#ICEx
『ICEx Fourth Concert Tour 2026 ''FRESHest!!''』
8/29(土) 福岡・福岡国際会議場メインホール Day1
・うちわ（山本）
本日分完売です！"""

    result = parser.parse(text)

    assert result.is_relevant is True, result.reason
    assert result.sales_session_id == "FRESHEST_FUKUOKA_0829"
    assert result.date == "2026-08-29"


def test_invalid_day_number_does_not_fall_back_to_date(parser):
    text = """#ICEx
『ICEx Fourth Concert Tour 2026 ''FRESHest!!''』
8/29(土) 福岡・福岡国際会議場メインホール Day3
・うちわ（山本）
本日分完売です！"""

    result = parser.parse(text)

    assert result.is_relevant is False
    assert result.reason == "公演を特定できない"
