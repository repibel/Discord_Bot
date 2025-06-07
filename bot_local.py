# bot_local.py
# 로컬 실행용 Discord 뮤직 봇 (discord.py 및 yt-dlp 사용)
# 최적화: 다운로드 대신 스트리밍으로 재생 속도 개선

import os
import discord
from discord.ext import commands
from discord import app_commands
import yt_dlp
import asyncio

# 인텐트 설정: 슬래시 커맨드와 음성 상태 변화를 위해 guilds, voice_states 활성화
intents = discord.Intents.default()
intents.guilds = True
intents.voice_states = True

bot = commands.Bot(command_prefix="/", intents=intents)
tree = bot.tree

enabled_channel_id = None
queue = []

# ──────────────────────────────────────
# 채널 체크 유틸
def check_channel(interaction: discord.Interaction) -> bool:
    return interaction.channel.id == enabled_channel_id

# 봇 준비 완료 이벤트
@bot.event
async def on_ready():
    await tree.sync()
    print(f"✅ {bot.user} 로 로그인했습니다.")

# 사람이 모두 나가면 봇도 음성 채널에서 나가고, 채널 ID 리셋
@bot.event
async def on_voice_state_update(member, before, after):
    global enabled_channel_id
    vc = discord.utils.get(bot.voice_clients, guild=member.guild)
    if vc and before.channel == vc.channel and member != bot.user:
        non_bots = [m for m in before.channel.members if not m.bot]
        if not non_bots:
            await vc.disconnect()
            enabled_channel_id = None
            print("👋 음성 채널이 비어 봇이 나갔습니다.")

# ──────────────────────────────────────
# 다음 곡 재생 함수 (스트리밍)
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

# ──────────────────────────────────────
# /play 슬래시 커맨드: YouTube 스트리밍 재생
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
        'noplaylist': True
    }

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

# ──────────────────────────────────────
# /stop: 재생 중지 및 대기열 초기화
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

# /pause: 일시정지
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

# /resume: 일시정지된 음악 재생
@tree.command(name="resume", description="▶️ 일시정지된 음악을 재생")
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

# /leave: 음성 채널에서 나가기
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

# /queue: 대기열 표시
@tree.command(name="queue", description="📃 대기열 표시")
async def show_queue(interaction: discord.Interaction):
    if not check_channel(interaction):
        await interaction.response.send_message("❌ 이 채널에서 사용할 수 없습니다.", ephemeral=True)
        return
    if queue:
        msg = '\n'.join(f"{i+1}. {t}" for i, (t, _) in enumerate(queue))
        await interaction.response.send_message(f"📃 대기열:\n{msg}")
    else:
        await interaction.response.send_message("📭 대기열이 비어 있습니다.")

# ──────────────────────────────────────
if __name__ == "__main__":
    token = os.getenv("BOT_TOKEN")
    if not token:
        print("오류: BOT_TOKEN 환경 변수가 설정되지 않았습니다.")
    else:
        bot.run(token)
