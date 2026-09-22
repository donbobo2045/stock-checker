# Phase 10.2 — イベント日ベース取得 + since_id増分取得

Phase 10.2では、X APIのRecent Searchをツアーの開催日単位で使い、
同じイベント日の2回目以降は since_id で新規ポストだけを取得します。

## 検索条件

```text
from:SDE_STARDUSTBIN (ICEx OR #ICEx) 完売 -is:retweet
```

## 初回取得

対象イベント日の 00:00 JST から指定した終了時刻までを検索します。

例：2026-09-19 15:00 JSTまでリハーサルする場合

```text
start_time = 2026-09-18T15:00:00Z
end_time   = 2026-09-19T06:00:00Z
```

## 増分取得

初回取得後に取得結果の最新Post IDをテスト用cursorとして保存できます。
次回は start_time を使わず、since_id + end_time で取得します。

X Recent Searchでは start_time と since_id は同時指定できないため、
初回と増分でパラメータを切り替えます。

## リハーサルモード

Recent Searchでイベント日全体を取得可能な過去公演だけを選択できます。

2026-09-22時点では、今回のFRESHest!!ツアーでは
9/18と9/19がリハーサル対象です。
9/19を選び、まず15:00まで取得してcursorを保存し、
その後18:00へ進めることで増分取得を確認できます。

## 本番当日モード

実際のJST日付が events.csv に登録された開催日と一致するときだけ有効です。

2026-09-23は以下の流れになります。

1. 初回: 9/23 00:00 JSTから現在時刻まで取得
2. 最新Post IDをcursorに保存
3. 2回目以降: since_idより新しい投稿だけ取得

Phase 10.2ではcursorの保存はテスト用で、在庫DBへの自動反映は行いません。
本番用の自動反映とproduction cursorは次フェーズで分離します。

## 過去公演について

Recent Searchの start_time は直近7日以内に制限されるため、
8月公演のような古い開催日はこの画面では取得しません。
必要ならSearch Allまたは手動初期登録でバックフィルします。

## Secrets

```toml
X_BEARER_TOKEN = "YOUR_BEARER_TOKEN"
```

ローカルは `.streamlit/secrets.toml`、
Streamlit Community CloudはApp settingsのSecretsに設定します。
