# Phase 7 — 販売終了ステータス

## 方針

公演日の翌日0:00以降、

- `SOLD_OUT` → 🔴 完売のまま保持
- `AUTO` → ⚫ 販売終了
- `AVAILABLE` → ⚫ 販売終了

と表示できるようにしました。

実際の会場販売終了時刻は告知時間とずれる可能性があるため、
公演当日中は販売中扱いを維持します。

## 現在はテストモード

`config.py`:

```python
ENABLE_SALES_END_STATUS = False
```

デフォルトはFalseです。

そのため過去公演でも、

```text
完売商品 → 完売
その他 → 販売中
```

のままテストできます。

本番運用前に、

```python
ENABLE_SALES_END_STATUS = True
```

へ変更します。

## 仮想現在時刻

`config.py` の `TEST_NOW_ISO` で、
任意の時刻を使って表示テストできます。

通常:

```python
TEST_NOW_ISO = None
```

販売前テスト:

```python
TEST_NOW_ISO = "2026-09-23T12:00:00+09:00"
```

販売中テスト:

```python
TEST_NOW_ISO = "2026-09-23T14:00:00+09:00"
```

販売終了テスト:

```python
ENABLE_SALES_END_STATUS = True
TEST_NOW_ISO = "2026-09-24T00:01:00+09:00"
```

## 重要

販売終了はDBのstatusを書き換えません。

DBには、

```text
AUTO
AVAILABLE
SOLD_OUT
```

だけを保存し、画面表示時に実効ステータスを計算します。

そのため、完売履歴は保持され、
将来「どの商品が完売したか」を確認できます。
