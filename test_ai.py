from openai import OpenAI
from datetime import datetime
import json



while True:
    fråga = input("Du: ")
    
    historik.append({"role": "user", "content": fråga})
    
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=historik
    )
    
    svar = response.choices[0].message.content
    historik.append({"role": "assistant", "content": svar})
    
    print(f"AI: {svar}\n")
    print(f"Historik: {historik}\n")