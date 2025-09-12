from gpt_functions_0 import get_current_time, tools
from openai import OpenAI
from dotenv import load_dotenv
import os

load_dotenv(r"D:\GPT_AGENT_2025_BOOK\.env")
api_key=os.getenv('OPENAI_API_KEY')
client =OpenAI(api_key=api_key)

def get_ai_response(messages,tools=None):
    response=client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        tools=tools,
    )
    return response


messages=[
    {"role":"system","content":"너는 사용자를 도와주는 상담사야."},
] # 초기 시스템 메시지 설정

while True:
    user_input=input("사용자\t: ") # 사용자 입력받기

    if user_input=="exit": # 사용자가 대화를 종료하려는지 확인
        break

    messages.append({"role":"user","content":user_input}) # 사용자 메시지를 대화 기록에 추가

    ai_response=get_ai_response(messages,tools=tools) # 대화 기록을 기반으로 AI 응답 가져오기
    ai_message=ai_response.choices[0].message
    print(ai_message)

    tool_calls=ai_message.tool_calls
    if tool_calls:
        tool_name=tool_calls[0].function.name
        tool_call_id=tool_calls[0].id

        if tool_name=="get_current_time":
            messages.append({
                "role":"function",
                "tool_call_id":tool_call_id,
                "name":tool_name,
                "content":get_current_time(),
            })

        ai_response=get_ai_response(messages,tools=tools)
        ai_message=ai_response.choices[0].message

    messages.append(ai_message)
    print("AI\t: "+ ai_message.content)