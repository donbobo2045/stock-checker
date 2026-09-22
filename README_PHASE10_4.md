# Phase 10.4 — 9/23本番用の定期取得・自動反映

Phase 10.4では、Streamlitの閲覧有無に依存しないよう、
GitHub ActionsからX APIを定期実行します。

## 本番構成

1. GitHub Actionsが9/23 JSTに5分間隔で起動
2. X Recent SearchでICEx完売投稿を取得
3. parser.pyで安全に解析
4. 解析成功分をdata/production_state.jsonへSOLD_OUTとして保存
5. since_id相当のcursorも同じJSONへ保存
6. 変更があったときだけGitHub Actions botがmainへcommit
7. Streamlit Community Cloudがmain更新を反映
8. 公開アプリはproduction_state.jsonをSQLiteより優先して表示

StreamlitのローカルSQLiteに依存しないため、
再起動・再デプロイ後も自動取得した完売状態を維持できます。

## 9/23のスケジュール

```yaml
cron: "2-57/5 12-23 23 9 *"
timezone: "Asia/Tokyo"
```

2026-09-23の12:02〜23:57 JSTに5分間隔で起動します。
スクリプト側でもevents.csvのイベント日を確認するため、
別年の9/23に誤って取得処理を行いません。

初回実行は9/23 00:00 JSTからその時点までを取得し、
以降は保存済みPost IDより新しい投稿だけを取得します。

## 検索条件

```text
from:SDE_STARDUSTBIN (ICEx OR #ICEx) 完売 -is:retweet
```

## 安全策

- parser成功かつtour_id / event date一致のみ自動SOLD_OUT
- 要確認投稿は自動反映しない
- 要確認が1件でもある間はcursorを進めない
- 解析成功投稿はcursor停止中でも冪等に反映
- 同一投稿を再取得しても同じ状態ならJSONを書き換えない
- X Bearer TokenはGitHub Actions Secretからのみ取得
- 公開StreamlitはPUBLIC_READ_ONLY=trueで管理機能を隠す

## Production state

`data/production_state.json` に以下を永続化します。

- SOLD_OUT商品
- source_post_id / source_post_url
- live cursor
- 要確認Post

このファイルにはBearer Tokenなどの秘密情報は保存しません。

## GitHub Actions Secret

Repository Settings -> Secrets and variables -> Actions で、

```text
X_BEARER_TOKEN
```

をRepository secretとして登録します。

## Streamlit Community Cloud

App settingsのSecretsに以下を設定します。

```toml
PUBLIC_READ_ONLY = true
```

公開版では以下を非表示にします。

- 開発者用仮想時刻
- X API手動取得
- 手動parser
- 在庫状態の手動selectbox
- DB管理UI

## GitHub Actionsの事前リハーサル

workflow_dispatchでは初期値として、

```text
rehearsal_date = 2026-09-19
rehearsal_cutoff = 18:00
dry_run = true
```

を使えます。

このモードは実X API取得とparser処理まで実行しますが、
production_state.jsonは変更しません。

## 注意

GitHub Actionsのscheduleは厳密なリアルタイム実行ではありません。
通常は5分間隔ですが、GitHub側の混雑で遅延する場合があります。
またproduction_state.jsonのcommit後にStreamlit側の再デプロイ時間も加わります。
