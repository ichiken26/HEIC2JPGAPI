# HEIC2JPG API

DB を使わない FastAPI 製の HEIC/HEIF -> JPG 変換 API です。別プロジェクトから外部 API として呼び出す用途を想定しています。

## セットアップ

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
```

## 起動

```bash
uvicorn app.main:app --reload
```

API は `http://127.0.0.1:8000` で起動します。

## エンドポイント

### `GET /health`

ヘルスチェックです。

### `POST /convert`

`multipart/form-data` の `file` に HEIC/HEIF ファイルを渡すと、`image/jpeg` を返します。

```bash
curl -X POST \
  -F "file=@sample.heic;type=image/heic" \
  http://127.0.0.1:8000/convert \
  --output sample.jpg
```

テスト時は、次のスクリプトを使うと毎回 `curl` を書かずに実行できます。

```bash
chmod +x scripts/test_convert.sh
./scripts/test_convert.sh
```

デフォルトでは `testImg` 直下の `*.HEIC` / `*.heic` をまとめて `testImg/converted` に出力します。

引数で入力ディレクトリ・出力ディレクトリ・URL を上書きできます。

```bash
./scripts/test_convert.sh /path/to/input_dir /path/to/output_dir http://127.0.0.1:8000/convert
```

対応 MIME:

- `image/heic`
- `image/heif`
- `image/heic-sequence`
- `image/heif-sequence`

アップロード時の MIME に加えて、ファイル先頭の HEIF コンテナシグネチャも検証します。

## 環境変数

プレフィックスは `HEIC2JPG_` です。

| 変数 | デフォルト | 内容 |
| --- | ---: | --- |
| `HEIC2JPG_MAX_UPLOAD_BYTES` | `26214400` | 最大アップロードサイズ |
| `HEIC2JPG_JPEG_QUALITY` | `90` | JPG 品質 |
| `HEIC2JPG_JPEG_MAX_OUTPUT_BYTES` | `819200` | 変換後 JPG の最大サイズ（バイト） |

## AWS Lambda で公開する場合

```bash
mkdir -p build
pip install -r requirements.txt -t build
cp -r app build/
cd build
zip -r ../function.zip .
```

Lambda の handler は次を指定します。

```text
app.main.handler
```

API Gateway HTTP API または REST API と接続して利用してください。HEIC/HEIF と JPG はバイナリデータのため、API Gateway 側でバイナリメディアタイプとして `image/heic`, `image/heif`, `image/jpeg`, `multipart/form-data` を扱える設定にしてください。

### GitHub push で自動デプロイ（CD）

`main` ブランチに push すると、GitHub Actions で Lambda デプロイされます。

1. GitHub Repository Variables を設定
   - `AWS_REGION`（例: `ap-northeast-1`）
   - `LAMBDA_FUNCTION_NAME`
2. GitHub Repository Secret を設定
   - `AWS_DEPLOY_ROLE_ARN`（GitHub OIDC で Assume する IAM Role ARN）
3. ワークフロー
   - `.github/workflows/deploy-lambda.yml`

このロールには最低限 `lambda:UpdateFunctionCode` 権限が必要です。

## テスト

```bash
pytest
```
