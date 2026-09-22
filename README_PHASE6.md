# Phase 6 — 公演ごとの販売商品カタログ

## 背景

`goods.csv` は「ツアーに関係する商品マスター」ですが、
すべての商品がすべての公演で販売されるとは限りません。

そこで、

```text
data/sales_session_items.csv
```

を追加し、

```text
sales_session_id + item_id + variant
```

で「その物販セッションで販売予定の商品」を明示します。

## 今回反映した公式情報

### 愛知・福岡から販売

- PHOTO SET vol.30
- PHOTO SET vol.31
- FRESHest!! ポーチ
- 従来のFRESHest!!グッズ
- ICEx Penlight ver.4
- ICEx BOKUNCHI Mini Pouch
- ICEx Fight!! タオル
- ランダムアクリルキーホルダー
- ICEx ROUTE-8 Drawstring Bag

### 大阪から追加

- すたぴぃのしーる

### 東京から追加

- PHOTO SET vol.32
- PHOTO SET vol.33

## 画面表示

Streamlitは `goods.csv` の全商品を表示するのではなく、
選択した `sales_session_id` に存在する商品だけを表示します。

そのため東京限定のPHOTO SET vol.32 / 33が、
愛知・福岡・大阪に表示されることはありません。

## parser

完売投稿で商品自体を特定できても、
` sales_session_items.csv ` にその商品がなければ、

```text
この物販セッションの販売予定商品ではありません
```

としてDBへ反映しません。

## aliases

新商品・既存商品の別名も追加しました。

曖昧になりやすい以下は、意図的に複数候補として登録しています。

- `ポーチ`
- `タオル`
- `アクキー`
- `ランダムアクキー`
- `生写真`
- `生写真セット`
- `PHOTO SET`

具体的な商品名・vol番号がなければ自動判定しません。

## 自動チェック

```bash
python scripts/check_sales_session_items.py
pytest -q
```
