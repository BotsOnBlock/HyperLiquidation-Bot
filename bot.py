import time
import json
import requests
import urllib.parse
import threading
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from dotenv import load_dotenv
import os
from hyperliquid.info import Info
from hyperliquid.utils import constants
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from typing import Dict, List
import traceback

load_dotenv()
telegram_token = os.getenv('TELEGRAM_BOT_TOKEN')

BASE_ALERT_THRESHOLD = 0.70
REFRESH_INTERVAL = 600 # 10 minutes

wallets: Dict[str, List[int]] = {}
info = Info(constants.MAINNET_API_URL, skip_ws=False)

def read_settings():
    global wallets
    with open("settings.json", "r") as f:
        wallets = json.load(f)
    
def save_settings():
    with open("settings.json", "w") as f:
        json.dump(wallets, f, indent=4)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.from_user.first_name
    await update.message.reply_text(f"GM {name}!\nDon't wanna get HyperLiquidated? I'm here to help you.")
    await help(update, context)

async def help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("This bot can send you alerts when one of your positions on HyperLiquid perp is getting near liquidation.\n\n"
                                    "Here is the list of available commands:\n"
                              "/add <wallet_address> : Add a wallet to the monitoring list\n"
                              "/list : List the wallets you are monitoring\n"
                              "/remove <wallet_address> : Stop monitoring a wallet")

def validate_wallet(wallet: str) -> bool:
    return wallet.startswith("0x") and len(wallet) == 42 and all(c in "0123456789abcdefABCDEF" for c in wallet[2:])

def format_wallet_link(wallet: str) -> str:
    if not validate_wallet(wallet):
        return "Invalid wallet address"
    
    visible_part = f"{wallet[:10]}...{wallet[-8:]}"
    link = f"https://app.hyperliquid.xyz/explorer/address/{wallet}"
    return f"[{visible_part}]({link})"

async def add_wallet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args:
        wallet_address = context.args[0]
        user_id = update.message.from_user.id

        if not validate_wallet(wallet_address):
            await update.message.reply_text("Invalid wallet address.")
            return

        try:
            user_state = info.user_state(wallet_address)
        except Exception as e:
            user_state = None
            print(f"Error retrieving user data: {e}")

        if user_state:
            if float(user_state["marginSummary"]["accountValue"]) > 0:
                if wallet_address not in wallets:
                    wallets[wallet_address] = []
                if user_id not in wallets[wallet_address]:
                    wallets[wallet_address].append(user_id)
                    await update.message.reply_text(f"Wallet {format_wallet_link(wallet_address)} added to monitoring list.", parse_mode="Markdown")
                    save_settings()
                else:
                    await update.message.reply_text(f"You are already monitoring wallet {format_wallet_link(wallet_address)}.", parse_mode="Markdown")
            else:
                await update.message.reply_text("This wallet has no funds on HyperLiquid.")
        else:
            await update.message.reply_text("Error retrieving user data.")
    else:
        await update.message.reply_text("Please provide a wallet address.")

async def list_wallets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    monitored_wallets = [addr for addr, users in wallets.items() if user_id in users]
    if monitored_wallets:
        formatted_wallets = [format_wallet_link(addr) for addr in monitored_wallets]
        await update.message.reply_text("You are monitoring the following wallets:\n" + "\n".join(formatted_wallets), parse_mode="Markdown")
    else:
        await update.message.reply_text("You are not monitoring any wallets.")

async def remove_wallet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args:
        wallet_address = context.args[0]
        user_id = update.message.from_user.id
        if wallet_address in wallets and user_id in wallets[wallet_address]:
            wallets[wallet_address].remove(user_id)
            if not wallets[wallet_address]:  # If no users are monitoring this wallet, remove it
                del wallets[wallet_address]
            await update.message.reply_text(f"Stopped monitoring wallet {format_wallet_link(wallet_address)}.", parse_mode="Markdown")
            save_settings()
        else:
            await update.message.reply_text(f"You are not monitoring wallet {format_wallet_link(wallet_address)}.", parse_mode="Markdown")
    else:
        await update.message.reply_text("Please provide a wallet address.")

def fetch_assets():
    url = "https://api.hyperliquid.xyz/info"
    headers = {
        "Content-Type": "application/json"
    }
    payload = {
        "type": "metaAndAssetCtxs"
    }

    try:
        response = requests.post(url, headers=headers, data=json.dumps(payload))
        if response.status_code == 200:
            return response.json()
        else:
            print(f"Failed to fetch data. Status code: {response.status_code}")
            return None
    except Exception as e:
        print(f"Error: {e}")
        return None
    
def get_mark_price(data, asset_name):
    try:
        universe = data[0]['universe']
        asset_ctxs = data[1]
        
        for i, asset in enumerate(universe):
            if asset['name'] == asset_name:
                mark_price = asset_ctxs[i]['markPx']
                return float(mark_price)
        
        print(f"Asset {asset_name} not found in the universe.")
        return None
    except Exception as e:
        print(f"Error getting {asset_name} mark price : {e}")
        return None
    
