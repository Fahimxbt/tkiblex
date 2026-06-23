from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.errors import FloodWaitError
import asyncio
import os
import sys
import random
import time

# ========== CONFIG FROM ENVIRONMENT VARIABLES ==========
STRING_SESSION = os.environ.get('STRING_SESSION', '')
API_ID = int(os.environ.get('API_ID', '0'))
API_HASH = os.environ.get('API_HASH', '')
BOT_ID = int(os.environ.get('BOT_ID', '1'))
# ========================================================

if not STRING_SESSION or not API_ID or not API_HASH:
    print("[!] ERROR: Missing environment variables!")
    print("    Required: STRING_SESSION, API_ID, API_HASH")
    sys.exit(1)

client = TelegramClient(StringSession(STRING_SESSION), API_ID, API_HASH)

bot_entity = None
sticker_msg_id = None
heyyy_msg_id = None
f_msg_id = None

# State machine
STATE_IDLE = 'idle'
STATE_FINDING = 'finding'
STATE_MATCHED = 'matched'
STATE_PROMO_SENT = 'promo_sent'

current_state = STATE_IDLE
state_lock = asyncio.Lock()
match_start_time = 0
last_click_time = 0
last_partner_time = 0

# Timeouts
FINDING_TIMEOUT = 45
MATCH_STUCK_TIMEOUT = 60
RECOVERY_INTERVAL = 60

# Anti-self-match
MIN_PARTNER_INTERVAL = 15


async def safe_send_message(entity, message, retries=3):
    for attempt in range(retries):
        try:
            return await client.send_message(entity, message)
        except FloodWaitError as e:
            print(f"[!] FloodWait: Waiting {e.seconds} seconds...")
            await asyncio.sleep(e.seconds + 2)
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
            print(f"[!] FloodWait: Waiting {e.seconds} seconds...")
            await asyncio.sleep(e.seconds + 2)
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
            print(f"[!] FloodWait on click: Waiting {e.seconds} seconds...")
            await asyncio.sleep(e.seconds + 2)
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

        if sticker_msg_id:
            print("[+] Ready to run (sticker found)")
            return True

    except Exception as e:
        print(f"[!] Find error: {e}")

    print("[!] Send 'heyyy', 'F', and a sticker to Saved Messages first!")
    return False


async def dismiss_rating():
    try:
        msgs = await client.get_messages(bot_entity, limit=5)
        for m in msgs:
            if m.reply_markup and m.reply_markup.rows:
                for row in m.reply_markup.rows:
                    for btn in row.buttons:
                        btn_text = btn.text or ''
                        if 'like' in btn_text.lower() or 'dislike' in btn_text.lower():
                            result = await safe_click(m, btn.text)
                            if result:
                                print(f"[→] Rating dismissed: {btn_text}")
                                await asyncio.sleep(2)
                                return True
    except Exception as e:
        print(f"[!] Dismiss rating error: {e}")
    return False


async def click_next():
    global current_state, last_click_time, last_partner_time

    async with state_lock:
        if current_state in (STATE_MATCHED, STATE_PROMO_SENT):
            print(f"[*] In match (state={current_state}), skipping Next")
            return False

        now = time.time()
        if now - last_click_time < 7:
            print(f"[*] Click cooldown active ({now - last_click_time:.1f}s), skipping...")
            return False
        last_click_time = now

        if current_state == STATE_FINDING:
            print("[*] Already finding partner, skipping...")
            return False

        current_state = STATE_FINDING

    # ANTI-SELF-MATCH: staggered random delay based on BOT_ID
    base_delay = BOT_ID * 1.5
    random_delay = random.uniform(0, 3)
    total_delay = base_delay + random_delay
    print(f"[*] Anti-self-match: waiting {total_delay:.1f}s before Next (bot_id={BOT_ID})...")
    await asyncio.sleep(total_delay)

    # Rate limit check
    elapsed = time.time() - last_partner_time
    if elapsed < MIN_PARTNER_INTERVAL:
        wait = MIN_PARTNER_INTERVAL - elapsed
        print(f"[*] Rate limit: waiting {wait:.1f}s before next search...")
        await asyncio.sleep(wait)

    # Re-check state after delay
    async with state_lock:
        if current_state in (STATE_MATCHED, STATE_PROMO_SENT):
            print(f"[*] State changed to match during delay, aborting Next")
            return False

    print("[*] Looking for Next button...")

    # Try button first
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
                                last_partner_time = time.time()
                                await asyncio.sleep(3)
                                return True
    except Exception as e:
        print(f"[!] get_messages error: {e}")

    # Fallback to /next
    async with state_lock:
        if current_state == STATE_FINDING:
            print("[!] Next button not found, using /next fallback")
            await safe_send_message(bot_entity, '/next')
            last_partner_time = time.time()
            await asyncio.sleep(3)
            return True

    return False


