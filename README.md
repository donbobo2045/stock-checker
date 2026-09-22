# スタダ便 グッズ在庫チェッカー — Phase 2

## このPhaseでできること

- `goods.csv` を読み込む
- `events.csv` を読み込む
- ツアーを選ぶ
- 公演日 / 会場 / 1部・2部を選ぶ
- そのツアーのグッズ一覧を表示する
- 在庫状態を手動で変更する
- 在庫状態をSQLiteへ保存する
- 同じ `sales_session_id` を持つ1部/2部で在庫状態を共有する

まだX APIには接続しません。

---

## ファイル構成

```text
stadabin_phase2/
├─ app.py
├─ database.py
├─ inventory.db        # 初回起動時に自動作成
├─ requirements.txt
├─ README.md
└─ data/
   ├─ goods.csv
   └─ events.csv
```

---

## 起動

```bash
python -m venv .venv
```

Windows:

```bash
.venv\Scripts\activate
```

依存ライブラリをインストール:

```bash
pip install -r requirements.txt
```

起動:

```bash
streamlit run app.py
```

---

## 在庫状態

以下の3状態を使用します。

```text
UNKNOWN
AVAILABLE
SOLD_OUT
```

画面では、

```text
⚪ 不明
🟢 販売中
🔴 完売
```

と表示します。

---

## 在庫管理キー

在庫は、

```text
sales_session_id
+
item_id
+
variant
```

で管理します。

そのため、たとえば同日1部/2部が同じ `sales_session_id` を持つ場合、
1部で「完売」に変更した商品は2部を開いても「完売」のままです。

---

## 確認してほしいこと

Phase 2では特に以下を確認してください。

1. 公演選択が正しいか
2. 商品一覧が正しいか
3. メンバー別商品が正しく並ぶか
4. 在庫状態を変更すると保存されるか
5. Streamlitを再起動しても状態が残るか
6. 同日1部/2部で在庫状態が共有されるか
7. 別日へ切り替えると在庫状態が分離されるか

---

## 次のPhase

この動作が確認できたら、

```text
Phase 3
スタダ便の実際の投稿文をサンプルとして解析
```

へ進みます。

そこで、

- 商品名
- メンバー名 / variant
- 完売表現
- 公演日

を文字列から取り出す `parser.py` を作ります。
