# HyperLiquidation-Bot

![Version](https://img.shields.io/badge/version-1.0-darkgray) ![Python](https://img.shields.io/badge/python-3.9-blue) ![Status](https://img.shields.io/badge/status-active-brightgreen) ![Contributions](https://img.shields.io/badge/contributions-welcome-orange) ![License](https://img.shields.io/badge/license-GPLv3-green) ![Twitter](https://img.shields.io/badge/twitter-%40the%5Fecoinomist-blue)

A Telegram bot to monitor when your margin ratio is above a threshold on HyperLiquid trading platform.
&nbsp;
bot.py is the main file that runs the bot. You can try it at [@hyperliquidation_bot](https:///t.me/hyperliquidation_bot) on Telegram.

channel.py can be run to monitor in real-time the liquidations on HyperLiquid and sends a message to a Telegram channel when a liquidation occurs. You can try it at [@hyperliquidations](https:///t.me/hyperliquidations) on Telegram.

---

### Usage

To run the bot by yourself, you need to have Python 3.9 and install the required packages (HyperLiquid SDK and Telegram library). You can follow the steps below :

1. Clone the repository

```bash
git clone https://github.com/BotsOnBlock/HyperLiquidation-Bot.git
```

2. Install the required packages

```bash
pip install -r requirements.txt
```

3. Set up the .env file

```bash
cp .env.example .env
```

And edit the required fields. You can get the Telegram token by talking to the BotFather on Telegram to create a new bot.

---

### Improvement ideas:

-   Use a database
-   Review the ratio formula (for isolated margin)
-   Allow users to choose the threshold to be notified for
-   Add a command to get a wallet's overview
-   Use keyboards to improve the interactions with the bot

&nbsp;
Feel free to contribute to this project by sending a pull request.
You can also contact me on X [@the_ecoinomist](https://x.com/the_ecoinomist) if you have any questions or suggestions.
