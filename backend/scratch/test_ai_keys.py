import asyncio
import os
from dotenv import load_dotenv
import google.generativeai as genai
from openai import OpenAI

load_dotenv()

async def test_gemini():
    print("\n--- Testing Gemini ---")
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        print("GEMINI_API_KEY not found in .env")
        return
    try:
        genai.configure(api_key=key)
        model = genai.GenerativeModel('gemini-1.5-flash-latest')
        response = model.generate_content("Responde 'OK' si recibes este mensaje.")
        print(f"Gemini Response: {response.text}")
    except Exception as e:
        print(f"Gemini Error: {e}")

async def test_qwen():
    print("\n--- Testing QWEN ---")
    key = os.getenv("QWEN_API_KEY")
    if not key:
        print("QWEN_API_KEY not found in .env")
        return
    try:
        client = OpenAI(
            api_key=key,
            base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
        )
        response = client.chat.completions.create(
            model="qwen-plus",
            messages=[{"role": "user", "content": "Responde 'OK' si recibes este mensaje."}]
        )
        print(f"QWEN Response: {response.choices[0].message.content}")
    except Exception as e:
        print(f"QWEN Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_gemini())
    asyncio.run(test_qwen())
