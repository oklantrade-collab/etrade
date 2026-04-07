import os
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()
key = os.getenv("GEMINI_API_KEY")

print(f"Testing key starting with: {key[:8]}...")

genai.configure(api_key=key)

try:
    # List models to see what we have access to
    print("Available models:")
    for m in genai.list_models():
        if 'generateContent' in m.supported_generation_methods:
            print(f"- {m.name}")
    
    # Try a simple generation
    model = genai.GenerativeModel('gemini-1.5-flash')
    response = model.generate_content("Say hello")
    print(f"\nResponse: {response.text}")
    print("\n✅ SUCCESS: Gemini 1.5 Flash is working!")
except Exception as e:
    print(f"\n❌ FAILED: {e}")
