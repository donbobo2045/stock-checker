# Phase 10.1 — X API取得プレビュー

このフェーズでは、X APIのRecent Searchを使って、
@SDE_STARDUSTBIN のうち今回必要なポストだけを取得し、
既存の parser.py で解析結果を確認します。

## 現在の検索条件

```text
from:SDE_STARDUSTBIN (ICEx OR #ICEx) 完売 -is:retweet
```

つまり以下の条件です。

- 投稿元が @SDE_STARDUSTBIN
- 本文に ICEx または #ICEx を含む
- 本文に 完売 を含む
- リポストは除外

Recent Searchの対象は直近7日間です。
今後ほかのグループへ汎用化する場合は検索条件を差し替えます。

## 重要

- X側で条件を絞ってから取得するため、無関係なタイムライン投稿は取得しません。
- username -> user ID の追加API呼び出しも不要になりました。
- このフェーズではX APIから取得した結果をSQLiteへ自動反映しません。
- 解析成功 / 要確認 / 対象外の3分類で確認します。
- Bearer TokenはGitHubへコミットしません。

## ローカル設定

プロジェクト直下に以下を作成します。

```text
.streamlit/
└─ secrets.toml
```

```toml
X_BEARER_TOKEN = "YOUR_BEARER_TOKEN"
```

`.streamlit/secrets.toml` は `.gitignore` の対象です。

## Streamlit Community Cloud

App settings の Secrets に以下を登録します。

```toml
X_BEARER_TOKEN = "YOUR_BEARER_TOKEN"
```

保存後、アプリの「📡 X API取得テスト」から条件一致ポストを取得できます。

## 処理順

1. Recent Searchへ検索条件を渡す
2. 条件に一致したポストだけを取得
3. 各本文を既存parserへ渡す
4. DBへは書き込まず結果だけ表示

HTTP 402 / credits depleted の場合は、
クレジット残高不足として分かるメッセージを表示します。
