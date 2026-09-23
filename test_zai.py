# test_zai.py
import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv(".env")

client = OpenAI(
    api_key=os.getenv("LLM_API_KEY"),
    base_url=os.getenv("LLM_BASE_URL"),
)

response = client.chat.completions.create(
    model=os.getenv("LLM_MODEL"),
    messages=[{"role": "user", "content": "Responde solo: ok"}],
)

print("Respuesta del modelo:", response.choices[0].message.content)