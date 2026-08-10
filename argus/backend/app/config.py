import os

from dotenv import load_dotenv

load_dotenv()

BRIGHTDATA_API_TOKEN = os.getenv("BRIGHTDATA_API_TOKEN", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

BRIGHTDATA_COLLECTORS = {
    "amazon": os.getenv("BRIGHTDATA_COLLECTOR_AMAZON", ""),
    "flipkart": os.getenv("BRIGHTDATA_COLLECTOR_FLIPKART", ""),
    "croma": os.getenv("BRIGHTDATA_COLLECTOR_CROMA", ""),
    "demo": os.getenv("BRIGHTDATA_COLLECTOR_DEMO", ""),
}

SITE_URLS = {
    "amazon": os.getenv("SITE_URL_AMAZON", "https://www.amazon.in/"),
    "flipkart": os.getenv("SITE_URL_FLIPKART", "https://www.flipkart.com/"),
    "croma": os.getenv("SITE_URL_CROMA", "https://www.croma.com/"),
    "demo": os.getenv(
        "SITE_URL_DEMO", "https://kapilshastriwork-maker.github.io/Scrapper/"
    ),
}
