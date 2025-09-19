from dotenv import load_dotenv
import os
load_dotenv(r"D:\GPT_AGENT_2025_BOOK\chap02\.env")
api_key=os.getenv("OPENAI_API_KEY")

import streamlit as st

from langchain_openai import ChatOpenAI
from langchain_core.chat_history import BaseChatMessageHistory, InMemoryChatMessageHistory
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

# with st.sidebar:
#     openai_api_key=os.getenv('OPENAI_API_KEY')
 
#     # openai_api_key = st.text_input("OpenAI API Key", key="chatbot_api_key", type="password")
#     "[Get an OpenAI API key](https://platform.openai.com/account/api-keys)"
#     "[View the source code](https://github.com/streamlit/llm-examples/blob/main/Chatbot.py)"
#     "[![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/streamlit/llm-examples?quickstart=1)"

st.title("💬 Chatbot")

# (1) st.session_state에 "messages"가 없으면 초기값을 설정
if "messages" not in st.session_state:
    st.session_state["messages"] = [SystemMessage("너는 사용자의 질문에 친절히 답하는 AI 챗봇이다.")]

# 세션별 대화 기록을 저장할 딕셔너리 대신 session_state 사용
if "store" not in st.session_state:
    st.session_state["store"]={}

def get_session_history(session_id: str) -> BaseChatMessageHistory:
    if session_id not in st.session_state["store"]:
        st.session_state["store"][session_id] = InMemoryChatMessageHistory()
    return st.session_state["store"][session_id]

llm = ChatOpenAI(model="gpt-4o-mini")
with_message_history = RunnableWithMessageHistory(llm, get_session_history)

config = {"configurable": {"session_id": "abc2"}}

# 스트림릿 화면에 메시지 출력
for msg in st.session_state.messages:
    if msg:
        if isinstance(msg, SystemMessage):
            st.chat_message("system").write(msg.content)
        elif isinstance(msg, AIMessage):
            st.chat_message("assistant").write(msg.content)
        elif isinstance(msg, HumanMessage):
            st.chat_message("user").write(msg.content)

# (3) 사용자 입력을 받아 대화 기록에 추가하고 AI 응답을 생성
if prompt := st.chat_input():
    print('user:', prompt)  
    st.session_state.messages.append(HumanMessage(prompt))
    st.chat_message("user").write(prompt)

    response = with_message_history.stream([HumanMessage(prompt)], config=config)

    ai_response_bucket=None
    with st.chat_message("assistant").empty():
        for r in response:
            if ai_response_bucket is None:
                ai_response_bucket = r
            else:
                ai_response_bucket += r
            print(r.content, end='')
            st.markdown(ai_response_bucket.content)

    msg=ai_response_bucket.content
    st.session_state.messages.append(ai_response_bucket)
    print('assistant:',msg)