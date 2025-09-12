import os
import sys
import asyncio
import time
from datetime import timedelta

import discord
from discord.ext import commands
from aiohttp import web
from dotenv import load_dotenv

from keep_alive import keep_alive

# .env 파일 로드
load_dotenv()

# JSON 파일로 매핑 데이터 관리
import json

MAPPING_FILE = "user_channel_mapping.json"

def load_mapping():
    """JSON 파일에서 매핑 데이터 로드 (서버별 구조)"""
    try:
        with open(MAPPING_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data.get('guild_mappings', {})
    except FileNotFoundError:
        return {}

def save_mapping(mapping):
    """매핑 데이터를 JSON 파일에 저장 (서버별 구조)"""
    data = {'guild_mappings': mapping}
    with open(MAPPING_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_user_mapping(guild_id, user_id):
    """특정 서버에서 사용자의 매핑을 가져옴"""
    guild_mappings = load_mapping()
    guild_id_str = str(guild_id)
    user_id_str = str(user_id)
    
    if guild_id_str in guild_mappings:
        return guild_mappings[guild_id_str].get(user_id_str)
    return None

def set_user_mapping(guild_id, user_id, channel_id):
    """특정 서버에서 사용자의 매핑을 설정함"""
    guild_mappings = load_mapping()
    guild_id_str = str(guild_id)
    user_id_str = str(user_id)
    channel_id_str = str(channel_id)
    
    if guild_id_str not in guild_mappings:
        guild_mappings[guild_id_str] = {}
    
    guild_mappings[guild_id_str][user_id_str] = channel_id_str
    save_mapping(guild_mappings)

def remove_user_mapping(guild_id, user_id):
    """특정 서버에서 사용자의 매핑을 삭제함"""
    guild_mappings = load_mapping()
    guild_id_str = str(guild_id)
    user_id_str = str(user_id)
    
    if guild_id_str in guild_mappings and user_id_str in guild_mappings[guild_id_str]:
        del guild_mappings[guild_id_str][user_id_str]
        save_mapping(guild_mappings)
        return True
    return False

def get_guild_mappings(guild_id):
    """특정 서버의 모든 매핑을 가져옴"""
    guild_mappings = load_mapping()
    guild_id_str = str(guild_id)
    return guild_mappings.get(guild_id_str, {})

# --- 외부 서비스 시작 ---
keep_alive()

intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True
intents.members = True

bot = commands.Bot(command_prefix='!', intents=intents)

# 서버별 매핑은 함수로 관리 (JSON 파일에서 로드)

# 사용할 이모지
target_emoji = "📌"

# 최근 반응 저장용 (중복 필터링)
recent_reactions = {}
CLEANUP_INTERVAL = 300  # 5분
last_cleanup = time.time()

def cleanup_old_reactions():
    #오래된 반응 기록들을 정리
    global last_cleanup
    now = time.time()
    
    if now - last_cleanup > CLEANUP_INTERVAL:
        old_keys = [
            key for key, timestamp in recent_reactions.items()
            if now - timestamp > 3
        ]
        for key in old_keys:
            del recent_reactions[key]
        
        last_cleanup = now
        if old_keys:  # 정리된 항목이 있을 때만 로그 출력
            print(f"[DEBUG] Cleaned up {len(old_keys)} old reactions")

#  aiohttp 웹서버 핸들러
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
    
    # 슬래시 명령어 동기화
    try:
        synced = await bot.tree.sync()
        print(f"[DEBUG] Synced {len(synced)} slash commands")
    except Exception as e:
        print(f"[ERROR] Failed to sync slash commands: {e}")

@bot.event
async def on_raw_reaction_add(payload):
    print(f"[DEBUG] Reaction event received: user_id={payload.user_id}, message_id={payload.message_id}, emoji={payload.emoji}, PID={os.getpid()}")
    print(f"[DEBUG] Reaction event received: user_id={payload.user_id}, message_id={payload.message_id}, emoji={payload.emoji}, channel_id={payload.channel_id}")

    if str(payload.emoji) != target_emoji:
        print(f"[DEBUG] Ignored emoji: {payload.emoji}")
        return

    key = (payload.user_id, payload.message_id, str(payload.emoji))
    now = time.time()

    # 정리 작업 먼저 실행
    cleanup_old_reactions()

    # 3초 이내에 같은 이벤트가 들어오면 무시
    if key in recent_reactions and now - recent_reactions[key] < 3:
        print(f"[DEBUG] Duplicate reaction ignored: {key}")
        return
    recent_reactions[key] = now
    print(f"[DEBUG] Processing reaction: {key}")

    user_id = payload.user_id
    guild_id = payload.guild_id
    
    # 서버별 매핑에서 사용자의 채널 찾기
    channel_id = get_user_mapping(guild_id, user_id)
    print(f"[DEBUG] Found mapping: guild_id={guild_id}, user_id={user_id}, channel_id={channel_id}")

    if not channel_id:
        print(f"⚠️ 서버 {guild_id}에서 유저 {user_id}에 대한 채널 매핑이 없음.")
        return
    
    # 채널 ID를 정수로 변환
    try:
        channel_id = int(channel_id)
        print(f"[DEBUG] Converted channel_id to int: {channel_id}")
    except (ValueError, TypeError):
        print(f"❌ 잘못된 채널 ID 형식: {channel_id}")
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

# 슬래시 명령어
@bot.tree.command(name="add", description="사용자-채널 매핑을 추가합니다")
async def add(interaction: discord.Interaction, user: discord.Member, channel: discord.TextChannel):
    """사용자와 채널을 매핑합니다"""
    
    # 권한 확인 (관리자 또는 본인만 가능)
    if not interaction.user.guild_permissions.administrator and interaction.user.id != user.id:
        await interaction.response.send_message("❌ 이 명령어는 관리자 또는 본인만 사용할 수 있습니다.", ephemeral=True)
        return
    
    # 현재 서버의 모든 매핑 가져오기
    guild_mappings = get_guild_mappings(interaction.guild_id)
    
    # 해당 채널이 이미 다른 사용자에게 매핑되어 있는지 확인
    for existing_user_id, existing_channel_id in guild_mappings.items():
        if str(existing_channel_id) == str(channel.id) and str(existing_user_id) != str(user.id):
            # 이미 매핑된 사용자 정보 가져오기
            existing_user = bot.get_user(int(existing_user_id))
            existing_user_name = existing_user.display_name if existing_user else f"사용자 ID: {existing_user_id}"
            
            # 경고 메시지와 함께 현재 매핑 상황 표시
            embed = discord.Embed(
                title="⚠️ 채널 중복 매핑 경고",
                description=f"**{channel.name}** 채널은 이미 **{existing_user_name}**이 사용 중입니다.",
                color=0xff6b6b
            )
            
            # 현재 매핑 목록 추가
            if guild_mappings:
                embed.add_field(
                    name="📌 현재 서버의 매핑 상황",
                    value="이 외의 다른 채널을 선택해주세요. 채널이 없다면 생성해주세요. 채널명에 본인의 닉네임을 명시하시면 좋습니다.",
                    inline=False
                )
                
                for user_id, channel_id in guild_mappings.items():
                    try:
                        mapped_user = bot.get_user(int(user_id))
                        mapped_channel = bot.get_channel(int(channel_id))
                        
                        if mapped_user and mapped_channel:
                            embed.add_field(
                                name=f"😃 {mapped_user.display_name}",
                                value=f"🖥️ {mapped_channel.name}",
                                inline=True
                            )
                    except:
                        embed.add_field(
                            name=f"❓ 사용자 ID: {user_id}",
                            value=f"❓ 채널 ID: {channel_id}",
                            inline=True
                        )
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
    
    # 중복이 없으면 매핑 추가
    set_user_mapping(interaction.guild_id, user.id, channel.id)
    
    await interaction.response.send_message(
        f"✅ **{user.display_name}** → **{channel.name}** 매핑이 완료되었습니다!",
        ephemeral=True
    )

@bot.tree.command(name="remove", description="사용자-채널 매핑을 삭제합니다")
async def remove(interaction: discord.Interaction, user: discord.Member):
    """사용자의 매핑을 삭제합니다"""
    
    # 권한 확인 (관리자 또는 본인만 가능)
    if not interaction.user.guild_permissions.administrator and interaction.user.id != user.id:
        await interaction.response.send_message("❌ 이 명령어는 관리자 또는 본인만 사용할 수 있습니다.", ephemeral=True)
        return
    
    # 서버별 매핑 삭제
    if remove_user_mapping(interaction.guild_id, user.id):
        await interaction.response.send_message(
            f"✅ **{user.display_name}**의 매핑이 삭제되었습니다!",
            ephemeral=True
        )
    else:
        await interaction.response.send_message(
            f"❌ **{user.display_name}**의 매핑을 찾을 수 없습니다.",
            ephemeral=True
        )

@bot.tree.command(name="list", description="현재 서버의 모든 매핑을 보여줍니다")
async def list(interaction: discord.Interaction):
    """현재 서버의 매핑 목록을 보여줍니다"""
    
    # 현재 서버의 매핑 가져오기
    guild_mappings = get_guild_mappings(interaction.guild_id)
    
    if not guild_mappings:
        await interaction.response.send_message("📝 현재 서버에 등록된 매핑이 없습니다.", ephemeral=True)
        return
    
    embed = discord.Embed(
        title=f"📌 {interaction.guild.name} 서버 북마크 매핑 목록",
        color=0x1abc9c
    )
    
    for user_id, channel_id in guild_mappings.items():
        try:
            user = bot.get_user(int(user_id))
            channel = bot.get_channel(int(channel_id))
            
            if user and channel:
                embed.add_field(
                    name=f"😃 {user.display_name}",
                    value=f"🖥️ {channel.name}",
                    inline=False
                )
            else:
                embed.add_field(
                    name=f"❓ 사용자 ID: {user_id}",
                    value=f"❓ 채널 ID: {channel_id}",
                    inline=False
                )
        except:
            embed.add_field(
                name=f"❓ 사용자 ID: {user_id}",
                value=f"❓ 채널 ID: {channel_id}",
                inline=False
            )
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="clear", description="현재 서버의 모든 매핑을 삭제합니다")
async def clear(interaction: discord.Interaction):
    """현재 서버의 모든 매핑을 삭제합니다"""
    
    # 권한 확인 (관리자만 가능)
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ 이 명령어는 관리자만 사용할 수 있습니다.", ephemeral=True)
        return
    
    # 현재 서버의 매핑 가져오기
    guild_mappings = get_guild_mappings(interaction.guild_id)
    count = len(guild_mappings)
    
    if count == 0:
        await interaction.response.send_message("📝 삭제할 매핑이 없습니다.", ephemeral=True)
        return
    
    # 현재 서버의 매핑만 삭제
    guild_mappings = load_mapping()
    guild_id_str = str(interaction.guild_id)
    if guild_id_str in guild_mappings:
        del guild_mappings[guild_id_str]
        save_mapping(guild_mappings)
    
    await interaction.response.send_message(
        f"✅ 현재 서버의 모든 매핑이 삭제되었습니다! (총 {count}개)",
        ephemeral=True
    )

bot.run(os.getenv("DISCORD_TOKEN"))
