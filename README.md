# TimeSignal-for-Discord

毎時00分ぴったりにDiscordの指定チャンネルに時報（「〇〇時をお知らせします」）を送信するBotです。
誤差が出ないように、システム時刻の次の00分00秒まで正確にスリープして待機する方式を採用しています。

## 機能
- スラッシュコマンドを使ったチャンネルの指定・解除
- 時報の一時停止と再開機能
- 設定はJSONファイルに自動保存され、Botの再起動時にも維持されます
- セキュリティのため、コマンドの実行は**管理者権限（Administrator）**を持つユーザーに限定されています

## 必要な環境
- Python 3.8 以上
- 以下のライブラリ（`requirements.txt`よりインストール）
  - `discord.py`
  - `python-dotenv`

## セットアップ手順

1. **Botアカウントの作成**
   [Discord Developer Portal](https://discord.com/developers/applications) にてアプリケーションとBotを作成し、Token（トークン）を取得します。
   Botをサーバーに招待する際は、スコープとして `bot` と `applications.commands` を指定し、権限として `Send Messages` を付与してください。

2. **依存パッケージのインストール**
   ```bash
   pip install -r requirements.txt
   ```

3. **環境変数の設定**
   `.env.example` をコピーして `.env` というファイルを作成し、取得したトークンを設定してください。
   ```env
   DISCORD_TOKEN=ここにあなたの_bot_トークンを貼り付けます
   ```

4. **Botの起動**
   ```bash
   python bot.py
   ```

## コマンド一覧（管理者のみ）
Botがサーバーに参加すると、以下のスラッシュコマンドが使用できるようになります。

- `/set_signal_channel`
  - コマンドを実行したチャンネルを、そのサーバーの時報送信先に設定します。
- `/stop_signal`
  - このサーバーでの時報を一時停止します。
- `/resume_signal`
  - 一時停止している時報を再開します。
- `/remove_signal_channel`
  - このサーバーでの時報設定を完全に解除（削除）します。

## 注意事項
- `.env` ファイルには重要なトークンが含まれるため、絶対に公開しないでください（Git等にプッシュしないよう注意）。
- 各サーバーの設定データは `channels.json` に保存されます。