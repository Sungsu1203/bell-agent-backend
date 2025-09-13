from gpt_functions import get_current_time, tools
from openai import OpenAI
from dotenv import load_dotenv
import os
import json # GPT가 JSON 형태의 문자열을 반환할 때 읽기 위한 라이브러리 임포트

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
    if tool_calls: # tool_calls가 있는 경우
        for tool_call in tool_calls:

            tool_name=tool_call.function.name   # 실행해야 한다고 판단한 함수명 받기
            tool_call_id=tool_call.id           # 함수 아이디 받기

            arguments=json.loads(tool_call.function.arguments) # 문자열을 딕셔너리로 변환

            if tool_name=="get_current_time":   # tool_name이 "get_current_time"인 경우
                messages.append({
                    "role":"function",
                    "tool_call_id":tool_call_id,
                    "name":tool_name,
                    "content":get_current_time(timezone=arguments['timezone']),
                })
        messages.append({"role":"system","content":"이제 주어진 결과를 바탕으로 답변할 차례다."})

        ai_response=get_ai_response(messages,tools=tools)
        ai_message=ai_response.choices[0].message

    messages.append(ai_message)
    print("AI\t: " + ai_message.content)