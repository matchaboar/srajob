from crawl4ai import BrowserConfig
import os
from dotenv import load_dotenv
from litellm import completion

# Load environment variables from .env file
load_dotenv()

browser_conf = BrowserConfig(
    browser_type="firefox",
    headless=False,
    text_mode=False,
    user_agent_mode="random"
)

MODEL_NAME = 'openrouter/@preset/free-only'
OPENROUTER_BASE_URL = 'https://openrouter.ai/api/v1'
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

tempp = 'deepseek/deepseek-chat-v3-0324:free'
temp = 'chutes/fp8'