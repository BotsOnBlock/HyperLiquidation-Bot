import time
import logging
import requests
import urllib.parse
import os
from dotenv import load_dotenv
from hyperliquid.info import Info
from hyperliquid.utils import constants

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

load_dotenv()
telegram_token = os.getenv('TELEGRAM_BOT_TOKEN')
chat_id = os.getenv('TELEGRAM_CHAT_ID')

liq_vault = "0x2e3d94f0562703b25c83308a05046ddaf9a8dd14"

class Liquidation:
    def __init__(self, price, size, asset, markPrice):
        self.price = price
        self.size = size
        self.asset = asset
        self.markPrice = markPrice

    def __str__(self):
        return f"• {self.asset}\n  Size: {self.size}\n  Price: {self.price}\n  Mark Price: {self.markPrice}\n  **${round(self.size * self.price, 2)}**\n"

    def __repr__(self):
        return self.__str__()
    
def on_event(event):
    try: 
        if "data" in event and "fills" in event["data"]:
            liquidations = []
            dir = ""
            for fill in event["data"]["fills"]:
                if "liquidation" in fill:
                    dir = fill["dir"]
                    price = float(fill["px"])
                    size = float(fill["sz"])
                    asset = fill["coin"]
                    markPrice = float(fill["liquidation"]["markPx"])
                    liquidation = Liquidation(price, size, asset, markPrice)
                    liquidations.append(liquidation)
            if liquidations:
                emoji = "📉" if "Long" in dir else "📈"
                message = f"{emoji} *{dir}*\n"
                for liquidation in liquidations:
                    message += str(liquidation) + "\n"
                logging.info(message)
                send_message(message)

    except Exception as e:
        logging.error("Error in on_event: %s", e)

def send_message(message):
    message = urllib.parse.quote(message)
    send_text = 'https://api.telegram.org/bot' + telegram_token + '/sendMessage?chat_id=' + chat_id + '&parse_mode=Markdown&text=' + message
    response = requests.get(send_text)


def maitain_ws():
    reconnect_delay = 5  # Start with a 5-second delay
    max_reconnect_delay = 300  # Maximum delay of 5 minutes

    while True:
        try:
            info = Info(constants.MAINNET_API_URL, skip_ws=False)
            r = info.subscribe({"type": "userEvents", "user": liq_vault}, on_event)
            logging.info("Subscribed to user events: %s", r)

            # Wait for the websocket to connect
            while not (info.ws_manager.ws.sock and info.ws_manager.ws.sock.connected):
                logging.info("Waiting for websocket to connect...")
                time.sleep(1)

            logging.info("Websocket connected successfully")

            # Reset reconnect delay on successful connection
            reconnect_delay = 5

            # Monitor the connection
            while info.ws_manager.ws.sock and info.ws_manager.ws.sock.connected:
                time.sleep(30)  # Check every 30 seconds

            logging.warning("Websocket connection closed. Preparing to reconnect...")

        except Exception as e:
            logging.error("Error in subscription: %s", e)

        finally:
            # Clean up resources
            if info:
                try:
                    info.ws_manager.close()
                except:
                    pass
                info = None

            # Implement exponential backoff for reconnection
            logging.info(f"Reconnecting in {reconnect_delay} seconds...")
            time.sleep(reconnect_delay)
            reconnect_delay = min(reconnect_delay * 2, max_reconnect_delay)


if __name__ == "__main__":
    maitain_ws()
