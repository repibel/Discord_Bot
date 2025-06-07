# bot_local.py
# 로컬 실행용 Discord 뮤직 봇 (discord.py 및 yt-dlp 사용)
# 최적화: 다운로드 대신 스트리밍으로 재생 속도 개선

import os
import platform
import discord
from discord.ext import commands
from discord import app_commands
import asyncio

# ----------------------------
# opus 라이브러리 로드
# ----------------------------
if platform.system() == "Windows":
    # 프로젝트 루트에 libopus-0.dll 파일을 두세요
    dll_path = os.path.join(os.path.dirname(__file__), "libopus-0.dll")
    discord.opus.load_opus(dll_path)
# Linux/Mac 등의 시스템에서는 이미 설치된 libopus를 자동으로 사용하므로 별도 호출 불필요

# ----------------------------
# 봇 설정
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

# 봇 준비 완료 시
@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"✅ {bot.user} 로 로그인했습니다.")

# 음성 채널 사용자가 모두 나가면 봇도 나감
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
    # 다운로드 없이 스트림 URL 추출
    import yt_dlp as _yt_dlp
    with _yt_dlp.YoutubeDL(ydl_opts) as ydl:
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

# /stop 명령
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

# /pause 명령
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

# /resume 명령
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

# /leave 명령
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

# /queue 명령
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
# 실행
# ----------------------------
if __name__ == "__main__":
    token = os.getenv("BOT_TOKEN")
    if not token:
        print("오류: BOT_TOKEN 환경 변수가 설정되지 않았습니다.")
    else:
        bot.run(token)

