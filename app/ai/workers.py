from dotenv import load_dotenv
from groq import Groq

from datetime import date

current_year = date.today().year

load_dotenv()

client = Groq()
