import os
import sys
import asyncio
import time
from datetime import timedelta

import discord
from discord.ext import commands
from aiohttp import web

from keep_alive import keep_alive

# --- 외부 서비스 시작 ---
keep_alive()

intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True
intents.members = True

bot = commands.Bot(command_prefix='!', intents=intents)

# 유저 ID와 채널 ID 매핑
user_channel_map = {
    447077829130321921: 1373128857481252954,  # 서하
    285716819577143296: 1373128925361868811,  # 차보롬
    1338669217339408416: 1373166441200619570,  # 윤서하
    529695644760276992: 1373166919439355984,  # 김창윤
    949706769473601616: 1373167015925121164,  # 소윤
    1038379785346351164: 1373167043746201661,  # 영범이형
    352810254574026753: 1373167063874535525,  # 오동욱
    1338668174840954933: 1373167084527423498,  # 이원희
    941189989474119720: 1373167106656567327,  # 졸려pt
    562877071794110464: 1373167130656243722,  # 충교
    920744940445777960: 1373167181726089297,  # 큐띠뽀짝현재쨩
}

# 사용할 이모지
target_emoji = "📌"

# 최근 반응 저장용 (중복 필터링)
recent_reactions = {}

# --- aiohttp 웹서버 핸들러 ---
async def handle(request):
    return web.Response(text="OK")

async def start_webserver():
    app = web.Application()
    app.add_routes([web.get('/', handle)])
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 8000)
    await site.start()

print(f"[DEBUG] Bot starting: PID={os.getpid()}, BOT_USER={bot.user} if ready")

@bot.event
async def on_ready():
    print(f"[DEBUG] on_ready called: PID={os.getpid()}, BOT_USER={bot.user}")
    print(f'Logged in as {bot.user} (ID: {bot.user.id})')
    print('------')
    bot.loop.create_task(start_webserver())

@bot.event
async def on_raw_reaction_add(payload):
    print(f"[DEBUG] Reaction event received: user_id={payload.user_id}, message_id={payload.message_id}, emoji={payload.emoji}, PID={os.getpid()}")
    print(f"[DEBUG] Reaction event received: user_id={payload.user_id}, message_id={payload.message_id}, emoji={payload.emoji}, channel_id={payload.channel_id}")

    if str(payload.emoji) != target_emoji:
        print(f"[DEBUG] Ignored emoji: {payload.emoji}")
        return

    key = (payload.user_id, payload.message_id, str(payload.emoji))
    now = time.time()

    # 3초 이내에 같은 이벤트가 들어오면 무시
    if key in recent_reactions and now - recent_reactions[key] < 3:
        print(f"[DEBUG] Duplicate reaction ignored: {key}")
        return
    recent_reactions[key] = now
    print(f"[DEBUG] Processing reaction: {key}")

    user_id = payload.user_id
    channel_id = user_channel_map.get(user_id)

    if not channel_id:
        print(f"⚠️ 유저 {user_id}에 대한 채널 매핑이 없음.")
        return

    message_channel = bot.get_channel(payload.channel_id)
    if not message_channel:
        print("❌ 메시지 채널을 찾을 수 없음.")
        return

    try:
        message = await message_channel.fetch_message(payload.message_id)
    except Exception as e:
        print(f"❌ 메시지를 불러오지 못함: {e}")
        return

    guild_id = payload.guild_id
    message_url = f"https://discord.com/channels/{guild_id}/{payload.channel_id}/{payload.message_id}"
    target_channel = bot.get_channel(channel_id)

    if not target_channel:
        print(f"❌ 채널 {channel_id}을 찾을 수 없음.")
        return

    created_at_kst = message.created_at + timedelta(hours=9)
    formatted_date = created_at_kst.strftime("%Y-%m-%d %H:%M:%S")

    if message.content:
        description_text = message.content
    elif message.attachments:
        description_text = ""
    elif message.stickers:
        sticker = message.stickers[0]
        description_text = f"[스티커: {sticker.name}]"
    else:
        description_text = "[내용이 없는 메시지입니다]"

    embed = discord.Embed(
        title="📌 북마크된 메시지",
        url=message_url,
        description=description_text,
        color=0x1abc9c
    )
    embed.set_author(
        name=message.author.display_name,
        icon_url=message.author.avatar.url if message.author.avatar else None
    )
    embed.set_footer(text=f"작성일시: {formatted_date}")

    for attachment in message.attachments:
        if attachment.content_type and attachment.content_type.startswith("image"):
            embed.set_image(url=attachment.url)
            break

    try:
        await target_channel.send(embed=embed)
        print("[DEBUG] 북마크 임베드 메시지 전송 완료")
    except Exception as e:
        print(f"[ERROR] 임베드 메시지 전송 실패: {e}")

    if message.content and "http" in message.content and "```" not in message.content:
        try:
            await target_channel.send(message.content)
            print("[DEBUG] http 링크 메시지 전송 완료")
        except Exception as e:
            print(f"[ERROR] http 링크 메시지 전송 실패: {e}")

    for attachment in message.attachments:
        if attachment.content_type and attachment.content_type.startswith("video"):
            try:
                await target_channel.send(
                    content=f"🎬 동영상 첨부파일: {attachment.filename}",
                    file=await attachment.to_file()
                )
                print(f"[DEBUG] 동영상 첨부파일 전송 완료: {attachment.filename}")
            except Exception as e:
                print(f"[ERROR] 동영상 첨부파일 전송 실패: {e}")

    non_image_non_video_attachments = [
        attachment for attachment in message.attachments
        if not (attachment.content_type and (attachment.content_type.startswith("image") or attachment.content_type.startswith("video")))
    ]
    for attachment in non_image_non_video_attachments:
        try:
            await target_channel.send(
                content=f"📎 첨부파일: {attachment.filename}",
                file=await attachment.to_file()
            )
            print(f"[DEBUG] 일반 첨부파일 전송 완료: {attachment.filename}")
        except Exception as e:
            print(f"[ERROR] 일반 첨부파일 전송 실패: {e}")

bot.run(os.getenv("DISCORD_TOKEN"))
