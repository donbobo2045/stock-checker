# Phase 10.1 — X API取得プレビュー

このフェーズでは、@SDE_STARDUSTBIN の最新ポストをX APIから取得し、
既存の parser.py で解析結果を確認できるようにします。

## 重要

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

保存後、アプリの「📡 X API取得テスト」から最新ポストを取得できます。

## 処理順

1. usernameからユーザーIDを取得
2. ユーザーIDから最新ポストを取得
3. 各本文を既存parserへ渡す
4. DBへは書き込まず結果だけ表示
