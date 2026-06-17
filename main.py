from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.errors import FloodWaitError
import asyncio
import sys

# ========== HARDCODED CONFIG ==========
STRING_SESSION = '1BVtsOKcBu3Q1J_DVpoYr2eAkqIIz-lcga6QwZ_elbq1JsKXF8qTmgVXYv3irxcBvwlin1QS3PNOqOe9J0mmZX1uTVoWDcQb-TzmxZnOMyrmwv4Wotj82hIiNTk6IvrxED6rA6XshXBG8ST_2PN78vQX651KnINFs_MwtbIPP5CZHirfnRN2cdeT84dTtL27ODNgfXe-Gn_8cYLFQz3nEX6NqxZxoJAzvtapi9oVkt0hOZBHmrHdX3VoJ36tWm-ucJmzXNtnirw3jUQ9kqitXhh8WVcSui2ZgeDZ9MYmgl0UX970buyBbySeLPuo2zDsmb8A6i6zb06lhxtXc='
API_ID = 316565
API_HASH = '46fa4b3be12f89dc84d447cf3fc820'
# ======================================

client = TelegramClient(StringSession(STRING_SESSION), API_ID, API_HASH)

bot_entity = None
sticker_msg_id = None
heyyy_msg_id = None
f_msg_id = None

match_active = False
promo_sent = False
sending_lock = asyncio.Lock()
promo_cancelled = False
finding_lock = asyncio.Lock()
chat_ended = False
finding_timeout_task = None

# Rate limiting protection
MIN_PARTNER_INTERVAL = 15
last_partner_time = 0


async def safe_send_message(entity, message, retries=3):
    for attempt in range(retries):
        try:
            return await client.send_message(entity, message)
        except FloodWaitError as e:
            wait_time = e.seconds
            print(f"[!] FloodWait: Waiting {wait_time} seconds...")
            await asyncio.sleep(wait_time + 2)
        except Exception as e:
            print(f"[!] Send error (attempt {attempt+1}): {e}")
            if attempt < retries - 1:
                await asyncio.sleep(5)
    return None


async def safe_forward_messages(entity, msg_id, from_peer, retries=3):
    for attempt in range(retries):
        try:
            return await client.forward_messages(entity, msg_id, from_peer)
        except FloodWaitError as e:
            wait_time = e.seconds
            print(f"[!] FloodWait: Waiting {wait_time} seconds...")
            await asyncio.sleep(wait_time + 2)
        except Exception as e:
            print(f"[!] Forward error (attempt {attempt+1}): {e}")
            if attempt < retries - 1:
                await asyncio.sleep(5)
    return None


async def safe_click(message, text, retries=3):
    for attempt in range(retries):
        try:
            return await message.click(text=text)
        except FloodWaitError as e:
            wait_time = e.seconds
            print(f"[!] FloodWait on click: Waiting {wait_time} seconds...")
            await asyncio.sleep(wait_time + 2)
        except Exception as e:
            print(f"[!] Click error (attempt {attempt+1}): {e}")
            if attempt < retries - 1:
                await asyncio.sleep(5)
    return None


async def find_messages():
    global sticker_msg_id, heyyy_msg_id, f_msg_id
    try:
        msgs = await client.get_messages('me', limit=50)
        for m in msgs:
            if m.sticker and not sticker_msg_id:
                sticker_msg_id = m.id
                print("[+] Sticker found!")
            if m.text and m.text.lower() == 'heyyy' and not heyyy_msg_id:
                heyyy_msg_id = m.id
                print("[+] 'heyyy' message found!")
            if m.text and m.text.upper() == 'F' and not f_msg_id:
                f_msg_id = m.id
                print("[+] 'F' message found!")
        
        if all([sticker_msg_id, heyyy_msg_id, f_msg_id]):
            print("[+] All messages found!")
            return True
            
    except Exception as e:
        print(f"[!] Find error: {e}")
    
    print("[!] Send 'heyyy', 'F', and a sticker to Saved Messages first!")
    return False


async def click_next():
    global match_active, promo_sent, last_partner_time
    
    if finding_lock.locked():
        print("[*] Already finding partner, skipping...")
        return True
    
    async with finding_lock:
        elapsed = asyncio.get_event_loop().time() - last_partner_time
        if elapsed < MIN_PARTNER_INTERVAL:
            wait = MIN_PARTNER_INTERVAL - elapsed
            print(f"[*] Rate limit: waiting {wait:.1f}s before next search...")
            await asyncio.sleep(wait)
        
        print("[*] Looking for Next button...")
        
        try:
            msgs = await client.get_messages(bot_entity, limit=10)
            for m in msgs:
                if m.reply_markup:
                    for row in m.reply_markup.rows:
                        for btn in row.buttons:
                            btn_text = btn.text or ''
                            if 'Next' in btn_text:
                                result = await safe_click(m, btn.text)
                                if result:
                                    print("[→] Next clicked")
                                    match_active = False
                                    promo_sent = False
                                    last_partner_time = asyncio.get_event_loop().time()
                                    await asyncio.sleep(3)
                                    return True
                                continue
        except Exception as e:
            print(f"[!] get_messages error: {e}")
        
        print("[!] Next button not found, using /next fallback")
        await safe_send_message(bot_entity, '/next')
        print("[→] /next sent (fallback)")
        match_active = False
        promo_sent = False
        last_partner_time = asyncio.get_event_loop().time()
        await asyncio.sleep(3)
        return True


