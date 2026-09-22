from types import SimpleNamespace

from x_preview import IGNORED, PARSED, REVIEW, classify_parse_result


def make_result(
    *,
    is_relevant,
    reason,
    tour_id=None,
):
    return SimpleNamespace(
        is_relevant=is_relevant,
        reason=reason,
        tour_id=tour_id,
    )


def test_success_is_parsed():
    result = make_result(
        is_relevant=True,
        reason="完売情報として解析成功",
        tour_id="FRESHEST_2026",
    )
    assert classify_parse_result(result) == PARSED


def test_other_tour_is_ignored():
    result = make_result(
        is_relevant=False,
        reason="対象ツアーを特定できない",
        tour_id=None,
    )
    assert classify_parse_result(result) == IGNORED


def test_target_tour_non_sold_out_post_is_ignored():
    result = make_result(
        is_relevant=False,
        reason="完売情報または本日分完売の明示がないため対象外",
        tour_id="FRESHEST_2026",
    )
    assert classify_parse_result(result) == IGNORED


def test_target_tour_parse_failure_requires_review():
    result = make_result(
        is_relevant=False,
        reason="商品を特定できない: テスト商品",
        tour_id="FRESHEST_2026",
    )
    assert classify_parse_result(result) == REVIEW
