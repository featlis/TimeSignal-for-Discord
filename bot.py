import discord
from discord.ext import commands, tasks
from discord import app_commands
import json
import os
import datetime
from dotenv import load_dotenv

# .env ファイルの読み込み
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')

DATA_FILE = 'channels.json'

# 毎時00分00秒（UTC）のリストを作成
HOURLY_TIMES = [
    datetime.time(hour=h, minute=0, second=0, tzinfo=datetime.timezone.utc)
    for h in range(24)
]

class TimeSignalBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix='!', intents=discord.Intents.default())
        # データ構造: { "guild_id": {"channel_id": channel_id, "is_paused": bool} }
        self.guild_settings = self.load_data()

    def load_data(self):
        if not os.path.exists(DATA_FILE):
            return {}
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # キーは文字列として保存されるため、復元時に整数化しつつ形式を統一
                formatted_data = {}
                for k, v in data.items():
                    if isinstance(v, int):
                        # 古いフォーマット(channel_idだけの場合)の移行用
                        formatted_data[k] = {"channel_id": v, "is_paused": False}
                    else:
                        formatted_data[k] = v
                return formatted_data
        except Exception as e:
            print(f"Failed to load data: {e}")
            return {}

    def save_data(self):
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.guild_settings, f, ensure_ascii=False, indent=4)

    async def setup_hook(self):
        # スラッシュコマンドを同期
        await self.tree.sync()
        # 時報タスクの開始
        self.time_signal_task.start()

    async def on_ready(self):
        print(f'Logged in as {self.user} (ID: {self.user.id})')
        print('------')

    @tasks.loop(time=HOURLY_TIMES)
    async def time_signal_task(self):
        # 設定された時間（毎時00分00秒）に自動的に呼び出される
        # 日本標準時 (JST: UTC+9) のタイムゾーンを指定して時刻を取得
        jst_timezone = datetime.timezone(datetime.timedelta(hours=9))
        now = datetime.datetime.now(jst_timezone)
        hour = now.hour
        
        for guild_id_str, settings in self.guild_settings.items():
            if settings.get("is_paused", False):
                continue
            channel_id = settings.get("channel_id")
            if channel_id:
                channel = self.get_channel(channel_id)
                if channel:
                    try:
                        await channel.send(f'{hour}時をお知らせします')
                    except discord.Forbidden:
                        print(f"Missing permissions to send message in {channel.name} ({guild_id_str})")
                    except Exception as e:
                        print(f"Error sending message in {guild_id_str}: {e}")

    @time_signal_task.before_loop
    async def before_time_signal_task(self):
        await self.wait_until_ready()

bot = TimeSignalBot()

@bot.tree.command(name="set_signal_channel", description="このチャンネルを時報の送信先に設定します")
@app_commands.checks.has_permissions(administrator=True)
async def set_signal_channel(interaction: discord.Interaction):
    guild_id = str(interaction.guild.id)
    channel_id = interaction.channel.id
    
    # 既存の設定があればis_pausedを引き継ぎ、なければFalse
    is_paused = bot.guild_settings.get(guild_id, {}).get("is_paused", False)
    
    bot.guild_settings[guild_id] = {
        "channel_id": channel_id,
        "is_paused": is_paused
    }
    bot.save_data()
    await interaction.response.send_message(f"このチャンネル({interaction.channel.mention})を時報の送信先に設定しました。", ephemeral=False)

@bot.tree.command(name="remove_signal_channel", description="このサーバーでの時報設定を解除します")
@app_commands.checks.has_permissions(administrator=True)
async def remove_signal_channel(interaction: discord.Interaction):
    guild_id = str(interaction.guild.id)
    if guild_id in bot.guild_settings:
        del bot.guild_settings[guild_id]
        bot.save_data()
        await interaction.response.send_message("時報の送信先設定を解除しました。", ephemeral=False)
    else:
        await interaction.response.send_message("時報の送信先は設定されていません。", ephemeral=True)

@bot.tree.command(name="stop_signal", description="このサーバーでの時報を一時停止します")
@app_commands.checks.has_permissions(administrator=True)
async def stop_signal(interaction: discord.Interaction):
    guild_id = str(interaction.guild.id)
    if guild_id in bot.guild_settings:
        bot.guild_settings[guild_id]["is_paused"] = True
        bot.save_data()
        await interaction.response.send_message("時報を一時停止しました。`/resume_signal`で再開できます。", ephemeral=False)
    else:
        await interaction.response.send_message("時報の送信先が設定されていないため、一時停止できません。", ephemeral=True)

@bot.tree.command(name="resume_signal", description="一時停止している時報を再開します")
@app_commands.checks.has_permissions(administrator=True)
async def resume_signal(interaction: discord.Interaction):
    guild_id = str(interaction.guild.id)
    if guild_id in bot.guild_settings:
        if bot.guild_settings[guild_id]["is_paused"]:
            bot.guild_settings[guild_id]["is_paused"] = False
            bot.save_data()
            await interaction.response.send_message("時報を再開しました。", ephemeral=False)
        else:
            await interaction.response.send_message("時報は現在一時停止されていません。", ephemeral=True)
    else:
        await interaction.response.send_message("時報の送信先が設定されていません。先に`/set_signal_channel`を実行してください。", ephemeral=True)

@set_signal_channel.error
@remove_signal_channel.error
@stop_signal.error
@resume_signal.error
async def command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message("このコマンドを実行するには管理者権限が必要です。", ephemeral=True)
    else:
        await interaction.response.send_message(f"エラーが発生しました: {error}", ephemeral=True)

if __name__ == "__main__":
    if TOKEN is None or TOKEN == 'your_token_here':
        print("エラー: .envファイルに正しいDISCORD_TOKENを設定してください。")
    else:
        bot.run(TOKEN)