def check_positions():
    while True:
        print("Checking positions...")
        local_wallets = wallets.copy()
        data = fetch_assets()
        if not data:
            time.sleep(60)
            continue
        with ThreadPoolExecutor(max_workers=32) as executor:  
            executor.map(partial(check_wallet_positions, data), local_wallets.keys())
        print("Positions checked.")
        time.sleep(REFRESH_INTERVAL)  

def check_wallet_positions(data, wallet_address):
    try:
        user_data = info.user_state(wallet_address)
        positions = user_data['assetPositions']
        cross_account_value = float(user_data['crossMarginSummary']['accountValue'])
        if cross_account_value != 0:
            maintenace_margin_used = float(user_data['crossMaintenanceMarginUsed'])
            margin_ratio =  maintenace_margin_used / cross_account_value

            if margin_ratio > BASE_ALERT_THRESHOLD:
                cross_margin_positions = [pos for pos in positions if pos['position']['leverage']['type'] == 'cross']

                for pos in cross_margin_positions:
                    pos_data = pos['position']
                    coin = pos_data['coin']
                    current_price = get_mark_price(data, coin)
                    liquidation_price = pos_data['liquidationPx']
                    if liquidation_price is None:
                        move_before_liq = 1
                    else:
                        liquidation_price = float(liquidation_price) 
                        move_before_liq = abs(current_price - liquidation_price) / current_price
                    pos_data['move_before_liq'] = move_before_liq

                cross_margin_positions = sorted(cross_margin_positions, key=lambda pos: pos['position']['move_before_liq'])
                # coin_list = [pos['position']['coin'] for pos in cross_margin_positions]

                alert_message = (
                    f"⚠️ *Cross margin liquidation risk alert* ⚠️\n"
                    f"Wallet *{wallet_address[:8] + '...' + wallet_address[-6:]}*\n"
                    f"• Cross margin account value: *${round(cross_account_value, 2)}*\n"
                    f"• Margin ratio: *{round(margin_ratio * 100, 2)}%* (your cross positions will be liquidated if margin ratio reaches 100%)\n"
                    f"• Maintenance margin used: *${round(maintenace_margin_used, 2)}*\n"
                    f"• *{len(cross_margin_positions)} positions* at risk: (be careful that liquidation prices will change as the prices move, monitor your positions on [HyperLiquid app](app.hyperliquid.xyz/trade))\n")
                    # f"Positions at risk: {', '.join(coin_list)}\n")

                position_messages = []
                for pos in cross_margin_positions:
                    pos_data = pos['position']
                    coin = pos_data['coin']
                    current_price = get_mark_price(data, coin)
                    liquidation_price = pos_data['liquidationPx']
                    position_message = (
                        f"• {coin}\n"
                        f"  Current price: {current_price}\n"
                        f"  Liquidation price: {liquidation_price}\n"
                    )
                    position_messages.append(position_message)
                position_message = "\n".join(position_messages)

                for user_id in wallets[wallet_address]:
                    send_message(user_id, alert_message)
                    send_message(user_id, position_message)
            
        isolated_positions = [pos for pos in positions if pos['position']['leverage']['type'] == 'isolated']
        for pos in isolated_positions:
            pos_data = pos['position']
            coin = pos_data['coin']
            current_price = get_mark_price(data, coin)
            liquidation_price = pos_data['liquidationPx']
            entry_price = float(pos_data['entryPx'])
            uPnL = float(pos_data['unrealizedPnl'])
            if liquidation_price is None or uPnL > 0:
                continue
            else:
                liquidation_price = float(liquidation_price) 
                move_before_liq = abs(entry_price - current_price) / abs(entry_price - liquidation_price)
                if move_before_liq > BASE_ALERT_THRESHOLD:
                    alert_message = (
                        f"⚠️ *Isolated position liquidation risk alert* ⚠️\n"
                        f"Wallet: *{wallet_address[:8] + '...' + wallet_address[-6:]}*\n"
                        f"Position at risk: {coin}\n"
                        f"Current price: ${current_price}\n"
                        f"Liquidation price: ${liquidation_price}\n"
                    )
                    for user_id in wallets[wallet_address]:
                        send_message(user_id, alert_message)

    except Exception as e:
        print(f"Error fetching positions for wallet {wallet_address}: {e}")
        print(traceback.format_exc())

def send_message(user_id, message):
    message = urllib.parse.quote(message)
    send_text = 'https://api.telegram.org/bot' + telegram_token + '/sendMessage?chat_id=' + str(user_id) + '&parse_mode=Markdown&text=' + message
    response = requests.get(send_text)

def main() -> None:
    read_settings()

    application = Application.builder().token(telegram_token).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("add", add_wallet))
    application.add_handler(CommandHandler("list", list_wallets))
    application.add_handler(CommandHandler("remove", remove_wallet))
    application.add_handler(CommandHandler("help", help))

    # on non command i.e message - do nothing
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, {
        "callback": lambda update, context: None
    }))

    # Start the position checking in a separate thread
    threading.Thread(target=check_positions, daemon=True).start()

    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()