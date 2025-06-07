import discord
from discord.ext import commands
from discord import Option
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
    # 사람이 모두 나가면 봇도 나가고 채널 리셋
    if before.channel and member != bot.user:
        vc = discord.utils.get(bot.voice_clients, guild=member.guild)
        if vc and vc.channel == before.channel:
            non_bots = [m for m in before.channel.members if not m.bot]
            if not non_bots:
                await vc.disconnect()
                ALLOWED_CHANNEL_ID = None
                print("👋 모두 나가서 봇이 음성 채널을 나감")

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
            asyncio.run_coroutine_threadsafe(
                interaction.channel.send("✅ 대기열이 끝났어요."), bot.loop
            )

    vc.play(source, after=after_playing)
    await interaction.channel.send(f"🎶 재생 중: **{title}**")

@tree.command(name="play", description="🎵 유튜브 링크로 음악 재생")
async def play(
    interaction: discord.Interaction,
    url: Option(str, "유튜브 URL")
):
    global ALLOWED_CHANNEL_ID
    ALLOWED_CHANNEL_ID = interaction.channel.id

    if not check_channel(interaction):
        await interaction.response.send_message(
            "❌ 이 채널에서는 사용할 수 없어요.", ephemeral=True
        )
        return

    await interaction.response.defer()
    if not getattr(interaction.user.voice, "channel", None):
        await interaction.followup.send("⚠️ 먼저 음성 채널에 들어가 주세요!")
        return

    channel = interaction.user.voice.channel
    if not interaction.guild.voice_client:
        await channel.connect()
    else:
        await interaction.guild.voice_client.move_to(channel)

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

# (이하 /pause, /resume, /stop, /leave, /queue 도 모두 동일하게 @tree.command 데커레이터 사용)

bot.run(os.getenv("BOT_TOKEN"))
