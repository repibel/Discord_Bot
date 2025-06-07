
import discord
from discord import app_commands
from discord.ext import commands
import yt_dlp
import asyncio
import os

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

ALLOWED_CHANNEL_ID = 123456789012345678  # 여기에 허용된 텍스트 채널 ID 입력
music_queue = []
interaction_cache = {}

@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"✅ Logged in as {bot.user}")
    print("✅ Slash commands synced.")

def check_channel(interaction: discord.Interaction):
    return interaction.channel.id == ALLOWED_CHANNEL_ID

async def play_next(interaction: discord.Interaction):
    if not music_queue:
        await interaction.channel.send("✅ 대기열에 남은 곡이 없습니다.")
        return

    title, filename = music_queue.pop(0)
    vc = interaction.guild.voice_client
    source = discord.FFmpegPCMAudio(filename)

    def after_playing(err):
        coro = play_next(interaction)
        asyncio.run_coroutine_threadsafe(coro, bot.loop)
        if not music_queue:
            asyncio.run_coroutine_threadsafe(interaction.channel.send("✅ 대기열이 비었습니다."), bot.loop)
        else:
            next_title = music_queue[0][0]
            asyncio.run_coroutine_threadsafe(interaction.channel.send(f"▶️ 다음 곡: **{next_title}**"), bot.loop)

    vc.play(source, after=after_playing)
    await interaction.channel.send(f"🎶 재생 중: **{title}**")

@bot.tree.command(name="play", description="🎵 유튜브 링크로 음악을 재생합니다.")
@app_commands.describe(url="재생할 유튜브 URL")
async def play(interaction: discord.Interaction, url: str):
    if not check_channel(interaction):
        await interaction.response.send_message("❌ 이 채널에서는 명령어를 사용할 수 없습니다.", ephemeral=True)
        return

    await interaction.response.defer()

    if interaction.user.voice is None or interaction.user.voice.channel is None:
        await interaction.followup.send("⚠️ 먼저 음성 채널에 들어가 있어야 해요!")
        return

    voice_channel = interaction.user.voice.channel
    if interaction.guild.voice_client is None:
        await voice_channel.connect()
    else:
        await interaction.guild.voice_client.move_to(voice_channel)

    ydl_opts = {
        'format': 'bestaudio/best',
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
        await interaction.followup.send(f"🎶 **{title}** 이(가) 대기열에 추가되었어요!")

@bot.tree.command(name="search", description="🔍 유튜브에서 키워드로 음악을 검색합니다.")
@app_commands.describe(query="검색 키워드")
async def search(interaction: discord.Interaction, query: str):
    if not check_channel(interaction):
        await interaction.response.send_message("❌ 이 채널에서는 명령어를 사용할 수 없습니다.", ephemeral=True)
        return

    await interaction.response.defer()

    ydl_opts = {
        'format': 'bestaudio/best',
        'quiet': True,
        'default_search': 'ytsearch5',
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(query, download=False)
        entries = info['entries']

    view = discord.ui.View(timeout=30)
    for i, entry in enumerate(entries):
        title = entry['title']
        url = entry['webpage_url']

        async def callback(interaction_button, entry=entry):
            await interaction_button.response.defer()
            if interaction.user.voice is None or interaction.user.voice.channel is None:
                await interaction_button.followup.send("⚠️ 먼저 음성 채널에 들어가 있어야 해요!", ephemeral=True)
                return

            voice_channel = interaction.user.voice.channel
            if interaction.guild.voice_client is None:
                await voice_channel.connect()
            else:
                await interaction.guild.voice_client.move_to(voice_channel)

            download_opts = {
                'format': 'bestaudio/best',
                'noplaylist': True,
                'quiet': True,
                'outtmpl': 'song.%(ext)s',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
            }

            with yt_dlp.YoutubeDL(download_opts) as ydl_dl:
                data = ydl_dl.extract_info(entry['webpage_url'], download=True)
                filename = ydl_dl.prepare_filename(data).replace('.webm', '.mp3')
                title = data['title']
                music_queue.append((title, filename))

            if not interaction.guild.voice_client.is_playing():
                await play_next(interaction)
            else:
                await interaction_button.followup.send(f"🎶 **{title}** 이(가) 대기열에 추가되었어요!")

        button = discord.ui.Button(label=title[:80], style=discord.ButtonStyle.primary)
        button.callback = callback
        view.add_item(button)

    await interaction.followup.send("🔍 검색 결과 중 하나를 선택하세요:", view=view)

@bot.tree.command(name="pause", description="⏸️ 음악을 일시정지합니다.")
async def pause(interaction: discord.Interaction):
    if not check_channel(interaction):
        await interaction.response.send_message("❌ 이 채널에서는 명령어를 사용할 수 없습니다.", ephemeral=True)
        return

    vc = interaction.guild.voice_client
    if vc and vc.is_playing():
        vc.pause()
        await interaction.response.send_message("⏸️ 음악 일시정지!")
    else:
        await interaction.response.send_message("❌ 현재 재생 중인 음악이 없습니다.")

@bot.tree.command(name="resume", description="▶️ 음악을 다시 재생합니다.")
async def resume(interaction: discord.Interaction):
    if not check_channel(interaction):
        await interaction.response.send_message("❌ 이 채널에서는 명령어를 사용할 수 없습니다.", ephemeral=True)
        return

    vc = interaction.guild.voice_client
    if vc and vc.is_paused():
        vc.resume()
        await interaction.response.send_message("▶️ 음악 재생을 다시 시작합니다!")
    else:
        await interaction.response.send_message("❌ 일시정지된 음악이 없습니다.")

@bot.tree.command(name="stop", description="⏹️ 음악을 정지합니다.")
async def stop(interaction: discord.Interaction):
    if not check_channel(interaction):
        await interaction.response.send_message("❌ 이 채널에서는 명령어를 사용할 수 없습니다.", ephemeral=True)
        return

    if interaction.guild.voice_client is not None:
        interaction.guild.voice_client.stop()
        await interaction.response.send_message("⏹️ 음악 정지 완료!")
    else:
        await interaction.response.send_message("❌ 봇이 음성 채널에 있지 않아요.")

@bot.tree.command(name="leave", description="🚪 봇이 음성 채널에서 나갑니다.")
async def leave(interaction: discord.Interaction):
    if not check_channel(interaction):
        await interaction.response.send_message("❌ 이 채널에서는 명령어를 사용할 수 없습니다.", ephemeral=True)
        return

    if interaction.guild.voice_client is not None:
        await interaction.guild.voice_client.disconnect()
        await interaction.response.send_message("👋 음성 채널에서 나갔어요!")
    else:
        await interaction.response.send_message("❌ 봇이 음성 채널에 없어요.")

@bot.tree.command(name="queue", description="📃 현재 대기 중인 음악 목록을 확인합니다.")
async def queue(interaction: discord.Interaction):
    if not check_channel(interaction):
        await interaction.response.send_message("❌ 이 채널에서는 명령어를 사용할 수 없습니다.", ephemeral=True)
        return

    if music_queue:
        msg = "\n".join([f"{idx+1}. {title}" for idx, (title, _) in enumerate(music_queue)])
        await interaction.response.send_message(f"📃 대기열:\n{msg}")
    else:
        await interaction.response.send_message("📭 대기열이 비어 있어요.")

# 여기에 디스코드 봇 토큰 입력
bot.run("MTM4MDg4MjQwNjU4MzcwMTYzNQ.GO-XFl.UWTapQQC5b5gS99TZc29c-lerWlReiAv-vVCwM")
