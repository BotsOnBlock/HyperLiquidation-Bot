import json
import time
import logging
import requests
import urllib.parse
import os
from dotenv import load_dotenv
import websocket
import threading

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

load_dotenv()
TELEGRAM_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

MAINNET_WS_URL = 'wss://api.hyperliquid.xyz/ws'
LIQ_VAULT = "0x2e3d94f0562703b25c83308a05046ddaf9a8dd14"

class Liquidation:
    def __init__(self, value, size, asset, markPrice):
        self.size = size
        self.total_value = value
        self.asset = asset
        self.markPrice = markPrice

    def __str__(self):
        return f"• {self.asset}\n  Size: {self.size}\n  Value: ${self.total_value:.2f}\n  Mark Price: {self.markPrice}**\n"

def send_message(message):
    message = urllib.parse.quote(message)
    send_text = f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage?chat_id={TELEGRAM_CHAT_ID}&parse_mode=Markdown&text={message}'
    response = requests.get(send_text)
    if response.status_code != 200:
        logger.error(f"Failed to send Telegram message: {response.text}")

def on_message(ws, message):
    try:
        event = json.loads(message)
        if event.get("channel") == "pong":
            logger.debug("Received pong from server")
        elif event.get("channel") == "subscriptionResponse":
            logger.debug(f"Subscription response: {event}")
        elif event.get("channel") == "user":
            on_user_event(event.get("data", {}))
        else:
            logger.warning(f"Received message: {message}")
    except json.JSONDecodeError:
        logger.warning(f"Received non-JSON message: {message}")

def on_user_event(event):
    try:
        if "fills" in event:
            liquidations_by_token = {}
            dir = ""
            for fill in event["fills"]:
                if "liquidation" in fill:
                    dir = fill["dir"]
                    token = fill["coin"]
                    price = float(fill["px"])
                    size = float(fill["sz"])
                    mark_price = float(fill["liquidation"]["markPx"])
                    
                    if token not in liquidations_by_token:
                        liquidations_by_token[token] = {
                            "total_size": 0,
                            "total_value": 0,
                            "mark_price": mark_price
                        }
                    
                    liquidations_by_token[token]["total_size"] += size
                    liquidations_by_token[token]["total_value"] += size * price
            
            if liquidations_by_token:
                emoji = "📉" if "Long" in dir else "📈"
                message = f"{emoji} *{dir}*\n"
                
                for token, data in liquidations_by_token.items():
                    liquidation = Liquidation(
                        data["total_value"],
                        data["total_size"],
                        token,
                        data["mark_price"]
                    )
                    message += str(liquidation) + "\n"
                
                logger.info(message)
                send_message(message)
    except Exception as e:
        logger.error(f"Error in on_user_event: {e}")

def send_ping(ws):
    while True:
        time.sleep(30)
        if ws.sock and ws.sock.connected:
            ping_message = json.dumps({"method": "ping"})
            ws.send(ping_message)
            logger.debug(f"Sent ping: {ping_message}")
        else:
            logger.warning("WebSocket is not connected. Stopping ping.")
            break

def on_open(ws):
    logger.info("WebSocket connected successfully")
    subscription = json.dumps({
        "method": "subscribe",
        "subscription": {"type": "userEvents", "user": LIQ_VAULT}
    })
    ws.send(subscription)
    logger.debug(f"Sent subscription request: {subscription}")

    # Start the ping thread here
    ping_thread = threading.Thread(target=send_ping, args=(ws,))
    ping_thread.daemon = True
    ping_thread.start()

def on_close(ws, close_status_code, close_msg):
    logger.warning(f"WebSocket connection closed: {close_status_code} - {close_msg}")

def on_error(ws, error):
    logger.error(f"WebSocket error: {error}")

def maintain_ws():
    reconnect_delay = 5  # Start with a 5-second delay
    max_reconnect_delay = 300  # Maximum delay of 5 minutes

    while True:
        try:
            ws = websocket.WebSocketApp(
                MAINNET_WS_URL,
                on_open=on_open,
                on_message=on_message,
                on_error=on_error,
                on_close=on_close
            )

            ws.run_forever()
        except Exception as e:
            logger.error(f"Error in WebSocket connection: {e}")
        finally:
            logger.info(f"Reconnecting in {reconnect_delay} seconds...")
            time.sleep(reconnect_delay)
            reconnect_delay = min(reconnect_delay * 2, max_reconnect_delay)

if __name__ == "__main__":
    maintain_ws()
