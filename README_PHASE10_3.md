# Phase 10.3 — X API解析結果を確認して在庫へ反映

Phase 10.3では、Phase 10.2のイベント日ベース取得とsince_id増分取得に、
「解析成功したX投稿を確認後にSQLiteへSOLD_OUT反映する」処理を追加します。

## 安全方針

X APIで取得した投稿は、次の順で処理します。

1. X側で投稿元・ICEx・完売を絞り込み
2. parser.py でツアー / 公演 / 商品 / variantを解析
3. X取得対象のtour_id・イベント日とparser結果が一致するか再確認
4. 解析成功のみSOLD_OUT候補として表示
5. ユーザー確認後にSQLiteへ反映
6. 問題がない場合だけsince_idも同時に進める

## 要確認投稿がある場合

1件でも「要確認」がある場合は、cursorを進めません。

解析成功分だけSOLD_OUTへ反映することはできますが、
要確認投稿を飛ばさないためsince_idはそのままです。

## 要確認がない場合

「SOLD_OUTへ反映 ＋ since_idを保存」ボタンで、

- inventory_statusへのSOLD_OUT反映
- source_post_id / source_post_urlの保存
- x_sync_stateのsince_id更新

を1つのSQLiteトランザクションで実行します。

途中で失敗した場合に
「在庫だけ更新されたがcursorだけ進んだ」
という不整合が起きないようにしています。

## 対象外投稿のみの場合

在庫DBは変更せず、対象外投稿を処理済みとしてsince_idだけ進められます。

## リハーサル

9/19などRecent Search範囲内の過去イベント日で、

- 17:00まで初回取得
- cursor保存
- 18:00まで増分取得
- 取得結果をSOLD_OUTへ反映

という本番相当の確認ができます。

リハーサルでSOLD_OUTへ反映すると、ローカルinventory.dbの
該当過去公演セッションへ実際に保存されます。
必要なら既存の管理UIからセッションをAUTOへ戻せます。

## 本番当日

本番当日はscopeを以下の形式で分離します。

```text
live:<tour_id>:<YYYY-MM-DD>
```

例:

```text
live:FRESHEST_2026:2026-09-23
```

Phase 10.2のpreview cursorとは分離されるため、
9/23は本番用cursorなしの初回取得から開始できます。

## まだ自動化していないこと

Phase 10.3は「取得 → 解析 → 確認 → 反映」までです。
定期実行や完全自動反映はまだ有効にしません。