async def handle_match():
    global current_state

    # Step 1: Forward "heyyy" immediately
    async with state_lock:
        if current_state != STATE_MATCHED:
            print(f"[*] Not in match (state={current_state}), aborting handle_match")
            return
        current_state = STATE_PROMO_SENT

    print("[*] Forwarding heyyy...")
    try:
        if heyyy_msg_id:
            await safe_forward_messages(bot_entity, heyyy_msg_id, 'me')
            print("[+] Forwarded: heyyy")
        else:
            await safe_send_message(bot_entity, "heyyy")
            print("[+] Sent: heyyy")
    except Exception as e:
        print(f"[!] heyyy error: {e}")

    # Wait 3 seconds
    print("[*] Waiting 3s before F...")
    waited = 0
    check_interval = 0.5
    while waited < 3:
        await asyncio.sleep(check_interval)
        waited += check_interval
        async with state_lock:
            if current_state != STATE_PROMO_SENT:
                print(f"[*] State changed to {current_state} during heyyy wait (early skip)")
                return

    # Step 2: Forward "F"
    async with state_lock:
        if current_state != STATE_PROMO_SENT:
            print(f"[*] State changed to {current_state}, aborting F")
            return

    print("[*] Forwarding F...")
    try:
        if f_msg_id:
            await safe_forward_messages(bot_entity, f_msg_id, 'me')
            print("[+] Forwarded: F")
        else:
            await safe_send_message(bot_entity, "F")
            print("[+] Sent: F")
    except Exception as e:
        print(f"[!] F error: {e}")

    # Wait 4 seconds
    print("[*] Waiting 4s before sticker...")
    waited = 0
    while waited < 4:
        await asyncio.sleep(check_interval)
        waited += check_interval
        async with state_lock:
            if current_state != STATE_PROMO_SENT:
                print(f"[*] State changed to {current_state} during F wait (early skip)")
                return

    # Step 3: Forward sticker
    async with state_lock:
        if current_state != STATE_PROMO_SENT:
            print(f"[*] State changed to {current_state}, aborting sticker")
            return

    print("[*] Forwarding sticker...")
    try:
        if sticker_msg_id:
            await safe_forward_messages(bot_entity, sticker_msg_id, 'me')
            print("[+] Sticker forwarded!")
        else:
            await safe_send_message(bot_entity, "💜 @chatxbt_bot\nhttps://t.me/chatxbt_bot")
            print("[+] Text promo sent!")
    except Exception as e:
        print(f"[!] Sticker error: {e}")

    # Wait 3 seconds after sticker, check for early skip
    print("[*] Waiting 3s after sticker...")
    waited = 0
    while waited < 3:
        await asyncio.sleep(check_interval)
        waited += check_interval
        async with state_lock:
            if current_state != STATE_PROMO_SENT:
                print(f"[*] State changed to {current_state} during post-sticker wait (early skip)")
                return

    # Now find next partner
    async with state_lock:
        current_state = STATE_IDLE

    await click_next()


async def handle_finding_timeout():
    global current_state
    await asyncio.sleep(FINDING_TIMEOUT)

    try:
        async with state_lock:
            state = current_state

        if state != STATE_FINDING:
            return

        print(f"[!] Finding timeout! No partner after {FINDING_TIMEOUT}s.")

        async with state_lock:
            current_state = STATE_IDLE

        await dismiss_rating()
        await click_next()
    except Exception as e:
        print(f"[!] Finding timeout error: {e}")


