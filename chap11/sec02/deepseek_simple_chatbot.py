# from langchain_openai import ChatOpenAI
from langchain_ollama import ChatOllama
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

llm=ChatOllama(model="deepseek-r1:14b")

messages=[
    SystemMessage("너는 사용자의 질문에 한국어로 답변해야 한다."),
] # 초기 시스템 메시지 설정

while True:
    user_input=input("You\t: ").strip()

    if user_input in ["exit","quit","q"]:
        print("Goodbye!")
        break

    messages.append(HumanMessage(user_input))
    response = llm.stream(messages)

    ai_message=None
    for chunk in response:
        print(chunk.content, end="")
        if ai_message is None:
            ai_message=chunk
        else:
            ai_message += chunk
    print('')

    message_only=ai_message.content.split("</think>")[1].strip()
    messages.append(AIMessage(message_only))