import discord
from discord.ext import commands
from discord import app_commands
import yt_dlp
import asyncio
import os

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="/", intents=intents)
tree = bot.tree

ALLOWED_CHANNEL_ID = None
music_queue = []

def check_channel(interaction: discord.Interaction):
    return ALLOWED_CHANNEL_ID == interaction.channel.id

@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"✅ Logged in as {bot.user}")

@bot.event
async def on_voice_state_update(member, before, after):
    global ALLOWED_CHANNEL_ID

    # 사람이 모두 나가면 봇도 나감
    if before.channel and member != bot.user:
        voice_client = discord.utils.get(bot.voice_clients, guild=member.guild)
        if voice_client and voice_client.channel == before.channel:
            non_bot_members = [m for m in before.channel.members if not m.bot]
            if len(non_bot_members) == 0:
                await voice_client.disconnect()
                print("👋 모두 나가서 봇이 음성 채널을 나감")
                ALLOWED_CHANNEL_ID = None

async def play_next(interaction: discord.Interaction):
    if not music_queue:
        await interaction.channel.send("✅ 대기열이 비어있어요.")
        return

    title, filename = music_queue.pop(0)
    vc = interaction.guild.voice_client
    source = discord.FFmpegPCMAudio(filename)

    def after_playing(err):
        coro = play_next(interaction)
        asyncio.run_coroutine_threadsafe(coro, bot.loop)
        if not music_queue:
            asyncio.run_coroutine_threadsafe(interaction.channel.send("✅ 대기열이 끝났어요."), bot.loop)

    vc.play(source, after=after_playing)
    await interaction.channel.send(f"🎶 재생 중: **{title}**")

@tree.command(name="play", description="🎵 유튜브 링크로 음악 재생")
@app_commands.describe(url="유튜브 URL")
async def play(interaction: discord.Interaction, url: str):
    global ALLOWED_CHANNEL_ID
    ALLOWED_CHANNEL_ID = interaction.channel.id

    if not check_channel(interaction):
        await interaction.response.send_message("❌ 이 채널에서는 명령어를 사용할 수 없어요.", ephemeral=True)
        return

    await interaction.response.defer()

    if interaction.user.voice is None:
        await interaction.followup.send("⚠️ 먼저 음성 채널에 들어가 주세요!")
        return

    voice_channel = interaction.user.voice.channel
    if interaction.guild.voice_client is None:
        await voice_channel.connect()
    else:
        await interaction.guild.voice_client.move_to(voice_channel)

    ydl_opts = {
        'format': 'bestaudio',
        'noplaylist': True,
        'quiet': True,
        'outtmpl': 'song.%(ext)s',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info).replace('.webm', '.mp3')
        title = info['title']
        music_queue.append((title, filename))

    if not interaction.guild.voice_client.is_playing():
        await play_next(interaction)
    else:
        await interaction.followup.send(f"🎶 **{title}** 대기열에 추가!")

@tree.command(name="stop", description="⏹️ 음악 정지")
async def stop(interaction: discord.Interaction):
    if not check_channel(interaction):
        await interaction.response.send_message("❌ 이 채널에서는 사용할 수 없어요.", ephemeral=True)
        return
    if interaction.guild.voice_client:
        interaction.guild.voice_client.stop()
        await interaction.response.send_message("⏹️ 음악 정지!")

@tree.command(name="pause", description="⏸️ 음악 일시정지")
async def pause(interaction: discord.Interaction):
    if not check_channel(interaction):
        await interaction.response.send_message("❌ 이 채널에서는 사용할 수 없어요.", ephemeral=True)
        return
    vc = interaction.guild.voice_client
    if vc and vc.is_playing():
        vc.pause()
        await interaction.response.send_message("⏸️ 일시정지 완료!")

@tree.command(name="resume", description="▶️ 음악 재개")
async def resume(interaction: discord.Interaction):
    if not check_channel(interaction):
        await interaction.response.send_message("❌ 이 채널에서는 사용할 수 없어요.", ephemeral=True)
        return
    vc = interaction.guild.voice_client
    if vc and vc.is_paused():
        vc.resume()
        await interaction.response.send_message("▶️ 재생 재개!")

@tree.command(name="leave", description="🚪 봇 음성 채널 퇴장")
async def leave(interaction: discord.Interaction):
    global ALLOWED_CHANNEL_ID
    if not check_channel(interaction):
        await interaction.response.send_message("❌ 이 채널에서는 사용할 수 없어요.", ephemeral=True)
        return
    if interaction.guild.voice_client:
        await interaction.guild.voice_client.disconnect()
        await interaction.response.send_message("👋 나갔어요!")
        ALLOWED_CHANNEL_ID = None
    else:
        await interaction.response.send_message("❌ 음성 채널에 있지 않아요.")

@tree.command(name="queue", description="📃 현재 대기열 보기")
async def queue(interaction: discord.Interaction):
    if not check_channel(interaction):
        await interaction.response.send_message("❌ 이 채널에서는 사용할 수 없어요.", ephemeral=True)
        return
    if music_queue:
        msg = "\n".join([f"{idx+1}. {title}" for idx, (title, _) in enumerate(music_queue)])
        await interaction.response.send_message(f"📃 대기열:\n{msg}")
    else:
        await interaction.response.send_message("📭 대기열이 비어 있어요.")

# Render에서 BOT_TOKEN 환경변수 설정 필요
bot.run(os.getenv("BOT_TOKEN"))
