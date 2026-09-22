# Phase 5 — 販売前 / 販売中 / 完売の自動表示

## 追加したもの

```text
data/sales_sessions.csv
status_logic.py
scripts/check_sales_sessions.py
```

## 表示ルール

DBの初期状態は `AUTO`。

```text
AUTO + 販売開始前
    → 🟡 販売前

AUTO + 販売開始時刻以降
    → 🟢 販売中

SOLD_OUT
    → 🔴 完売
```

`AVAILABLE` は手動で「販売中」に固定したい場合の
オーバーライド用です。

## 既存DB

旧バージョンの `UNKNOWN` は、
アプリ起動時に自動的に `AUTO` へ移行します。

## sales_sessions.csv

物販在庫共有単位ごとに、
最初の会場販売開始時刻を管理します。

列：

```csv
sales_session_id,tour_id,date,sales_start_time,timezone,source_url,note
```

## 自動更新

在庫一覧部分はStreamlitのfragmentで60秒ごとに再描画します。

そのため販売開始時刻をまたぐと、
AUTOの商品は画面上で

```text
販売前 → 販売中
```

へ自動的に切り替わります。

## 手動変更

各商品は以下から選択できます。

```text
自動判定
販売中（手動固定）
完売
```

通常は `自動判定` のまま運用してください。

## チェック

```bash
python scripts/check_sales_sessions.py
pytest -q
```

## 公式販売時刻

- 愛知 8/21: 14:30
- 愛知 8/22: 10:00
- 福岡 8/29: 13:00
- 福岡 8/30: 10:00
- 大阪 9/18: 15:00
- 大阪 9/19: 10:00
- 東京 9/23: 13:00

詳細は `sales_sessions.csv` の `source_url` と `note` を参照。
