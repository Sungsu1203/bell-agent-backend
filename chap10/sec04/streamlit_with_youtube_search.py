from dotenv import load_dotenv
import os
load_dotenv(r"D:\GPT_AGENT_2025_BOOK\chap02\.env")
api_key=os.getenv("OPENAI_API_KEY")

import streamlit as st

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage,ToolMessage

from langchain_core.tools import tool
from datetime import datetime
import pytz

from langchain_community.tools import DuckDuckGoSearchResults
from langchain_community.utilities import DuckDuckGoSearchAPIWrapper

from youtube_search import YoutubeSearch
from langchain_community.document_loaders import YoutubeLoader
from typing import List

# youtubeloader.load() 버전 호환 충돌 해결 코드
from langchain_community.document_loaders import YoutubeLoader
from youtube_transcript_api import YouTubeTranscriptApi, NoTranscriptFound, TranscriptsDisabled
from langchain_core.documents import Document
from xml.etree.ElementTree import ParseError as ETParseError
from xml.parsers.expat import ExpatError

def _yt_patched_load(self):
    # (옵션) 동영상 메타정보
    if getattr(self, "add_video_info", False):
        self._metadata.update(self._get_video_info())

    api = YouTubeTranscriptApi()  # 1.2.2: 단수형 클래스
    try:
        tlist = api.list(self.video_id)   # 핵심: list_transcripts()가 아니라 list()
    except TranscriptsDisabled:
        return []

    langs = self.language if isinstance(self.language, (list, tuple)) else [self.language]
    try:
        t = tlist.find_transcript(langs)
    except NoTranscriptFound:
        try:
            t = tlist.find_transcript(["en"])
        except NoTranscriptFound:
            return []

    if getattr(self, "translation", None):
        t = t.translate(self.translation)

    try:
        fetched = t.fetch()               # FetchedTranscript
        raw = fetched.to_raw_data()       # [{text,start,duration}, ...]
    except (ETParseError, ExpatError):
        # 유튜브가 빈/차단 응답을 줄 때 나는 오류
        return []

    fmt = getattr(self, "transcript_format", None)
    fmt_val = getattr(fmt, "value", "text")
    if fmt_val == "text":
        text = " ".join(s.get("text","").strip() for s in raw if s.get("text"))
        return [Document(page_content=text, metadata=self._metadata)]
    else:  # lines/chunks 등
        return [
            Document(
                page_content=s.get("text","").strip(),
                metadata={**self._metadata, "start": s.get("start"), "duration": s.get("duration")}
            )
            for s in raw if s.get("text")
        ]

# 패치 적용
YoutubeLoader.load = _yt_patched_load


# 모델 초기화
llm=ChatOpenAI(model="gpt-4o-mini")

# 도구 함수 정의
@tool
def get_current_time(timezone: str, location: str) -> str:
    """ 현재 시각을 반환하는 함수. """
    try:
        tz=pytz.timezone(timezone)
        now=datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")
        result = f'{timezone} ({location}) 현재 시각 {now}'
        print(result)
        return result
    except pytz.UnknownTimeZoneError:
        return f"알 수 없는 타임존: {timezone}"
    
@tool
def get_web_search(query:str, search_period:str)->str:

    """
    웹 검색을 수행하는 함수

    Args:
        query (str) : 검색어
        search_period (str) : 검색 기간 (e.g., "w" for past week, "m" for past month, "y" for past year)

    Returns:
        str: 검색 결과
    """
    wrapper=DuckDuckGoSearchAPIWrapper(region="kr-kr",time=search_period)
    
    print('-----------WEB SEARCH------------')
    print(query)
    print(search_period)

    search=DuckDuckGoSearchResults(
        api_wrapper=wrapper,
        # source="news",
        results_separator=';\n'
    )

    docs=search.invoke(query)
    return docs

@tool
def get_youtube_search(query:str)->List:

    """
    유튜브 검색을 한 뒤, 영상들의 내용을 반환하는 함수.

    Args:
        query (str) : 검색어

    Returns:
        List: 검색 결과
    """
    
    print('-----------YOUTUBE SEARCH------------')
    print(query)
    videos = YoutubeSearch(query, max_results=5).to_dict()

    for video in videos:
        video_url='https://youtube.com' + video['url_suffix']

        loader = YoutubeLoader.from_youtube_url(
            video_url,
            language=['ko','en']
        )
        video['video_url']=video_url
        video['content']=loader.load()

    return videos

# 도구 바인딩
tools=[get_current_time, get_web_search, get_youtube_search]
tool_dict = {
    "get_current_time": get_current_time,
    "get_web_search": get_web_search,
    "get_youtube_search":get_youtube_search,}

llm_with_tools=llm.bind_tools(tools)

# 사용자의 메시지를 처리하는 함수
def get_ai_response(messages):
    response = llm_with_tools.stream(messages)

    gathered=None
    for chunk in response:
        yield chunk

        if gathered is None:
            gathered=chunk
        else:
            gathered += chunk

    if gathered.tool_calls:
        st.session_state.messages.append(gathered)

        for tool_call in gathered.tool_calls:
            selected_tool=tool_dict[tool_call['name']]
            tool_msg = selected_tool.invoke(tool_call)
            print(tool_msg, type(tool_msg))
            st.session_state.messages.append(tool_msg)

        for chunk in get_ai_response(st.session_state.messages):
            yield chunk

# 스트림릿 앱
st.title("💬 GPT-4o Langchain Chat")

# 스트림릿 session_state에 메시지 저장
if "messages" not in st.session_state:
    st.session_state["messages"] = [
        SystemMessage("너는 사용자를 돕기 위해 최선을 다하는 인공지능 봇이다."),
        AIMessage("How can I help you?")
    ]

# 스트림릿 화면에 메시지 출력
for msg in st.session_state.messages:
    if msg.content:
        if isinstance(msg, SystemMessage):
            st.chat_message("system").write(msg.content)
        elif isinstance(msg, AIMessage):
            st.chat_message("assistant").write(msg.content)
        elif isinstance(msg, HumanMessage):
            st.chat_message("user").write(msg.content)
        elif isinstance(msg, ToolMessage):
            st.chat_message("tool").write(msg.content)


# 사용자 입력 처리
if prompt := st.chat_input():
    st.chat_message("user").write(prompt) # 사용자 메시지 출력
    st.session_state.messages.append(HumanMessage(prompt)) # 사용자 메시지 저장

    response = get_ai_response(st.session_state["messages"])

    result = st.chat_message("assistant").write_stream(response) # AI 메시지 출력
    st.session_state["messages"].append(AIMessage(result)) # AI 메시지 저장