async def stuck_watchdog():
    global current_state
    await asyncio.sleep(MATCH_STUCK_TIMEOUT)

    try:
        async with state_lock:
            state = current_state

        if state not in (STATE_MATCHED, STATE_PROMO_SENT):
            return

        elapsed = time.time() - match_start_time
        if elapsed >= MATCH_STUCK_TIMEOUT:
            print(f"[!] MATCH STUCK for {elapsed:.0f}s, forcing /end and next...")

            async with state_lock:
                current_state = STATE_IDLE

            await safe_send_message(bot_entity, '/end')
            await asyncio.sleep(3)
            await dismiss_rating()
            await click_next()
    except Exception as e:
        print(f"[!] Stuck watchdog error: {e}")


async def recovery_watchdog():
    global current_state
    while True:
        await asyncio.sleep(RECOVERY_INTERVAL)

        try:
            async with state_lock:
                state = current_state

            if state == STATE_IDLE:
                print("[!] Watchdog: Idle state detected, finding partner...")
                await click_next()
        except Exception as e:
            print(f"[!] Watchdog error: {e}")


@client.on(events.NewMessage(chats='@tikible_bot'))
async def handler(event):
    global current_state, match_start_time

    text = event.text or ''

    if event.out:
        return

    # ========== PARTNER LEFT THE CHAT ==========
    if 'partner has left' in text.lower() or 'partner ended' in text.lower():
        print("[✓] Partner left the chat!")

        async with state_lock:
            current_state = STATE_IDLE

        await asyncio.sleep(2)
        await dismiss_rating()
        await click_next()
        return

    # ========== YOU LEFT THE CHAT ==========
    if 'you left' in text.lower():
        print("[✓] You left the chat")

        async with state_lock:
            current_state = STATE_IDLE

        await asyncio.sleep(2)
        await dismiss_rating()
        await click_next()
        return

    # ========== BOT WELCOME / MENU ==========
    if "I'm an anonymous chat bot" in text or "Use the menu" in text or "Meet strangers" in text:
        print("[*] Bot welcome/menu shown")

        async with state_lock:
            current_state = STATE_IDLE

        await asyncio.sleep(1)
        await click_next()
        return

    # ========== FINDING PARTNER ==========
    if 'Finding a random partner' in text or 'Searching' in text:
        print("[...] Searching for partner...")

        async with state_lock:
            current_state = STATE_FINDING

        asyncio.create_task(handle_finding_timeout())
        return

    # ========== MATCH STARTED ==========
    if 'Match successful' in text:
        print("[+] Match started!")

        async with state_lock:
            current_state = STATE_MATCHED
            match_start_time = time.time()

        # Start stuck watchdog
        asyncio.create_task(stuck_watchdog())

        # Start promo
        asyncio.create_task(handle_match())
        return

    # ========== PARTNER SENT MESSAGE DURING MATCH ==========
    async with state_lock:
        state = current_state

    if state == STATE_MATCHED:
        # Partner messaged before we sent heyyy
        print("[+] Partner sent message before our heyyy!")
        return

    if state == STATE_PROMO_SENT:
        # Partner messaged after promo started
        print("[+] Partner sent message during promo")
        return


async def main():
    global bot_entity
    await client.start()
    print(f"[*] Tikible Bot (@tikible_bot) started! BOT_ID={BOT_ID}")
    print(f"[*] FINDING_TIMEOUT={FINDING_TIMEOUT}s | MATCH_STUCK_TIMEOUT={MATCH_STUCK_TIMEOUT}s")
    print("[*] Flow: heyyy → 3s → F → 4s → sticker → 3s → Next")
    print("[*] Connected to Telegram successfully!")

    bot_entity = await client.get_entity('@tikible_bot')
    await find_messages()
    await click_next()

    asyncio.create_task(recovery_watchdog())

    await client.run_until_disconnected()


if __name__ == '__main__':
    while True:
        try:
            with client:
                client.loop.run_until_complete(main())
        except KeyboardInterrupt:
            print("\n[*] Bot stopped by user.")
            break
        except Exception as e:
            print(f"[!] Fatal error: {e}")
            print("[*] Restarting in 10 seconds...")
            time.sleep(10)
