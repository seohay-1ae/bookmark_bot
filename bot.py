import os
import asyncio
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
    447077829130321921: 1373128857481252954, #서하
    285716819577143296: 1373128925361868811, #차보롬
    1338669217339408416: 1373166441200619570, #윤서하
    529695644760276992: 1373166919439355984, #김창윤
    949706769473601616: 1373167015925121164, #소윤
    1038379785346351164: 1373167043746201661, #영범이형
    352810254574026753: 1373167063874535525, #오동욱
    1338668174840954933: 1373167084527423498, #이원희
    941189989474119720: 1373167106656567327, #졸려pt
    562877071794110464: 1373167130656243722, #충교
    920744940445777960: 1373167181726089297, #큐띠뽀짝현재쨩
}

# 사용할 이모지
target_emoji = "📌"

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

# 봇 시작 시 웹서버도 함께 실행하도록 설정
@bot.event
async def on_ready():
    print(f'Logged in as {bot.user} (ID: {bot.user.id})')
    print('------')
    # 웹서버 시작 (백그라운드에서 실행)
    bot.loop.create_task(start_webserver())

@bot.event
async def on_raw_reaction_add(payload):
    if str(payload.emoji) != target_emoji:
        return

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
    except:
        print("❌ 메시지를 불러오지 못함.")
        return

    guild_id = payload.guild_id
    message_url = f"https://discord.com/channels/{guild_id}/{payload.channel_id}/{payload.message_id}"
    target_channel = bot.get_channel(channel_id)

    if not target_channel:
        print(f"❌ 채널 {channel_id}을 찾을 수 없음.")
        return

    created_at_kst = message.created_at + timedelta(hours=9)
    formatted_date = created_at_kst.strftime("%Y-%m-%d %H:%M:%S")

    # 메시지 설명 텍스트 결정
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

    # 이미지 첨부 있으면 embed 이미지로 설정
    for attachment in message.attachments:
        if attachment.content_type and attachment.content_type.startswith("image"):
            embed.set_image(url=attachment.url)
            break

    # 1. 북마크 임베드 메시지 전송
    await target_channel.send(embed=embed)

    # 2. 코드 블록이 없고 http 링크가 있을 경우 링크 따로 전송 → Discord 미리보기 유도
    if message.content and "http" in message.content and "```" not in message.content:
        await target_channel.send(message.content)

    # 3. 이미지 외 첨부파일 중 동영상, 파일 따로 전송
    # 동영상 먼저 보내고, 그 외 파일 보내기
    for attachment in message.attachments:
        if attachment.content_type:
            if attachment.content_type.startswith("video"):
                await target_channel.send(
                    content=f"🎬 동영상 첨부파일: {attachment.filename}",
                    file=await attachment.to_file()
                )

    non_image_non_video_attachments = [
        attachment for attachment in message.attachments
        if not (attachment.content_type and (attachment.content_type.startswith("image") or attachment.content_type.startswith("video")))
    ]
    for attachment in non_image_non_video_attachments:
        await target_channel.send(
            content=f"📎 첨부파일: {attachment.filename}",
            file=await attachment.to_file()
        )

bot.run(os.getenv("DISCORD_TOKEN"))
