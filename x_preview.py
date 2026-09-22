from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from parser import ParseResult


PARSED = "parsed"
IGNORED = "ignored"
REVIEW = "review"


def classify_parse_result(result: "ParseResult") -> str:
    """
    Classify an existing parser result for the X API preview.

    - parsed: safe parser success
    - ignored: clearly not this tour / not a sold-out post
    - review: this tour looks relevant, but automatic parsing failed
    """
    if result.is_relevant:
        return PARSED

    if result.tour_id is None:
        return IGNORED

    if (
        result.reason
        == "完売情報または本日分完売の明示がないため対象外"
    ):
        return IGNORED

    return REVIEW
