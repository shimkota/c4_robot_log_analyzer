# 天井施工ロボットログ分析 Webアプリ

CSV形式のロボットイベントログを行単位で解析し、`AutoStart` ごとのセッション、`AreaCycle`、Board 1〜4の状態、工程時間、元ログ行をブラウザで確認するためのFastAPIアプリです。

## クローンから起動まで

まず、このパッケージを任意の作業ディレクトリにクローンします。

```bash
git clone https://github.com/shimkota/c4_robot_log_analyzer.git
cd c4_robot_log_analyzer
```

Python環境を作成して依存パッケージを入れます。Python 3.11を推奨します。

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

アプリを起動します。

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8080
```

ブラウザで次のURLを開きます。

```text
http://localhost:8080
```

画面上部のプルダウンからCSVを選び、`解析` を押すと分析結果が表示されます。別のCSVを使う場合は、画面の `アップロード` から追加できます。

2回目以降は、次の手順だけで起動できます。

```bash
cd c4_robot_log_analyzer
source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8080
```

## Dockerで起動する場合

Dockerを使う場合は、Python環境の作成なしで起動できます。

```bash
git clone https://github.com/shimkota/c4_robot_log_analyzer.git
cd c4_robot_log_analyzer
docker compose up --build
```

起動後は同じく `http://localhost:8080` を開きます。`docker-compose.yml` はカレントディレクトリをコンテナ内の `/app` にマウントし、`--reload` 付きで起動します。

## 使い方

1. ブラウザで `http://localhost:8080` を開く
2. プルダウンから解析したいCSVを選ぶ
3. `解析` を押す
4. セッションタブで `S1`, `S2` などを切り替える
5. 工程時間グラフ、セッション合計、方向マップを確認する
6. グラフ、グリッドセル、Boardカードをクリックして詳細と元ログ行を見る

## ログファイルの置き場所

アプリはリポジトリ直下とサブフォルダ内の `*.csv` を自動で一覧化します。

```text
天井施工ロボットログ/
├── Work_20260110_113830_0908.csv
├── Work_20260112_082222_1427.csv
├── 0722ログ/
│   └── Work_20260722_084516_2571.csv
└── 0723ログ/
    └── Work_20260723_083922_3203.csv
```

画面からアップロードしたCSVは `data/uploads/` に保存され、アップロード済みログとして一覧に表示されます。

## テスト

依存パッケージをインストールした状態で実行します。

```bash
python -m pytest
```

Dockerで実行する場合は次のコマンドを使えます。

```bash
docker compose run --rm robot-log-analyzer pytest
```

## 主な機能

- 直下およびサブフォルダ内のCSVを一覧化
- CSVを固定列テーブルとして扱わず、1行ずつイベントとして解析
- `YYYYMMDD_HH:MM:SS_ffff` の末尾4桁を捨て、秒単位で保持
- 同一秒内の順序を元ログ行番号で保持
- `AutoStart` ごとにセッション分割
- `AreaCycle` ごとに位置調整、スキャン、計算、ボード取得、取り付け、逆再生、置く動作を工程化
- セッション別、AreaCycle別の工程時間をグラフ表示
- 施工方向と次列方向を切り替えられる方向マップを表示
- Board配置を 1=右上、2=左上、3=左下、4=右下 として表示
- `Board?Skip=True` をP表示
- `Board?Pt` の1値目を差し入れ、2値目を取り付けモーションとして保持
- `ReverseAction` / `NeedRemoveBoard` を逆再生、`BoardRelease` を置く動作として集計
- グリッドセル、Boardカード、グラフから詳細と元ログ行を確認
- 未確定のモーション向きと8方向障害物配置を `config/*.yaml` に分離

## 設定ファイル

設定は `config/` 配下のYAMLで管理します。

```text
config/
├── motion_map.yaml            # モーションA〜E、差し入れ、取り付け方向の定義
├── obstacle_directions.yaml   # 8方向障害物配置の定義
└── phase_groups.yaml          # 工程グループ名の定義
```

API経由で設定を更新すると、対応するYAMLファイルに保存されます。

## 構成

```text
app/
├── main.py              # FastAPIアプリ本体
├── api/routes.py        # APIエンドポイント
├── parser/              # CSV行、イベント、状態遷移の解析
├── analysis/            # サマリ、工程時間、状態集計
├── templates/index.html # 画面HTML
└── static/              # JavaScriptとCSS
config/                  # 解析・表示設定
data/uploads/            # アップロードCSV
tests/                   # pytest
```

## 主なAPI

```text
GET  /api/logs
POST /api/logs/parse
POST /api/logs/upload
GET  /api/analysis/summary
GET  /api/analysis/sessions
GET  /api/analysis/timeline
GET  /api/analysis/session-totals
GET  /api/analysis/grid
GET  /api/analysis/areas/{area_id}
GET  /api/analysis/boards/{attempt_id}
GET  /api/settings
PUT  /api/settings
```

## トラブルシューティング

`python` コマンドが見つからない場合は、環境に合わせて `python3` または `python3.11` を使ってください。

```bash
python3 -m venv .venv
```

`8080` 番ポートが使用中の場合は、別のポートで起動します。

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8081
```
