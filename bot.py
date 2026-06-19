import discord
from discord.ext import commands, tasks
from discord import app_commands
import json
import os
import datetime
import socket
import struct
import time
import asyncio
from dotenv import load_dotenv

# .env ファイルの読み込み
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
TEST_MODE = os.getenv('TEST_MODE', 'False').lower() == 'true'

DATA_FILE = 'channels.json'

def get_ntp_offset():
    """外部NTPサーバーから正確な時刻を取得し、システム時刻との差分（秒）を計算します。
    戻り値: ntp_time - local_time
    """
    servers = ["ntp.nict.jp", "time.google.com", "pool.ntp.org"]
    port = 123
    data = b'\x1b' + 47 * b'\0'
    for server in servers:
        try:
            client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            client.settimeout(1.5)
            t_send = time.time()
            client.sendto(data, (server, port))
            response, _ = client.recvfrom(1024)
            t_recv = time.time()
            if response:
                unpacked = struct.unpack("!12I", response)
                ntp_seconds = unpacked[10] - 2208988800
                local_average = (t_recv + t_send) / 2
                offset = ntp_seconds - local_average
                return offset
        except Exception as e:
            print(f"NTP query to {server} failed: {e}")
    print("All NTP queries failed. Using local time (offset = 0.0)")
    return 0.0

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

    @tasks.loop()
    async def time_signal_task(self):
        # 毎回NTPから正確なオフセットを取得して補正
        offset = get_ntp_offset()
        
        jst_timezone = datetime.timezone(datetime.timedelta(hours=9))
        now_local = datetime.datetime.now(jst_timezone)
        # 現在の正確な時刻 (NTP補正値込み)
        now_actual = now_local + datetime.timedelta(seconds=offset)
        
        # 次のアナウンス対象時刻を計算
        if TEST_MODE:
            # テストモード: 次の「分」の00秒をターゲットにする（最大60秒待機）
            next_target_actual = (now_actual.replace(second=0, microsecond=0) + datetime.timedelta(minutes=1))
        else:
            # 通常モード: 次の「時間」の00分00秒をターゲットにする（最大1時間待機）
            next_target_actual = (now_actual.replace(minute=0, second=0, microsecond=0) + datetime.timedelta(hours=1))
        
        # 待機秒数を計算
        sleep_seconds = (next_target_actual - now_actual).total_seconds()
        
        # マイナス秒数（既に過ぎている極小の誤差など）の場合は最小の待機を設定
        if sleep_seconds <= 0:
            sleep_seconds = 60 if TEST_MODE else 3600
            
        print(f"[TimeSignal] {'[TEST MODE] ' if TEST_MODE else ''}Sleeping for {sleep_seconds:.3f} seconds until {next_target_actual.strftime('%Y-%m-%d %H:%M:%S')} JST")
        await asyncio.sleep(sleep_seconds)
        
        # 待機明け（時報送信時間）
        # 送信時の実際の時間を取得して、アナウンスする時間を決定
        now_send = datetime.datetime.now(jst_timezone) + datetime.timedelta(seconds=offset)
        
        if TEST_MODE:
            # テストモード時は分や秒誤差まで詳細に表示
            announce_text = f"【テスト時報】{now_send.hour}時{now_send.minute}分をお知らせします（NTP誤差補正: {offset:.3f}秒）"
        else:
            # 0.5秒足してから時間を取得することで、直前の極小の遅延によるズレを吸収して丸める
            hour = (now_send + datetime.timedelta(seconds=0.5)).hour
            announce_text = f"{hour}時をお知らせします"
        
        for guild_id_str, settings in self.guild_settings.items():
            if settings.get("is_paused", False):
                continue
            channel_id = settings.get("channel_id")
            if channel_id:
                channel = self.get_channel(channel_id)
                if channel:
                    try:
                        await channel.send(announce_text)
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

@bot.tree.command(name="test_signal", description="【テスト】現在の時間で時報を即座に送信テストします")
@app_commands.checks.has_permissions(administrator=True)
async def test_signal(interaction: discord.Interaction):
    jst_timezone = datetime.timezone(datetime.timedelta(hours=9))
    now = datetime.datetime.now(jst_timezone)
    hour = now.hour
    await interaction.response.send_message(f"【テスト時報】{hour}時をお知らせします（即時送信テスト）", ephemeral=False)

@set_signal_channel.error
@remove_signal_channel.error
@stop_signal.error
@resume_signal.error
@test_signal.error
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
