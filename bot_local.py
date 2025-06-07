# bot_local.py
# 로컬 및 Render 배포용 Discord 뮤직 봇 (discord.py 및 yt-dlp 사용)
# 최적화: 스트리밍으로 재생 속도 개선 + 헬스체크 HTTP 서버 추가

import os
import platform
import discord
from discord.ext import commands
from discord import app_commands
import asyncio
from threading import Thread
from http.server import HTTPServer, BaseHTTPRequestHandler

# ----------------------------
# opus 라이브러리 로드
# ----------------------------
if platform.system() == "Windows":
    dll_path = os.path.join(os.path.dirname(__file__), "libopus-0.dll")
    discord.opus.load_opus(dll_path)
else:
    # Linux/Mac 에서는 시스템에 설치된 libopus 사용
    discord.opus.load_opus(discord.opus._default_opus_name())

# ----------------------------
# Discord 봇 설정
# ----------------------------
intents = discord.Intents.default()
intents.voice_states = True
bot = commands.Bot(command_prefix="/", intents=intents)
tree = bot.tree

enabled_channel_id = None
queue = []

# 채널 사용 여부 체크
def check_channel(interaction: discord.Interaction) -> bool:
    return interaction.channel.id == enabled_channel_id

@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"✅ {bot.user} 로 로그인했습니다.")

@bot.event
async def on_voice_state_update(member, before, after):
    global enabled_channel_id
    vc = discord.utils.get(bot.voice_clients, guild=member.guild)
    if vc and before.channel == vc.channel and member != bot.user:
        non_bots = [m for m in before.channel.members if not m.bot]
        if not non_bots:
            await vc.disconnect()
            enabled_channel_id = None
            print("👋 음성 채널이 비어 있어 봇이 나갔습니다.")

# 스트림 재생
async def _play_next(interaction: discord.Interaction):
    if not queue:
        await interaction.channel.send("✅ 대기열이 비어 있습니다.")
        return

    title, stream_url = queue.pop(0)
    vc = interaction.guild.voice_client
    source = discord.FFmpegPCMAudio(
        stream_url,
        options='-vn -reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5'
    )

    def after_playing(err):
        coro = _play_next(interaction)
        asyncio.run_coroutine_threadsafe(coro, bot.loop)
        if not queue:
            asyncio.run_coroutine_threadsafe(
                interaction.channel.send("✅ 대기열이 끝났습니다."), bot.loop
            )
        else:
            next_title = queue[0][0]
            asyncio.run_coroutine_threadsafe(
                interaction.channel.send(f"▶️ 다음 곡: **{next_title}**"), bot.loop
            )

    vc.play(source, after=after_playing)
    await interaction.channel.send(f"🎶 재생 중: **{title}**")

# /play 명령: 스트리밍 재생
@tree.command(name="play", description="🎵 스트리밍으로 YouTube 음악 재생")
@app_commands.describe(url="YouTube URL")
async def play(
    interaction: discord.Interaction,
    url: str
):
    global enabled_channel_id
    enabled_channel_id = interaction.channel.id

    if not check_channel(interaction):
        await interaction.response.send_message("❌ 이 채널에서 사용할 수 없습니다.", ephemeral=True)
        return

    await interaction.response.defer()
    if not interaction.user.voice or not interaction.user.voice.channel:
        await interaction.followup.send("⚠️ 먼저 음성 채널에 들어가주세요!")
        return

    channel = interaction.user.voice.channel
    if not interaction.guild.voice_client:
        await channel.connect()
    else:
        await interaction.guild.voice_client.move_to(channel)

    ydl_opts = {
        'format': 'bestaudio/best',
        'quiet': True,
        'noplaylist': True,
        'default_search': 'auto'
    }
    import yt_dlp
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        if 'entries' in info:
            info = info['entries'][0]
        stream_url = info['url']
        title = info.get('title', 'Unknown')
        queue.append((title, stream_url))

    vc = interaction.guild.voice_client
    if not vc.is_playing():
        await _play_next(interaction)
    else:
        await interaction.followup.send(f"➕ 대기열 추가: **{title}**")

# 기타 명령어 (stop, pause, resume, leave, queue)… 동일 패턴으로 정의

@tree.command(name="stop", description="⏹️ 재생 중지 및 대기열 초기화")
async def stop(interaction: discord.Interaction):
    if not check_channel(interaction):
        await interaction.response.send_message("❌ 이 채널에서 사용할 수 없습니다.", ephemeral=True)
        return
    vc = interaction.guild.voice_client
    if vc:
        vc.stop()
        queue.clear()
        await interaction.response.send_message("⏹️ 재생을 중지하고 대기열을 초기화했습니다.")
    else:
        await interaction.response.send_message("❌ 음성 채널에 연결되어 있지 않습니다.")

@tree.command(name="pause", description="⏸️ 일시정지")
async def pause(interaction: discord.Interaction):
    if not check_channel(interaction):
        await interaction.response.send_message("❌ 이 채널에서 사용할 수 없습니다.", ephemeral=True)
        return
    vc = interaction.guild.voice_client
    if vc and vc.is_playing():
        vc.pause()
        await interaction.response.send_message("⏸️ 일시정지되었습니다.")
    else:
        await interaction.response.send_message("❌ 재생 중인 음악이 없습니다.")

@tree.command(name="resume", description="▶️ 일시정지된 음악 재생")
async def resume(interaction: discord.Interaction):
    if not check_channel(interaction):
        await interaction.response.send_message("❌ 이 채널에서 사용할 수 없습니다.", ephemeral=True)
        return
    vc = interaction.guild.voice_client
    if vc and vc.is_paused():
        vc.resume()
        await interaction.response.send_message("▶️ 재생을 다시 시작했습니다.")
    else:
        await interaction.response.send_message("❌ 일시정지된 음악이 없습니다.")

@tree.command(name="leave", description="🚪 음성 채널에서 나가기")
async def leave(interaction: discord.Interaction):
    global enabled_channel_id
    if not check_channel(interaction):
        await interaction.response.send_message("❌ 이 채널에서 사용할 수 없습니다.", ephemeral=True)
        return
    vc = interaction.guild.voice_client
    if vc:
        await vc.disconnect()
        enabled_channel_id = None
        await interaction.response.send_message("👋 음성 채널에서 나갔습니다.")
    else:
        await interaction.response.send_message("❌ 음성 채널에 연결되어 있지 않습니다.")

@tree.command(name="queue", description="📃 대기열 표시")
async def show_queue(interaction: discord.Interaction):
    if not check_channel(interaction):
        await interaction.response.send_message("❌ 이 채널에서 사용할 수 없습니다.", ephemeral=True)
        return
    if queue:
        msg = "\n".join(f"{i+1}. {t}" for i, (t, _) in enumerate(queue))
        await interaction.response.send_message(f"📃 대기열:\n{msg}")
    else:
        await interaction.response.send_message("📭 대기열이 비어 있습니다.")

# ----------------------------
# 헬스체크 HTTP 서버 (Render 웹 서비스용)
# ----------------------------
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")


def start_health_server():
    port = int(os.environ.get("PORT", 8080))
    HTTPServer(("0.0.0.0", port), HealthHandler).serve_forever()

# ----------------------------
# 실행
# ----------------------------
if __name__ == "__main__":
    token = os.getenv("BOT_TOKEN")
    if not token:
        print("오류: BOT_TOKEN 환경 변수가 설정되지 않았습니다.")
    else:
        # 헬스체크 서버 시작 (웹 서비스일 때만 필요)
        Thread(target=start_health_server, daemon=True).start()
        bot.run(token)