async def send_promo():
    global promo_sent, promo_cancelled
    
    if sending_lock.locked() or promo_sent:
        print("[*] Already sending or already sent, skipping...")
        return
    
    async with sending_lock:
        promo_cancelled = False
        print("[*] Starting forward sequence...")
        
        try:
            # Step 1: Forward "heyyy"
            if promo_cancelled:
                print("[!] Promo cancelled before heyyy")
                return
            
            if heyyy_msg_id:
                await safe_forward_messages(bot_entity, heyyy_msg_id, 'me')
                print("[+] Forwarded: heyyy")
            else:
                await safe_send_message(bot_entity, "heyyy")
                print("[+] Sent: heyyy")
            
            print("[*] Waiting 4 seconds...")
            await asyncio.sleep(4)
            
            # Step 2: Forward "F"
            if promo_cancelled:
                print("[!] Promo cancelled before F")
                return
            
            if f_msg_id:
                await safe_forward_messages(bot_entity, f_msg_id, 'me')
                print("[+] Forwarded: F")
            else:
                await safe_send_message(bot_entity, "F")
                print("[+] Sent: F")
            
            print("[*] Waiting 6 seconds...")
            await asyncio.sleep(6)
            
            # Step 3: Forward sticker
            if promo_cancelled:
                print("[!] Promo cancelled before sticker")
                return
            
            if sticker_msg_id:
                await safe_forward_messages(bot_entity, sticker_msg_id, 'me')
                print("[+] Sticker forwarded!")
            else:
                await safe_send_message(bot_entity, "💜 @chatxbt_bot\nhttps://t.me/chatxbt_bot")
                print("[+] Text promo sent!")
            
            print("[*] Waiting 4 seconds before next user...")
            await asyncio.sleep(4)
            
            promo_sent = True
            print("[✓] Promo sequence complete!")
            
        except Exception as e:
            print(f"[!] Send error: {e}")
            promo_sent = False


@client.on(events.NewMessage(chats='@tikible_bot'))
async def handler(event):
    global match_active, promo_sent, promo_cancelled
    
    text = event.text or ''
    
    if event.out:
        return
    
    # ========== PARTNER LEFT THE CHAT ==========
    if 'partner has left' in text.lower() or 'partner ended' in text.lower():
        print("[✓] Partner left the chat!")
        match_active = False
        promo_sent = False
        
        if sending_lock.locked():
            print("[!] Cancelling promo...")
            promo_cancelled = True
            for _ in range(100):
                if not sending_lock.locked():
                    break
                await asyncio.sleep(0.1)
        
        await asyncio.sleep(2)
        await click_next()
        return
    
    # ========== YOU LEFT THE CHAT ==========
    if 'you left' in text.lower():
        print("[✓] You left the chat")
        match_active = False
        promo_sent = False
        await asyncio.sleep(2)
        await click_next()
        return
    
    # ========== MATCH STARTED ==========
    if 'Match successful' in text:
        print("[+] Match started!")
        match_active = True
        promo_sent = False
        promo_cancelled = False
        
        await asyncio.sleep(1)
        await send_promo()
        
        if not promo_cancelled:
            await click_next()
        else:
            print("[!] Promo cancelled, finding next...")
            await asyncio.sleep(1)
            await click_next()
        return
    
    # ========== FINDING PARTNER ==========
    if 'Finding a random partner' in text:
        print("[...] Searching...")
        match_active = False
        promo_sent = False
        return
    
    # ========== PARTNER SENT MESSAGE DURING MATCH ==========
    if match_active and not promo_sent and not sending_lock.locked():
        print("[+] Partner messaged first!")
        await send_promo()
        
        if not promo_cancelled:
            await click_next()
        else:
            print("[!] Promo cancelled, finding next...")
            await asyncio.sleep(1)
            await click_next()
        return


async def main():
    global bot_entity
    await client.start()
    print("[*] xbt1-bot (@tikible_bot) started!")
    print("[*] Connected to Telegram successfully!")
    
    bot_entity = await client.get_entity('@tikible_bot')
    msgs_found = await find_messages()
    
    if not msgs_found:
        print("[!] WARNING: Some messages not found in Saved Messages!")
        print("[!] The bot will use text fallback for missing messages.")
    
    await safe_send_message(bot_entity, '/next')
    
    await client.run_until_disconnected()


if __name__ == '__main__':
    try:
        with client:
            client.loop.run_until_complete(main())
    except KeyboardInterrupt:
        print("\n[*] Bot stopped by user.")
    except Exception as e:
        print(f"[!] Fatal error: {e}")
        sys.exit(1)
