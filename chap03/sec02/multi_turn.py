from openai import OpenAI
from dotenv import load_dotenv
import os

load_dotenv(r"D:\GPT_AGENT_2025_BOOK\chap02\.env")
api_key=os.getenv("OPENAI_API_KEY")

client=OpenAI(api_key=api_key)

def get_ai_response(messages):
    response=client.chat.completions.create(
        model="gpt-4o",
        temperature=0.9,
        messages=messages,
    )
    return response.choices[0].message.content

messages=[
    {"role":"system","content":"너는 사용자를 도와주는 상담사야."},
] # 초기 시스템 메시지 설정

while True:
    user_input=input("사용자: ")

    if user_input=="exit":
        break

    messages.append({"role":"user","content":user_input})
    ai_response=get_ai_response(messages) # 대화 기록을 기반으로 AI 응답 가져오기
    messages.append({"role":"assistant","content":ai_response})
    print("AI: " + ai_response)