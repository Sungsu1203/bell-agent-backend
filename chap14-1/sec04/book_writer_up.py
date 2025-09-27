from langgraph.graph import StateGraph, START, END
from langchain_openai import ChatOpenAI
from langchain_core.messages import AnyMessage, SystemMessage, HumanMessage, AIMessage
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers.string import StrOutputParser
from typing_extensions import TypedDict
from typing import List

from utils import save_state, get_outline, save_outline 
from models import Task
# from tools import retrieve, web_search, add_web_pages_json_to_chroma, save_chapter, next_unwritten_title
from tools_up import retrieve, web_search, add_web_pages_json_to_chroma, save_chapter, save_section, next_unwritten_title
from datetime import datetime
import os

from pathlib import Path
import re


# 현재 폴더 경로 찾기
# 랭그래프 이미지로 저장 및 추후 작업 결과 파일 저장 경로로 활용
filename = os.path.basename(__file__) # 현재 파일명 반환
absolute_path = os.path.abspath(__file__) # 현재 파일의 절대 경로 반환
current_path = os.path.dirname(absolute_path) # 현재 .py 파일이 있는 폴더 경로

DOC_MODE = os.getenv("DOC_MODE", "book")  # "book" 또는 "report" cmd에서 set DOC_MODE=report

from dotenv import load_dotenv
load_dotenv(r"D:\GPT_AGENT_2025_BOOK\chap02\.env")
api_key=os.getenv("OPENAI_API_KEY")

# 모델 초기화
llm = ChatOpenAI(model="gpt-4o") 

# 상태 정의
class State(TypedDict):
    messages: List[AnyMessage | str]
    task_history: List[Task]    
    references: dict

def supervisor(state: State): # supervisor 에이전트 추가
    print("\n\n============ SUPERVISOR ============")

    # 시스템 프롬프트 정의
    supervisor_system_prompt = PromptTemplate.from_template(
        """
        너는 AI 팀의 supervisor로서 AI 팀의 작업을 관리하고 지도한다.
        사용자가 원하는 책을 써야 한다는 최종 목표를 염두에 두고, 
        사용자의 요구를 달성하기 위해 현재 해야할 일이 무엇인지 결정한다.

        supervisor가 활용할 수 있는 agent는 다음과 같다.     
        - content_strategist: 사용자의 요구사항이 명확해졌을 때 사용한다. AI 팀의 콘텐츠 전략을 결정하고, 전체 책의 목차(outline)를 작성한다. 
        - communicator: AI 팀에서 해야 할 일을 스스로 판단할 수 없을 때 사용한다. 사용자에게 진행상황을 사용자에게 보고하고, 다음 지시를 물어본다. 
        - web_search_agent: 웹 검색을 통해 목차(outline) 작성에 필요한 정보를 확보한다.
        - vector_search_agent: 벡터 DB 검색을 통해 목차(outline) 작성에 필요한 정보를 확보한다.
        - chapter_writer: 확정된 목차를 바탕으로 특정 항목의 본문 초안을 작성한다.
        - section_writer: 보고서(Report) 모드일 때, 특정 섹션의 본문 초안을 작성한다.

        아래 내용을 고려하여, 현재 해야할 일이 무엇인지, 사용할 수 있는 agent를 단답으로 말하라.

        ------------------------------------------
        previous_outline: {outline}
        ------------------------------------------
        messages:
        {messages}
        """
    )

    # 체인 연결
    supervisor_chain = supervisor_system_prompt | llm. with_structured_output(Task)    

    # 메시지 가져오기
    messages = state.get("messages", [])		#⑤

    # inputs 설정
    inputs = {
        "messages": messages,
        "outline": get_outline(current_path)
    }

    # task 문자열로 생성
    task = supervisor_chain.invoke(inputs) 	#⑦
    task_history = state.get("task_history", [])    # 작업 이력 가져오기
    task_history.append(task)                    	# 작업 이력에 추가

   
    # 메시지 추가
    supervisor_message = AIMessage(f"[Supervisor] {task}")
    messages.append(supervisor_message)
    print(supervisor_message.content)

    # state 업데이트
    return {
        "messages": messages, 
        "task_history": task_history
    }

# supervisor's route
def supervisor_router(state: State):
    task = state['task_history'][-1]
    # 가드를 쓰신다면:
    # allowed = {"content_strategist","communicator","vector_search_agent","web_search_agent","chapter_writer"}
    # return task.agent if task.agent in allowed else "communicator"
    return task.agent			

# 목차를 작성하는 노드(agent)
def content_strategist(state: State):
    print("\n\n============ CONTENT STRATEGIST ============")

    # 시스템 프롬프트 정의
    if DOC_MODE == "report":
        content_strategist_system_prompt = PromptTemplate.from_template(
            """
            너는 **보고서 기획자**다. 이전 대화와 참고자료를 바탕으로
            **실무 보고서 개요**를 작성하라.

            권장 구조(필요 시 조정):
            1. Executive Summary
            2. Background & Objectives
            3. Scope & Methodology
            4. Key Findings (데이터/사례 중심)
            5. Analysis & Insights
            6. Recommendations (Action Items)
            7. Risks & Mitigations
            8. Implementation Plan & Timeline
            9. Appendix (Data, Glossary, References)

            --------------------------------
            - 이전 대화: {messages}
            - 기존 개요: {outline}
            - 참고 자료: {references}
            """
        )
    else:
        # (기존 책 목차용 프롬프트 유지)
        content_strategist_system_prompt = PromptTemplate.from_template(
            """
            너는 책을 쓰는 AI팀의 콘텐츠 전략가(Content Strategist)로서,
            이전 대화 내용을 바탕으로 사용자의 요구사항을 분석하고, AI팀이 쓸 책의 세부 목차를 결정한다.

            지난 목차가 있다면 그 버전을 사용자의 요구에 맞게 수정하고, 없다면 새로운 목차를 제안한다.
            목차를 작성하는데 필요한 정보는 "참고 자료"에 있으므로 활용한다. 

            --------------------------------
            - 지난 목차: {outline}
            --------------------------------
            - 이전 대화 내용: {messages}
            --------------------------------
            - 참고 자료: {references}
            """
        )

    # 시스템 프롬프트와 모델을 연결
    content_strategist_chain = content_strategist_system_prompt | llm | StrOutputParser()

    messages = state["messages"]        # 상태에서 메시지를 가져옴
    # outline = get_outline(current_path) # 저장된 목차를 가져옴
    
    outline_path = os.path.join(current_path, "outline.md")  # 혹은 실제 저장 파일 이름
    if os.path.exists(outline_path):
        outline = get_outline(current_path)
    else:
        outline = ""   # 파일이 없으면 그냥 빈 목차로 시작



    # 입력값 정의
    inputs = {
        "messages": messages,
        "outline": outline, 
        "references": state.get("references", {"queries": [], "docs": []})
    }

    # 목차 작성
    gathered = ''
    for chunk in content_strategist_chain.stream(inputs):
        gathered += chunk
        print(chunk, end='')

    print()

    save_outline(current_path, gathered) # 목차 저장

    # 메시지 추가    
    content_strategist_message = f"[Content Strategist] 목차 작성 완료"
    print(content_strategist_message)
    messages.append(AIMessage(content_strategist_message))

    task_history = state.get("task_history", []) # task_history 가져오기
    # 최근 task 작업완료(done) 처리하기
    if task_history[-1].agent != "content_strategist": 
        raise ValueError(f"Content Strategist가 아닌 agent가 목차 작성을 시도하고 있습니다.\n {task_history[-1]}")
    
    task_history[-1].done = True
    task_history[-1].done_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # 다음 작업이 communicator로 사용자와 대화하는 것이므로 새 작업 추가 
    new_task = Task(
        agent="communicator",
        done=False,
        description="AI팀의 진행상황을 사용자에게 보고하고, 사용자의 의견을 파악하기 위한 대화를 나눈다",
        done_at=""
    )
    task_history.append(new_task)

    print(new_task)

    # 현재 state를 업데이트한다. 
    return {
        "messages": messages,
        "task_history": task_history
    }


def web_search_agent(state: State): #① (0)
    print("\n\n============ WEB SEARCH AGENT ============")

    # 작업 리스트 가져와서 web search agent 가 할 일인지 확인하기
    tasks = state.get("task_history", [])
    task = tasks[-1]

    if task.agent != "web_search_agent":
        raise ValueError(f"Web Search Agent가 아닌 agent가 Web Search Agent를 시도하고 있습니다.\n {task}")
    
    #③ 시스템 프롬프트 정의
    web_search_system_prompt = PromptTemplate.from_template(
        """
        너는 다른 AI Agent 들이 수행한 작업을 바탕으로, 
        목차(outline) 작성에 필요한 정보를 웹 검색을 통해 찾아내는 Web Search Agent이다.

        현재 부족한 정보를 검색하고, 복합적인 질문은 나눠서 검색하라.

        - 검색 목적: {mission}
        --------------------------------
        - 과거 검색 내용: {references}
        --------------------------------
        - 이전 대화 내용: {messages}
        --------------------------------
        - 목차(outline): {outline}
        --------------------------------
        - 현재 시각 : {current_time}
        """
    )
    
    #④ 기존 대화 내용 가져오기
    messages = state.get("messages", [])

    #⑤ 인풋 자료 준비하기
    inputs = {
        "mission": task.description,
        "references": state.get("references", {"queries": [], "docs": []}),
        "messages": messages,
        "outline": get_outline(current_path),
        "current_time": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }

    #⑥ LLM과 웹 검색 모델 연결
    llm_with_web_search = llm.bind_tools([web_search])

    #⑦ 시스템 프롬프트와 모델을 연결
    web_search_chain = web_search_system_prompt | llm_with_web_search

    #⑧ 웹 검색 tool_calls 가져오기
    search_plans = web_search_chain.invoke(inputs)

    #⑨ 어떤 내용을 검색했는지 담아두기
    queries = []

    #⑩ 검색 계획(tool_calls)에 따라 검색하기
    for tool_call in search_plans.tool_calls:
        print('-------- web search --------', tool_call)
        args = tool_call["args"]
        
        queries.append(args["query"])

        # (10)  검색 결과를 chroma에 추가
        _, json_path = web_search.invoke(args)
        print('json_path:', json_path)

        # (10)  JSON 파일을 chroma에 추가
        add_web_pages_json_to_chroma(json_path)

    #⑪ (11) task 완료
    tasks[-1].done = True
    tasks[-1].done_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    #⑪ (11) 새로운 task 추가
    task_desc = "AI팀이 쓸 책의 세부 목차를 결정하기 위한 정보를 벡터 검색을 통해 찾아낸다."
    task_desc += f" 다음 항목이 새로 추가되었다\n: {queries}"
    
    new_task = Task(
        agent="vector_search_agent",
        done=False,
        description=task_desc,
        done_at=""
    )

    tasks.append(new_task)

    #⑫ (12) 작업 후기 메시지
    msg_str = f"[WEB SEARCH AGENT] 다음 질문에 대한 검색 완료: {queries}"
    messages.append(AIMessage(msg_str))

    #⑬ (13) state 업데이트
    return {
        "messages": messages,
        "task_history": tasks
    }

def vector_search_agent(state: State):
    print("\n\n============ VECTOR SEARCH AGENT ============")
    
    tasks = state.get("task_history", [])
    task = tasks[-1]
    if task.agent != "vector_search_agent":
        raise ValueError(f"Vector Search Agent가 아닌 agent가 Vector Search Agent를 시도하고 있습니다.\n {task}")

    vector_search_system_prompt = PromptTemplate.from_template(
        """
        너는 다른 AI Agent 들이 수행한 작업을 바탕으로, 
        목차(outline) 작성에 필요한 정보를 벡터 검색을 통해 찾아내는 Agent이다.

        현재 목차(outline)을 작성하는데 필요한 정보를 확보하기 위해, 
        다음 내용을 활용해 적절한 벡터 검색을 수행하라. 

        - 검색 목적: {mission}
        --------------------------------
        - 과거 검색 내용: {references}
        --------------------------------
        - 이전 대화 내용: {messages}
        --------------------------------
        - 목차(outline): {outline}
        """
    )

    # inputs 설정
    mission = task.description
    references = state.get("references", {"queries": [], "docs": []})
    messages = state["messages"]
    outline = get_outline(current_path)

    inputs = {
        "mission": mission,
        "references": references,
        "messages": messages,
        "outline": outline
    }

    # LLM과 벡터 검색 모델 연결
    llm_with_retriever = llm.bind_tools([retrieve]) 
    vector_search_chain = vector_search_system_prompt | llm_with_retriever

    # LLM과 벡터 검색 모델 연결
    search_plans = vector_search_chain.invoke(inputs)
    # 검색할 내용 출력
    for tool_call in search_plans.tool_calls:
        print('-----------------------------------', tool_call)
        args = tool_call["args"]
       
        query = args["query"] 
        retrieved_docs = retrieve.invoke(args)
		#① (1) 결과 담아 두기
        references["queries"].append(query) 
        references["docs"] += retrieved_docs
    
    unique_docs = []
    unique_page_contents = set()

    for doc in references["docs"]:
        if doc.page_content not in unique_page_contents:
            unique_docs.append(doc)
            unique_page_contents.add(doc.page_content)
    references["docs"] = unique_docs

    # 검색 결과 출력 – 쿼리 출력
    print('Queries:--------------------------')
    queries = references["queries"]
    for query in queries:
        print(query)
    
    # 검색 결과 출력 – 문서 청크 출력
    print('References:--------------------------')
    for doc in references["docs"]:
        print(doc.page_content[:100])
        print('--------------------------')

    # task 완료
    tasks[-1].done = True
    tasks[-1].done_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # 새로운 task 추가
    new_task = Task(
        agent="communicator",
        done=False,
        description="AI팀의 진행상황을 사용자에게 보고하고, 사용자의 의견을 파악하기 위한 대화를 나눈다",
        done_at=""
    )
    tasks.append(new_task)

    # 1) 현재 타깃 섹션을 고름: 사용자 요구에서 추출 or 아웃라인에서 자동 선택
    from tools import next_unwritten_title  # 헬퍼 이미 추가하셨죠!
    outline_text = get_outline(current_path)
    target_title = next_unwritten_title(outline_text) or "Executive Summary" # Report면 적절히 기본값. 기본: 아직 안 쓴 첫 항목(H2 우선)

    # 2) Communicator 대신 바로 집필 태스크도 붙이기
    tasks.append(Task(
        agent="section_writer", # 보고서 모드면 section_writer, 책이면 chapter_writer
        done=False,
        description=f"write: {target_title}",
        done_at=""
    ))

    # (원한다면 communicator 태스크도 이어서 추가)
    tasks.append(Task(
        agent="communicator",
        done=False,
        description=f"'{target_title}' 초안 작성이 완료되면 사용자에게 보고하고 다음 대상을 물어본다.",
        done_at=""
    ))

    # vector search agent의 작업후기를 메시지로 생성
    msg_str = f"[VECTOR SEARCH AGENT] 다음 질문에 대한 검색 완료: {queries}"
    message = AIMessage(msg_str)
    print(msg_str)

    messages.append(message)
    # state 업데이트
    # vector_search_agent(state) 내부, 마지막 반환 직전

    return {
        "messages": messages,
        "task_history": tasks,
        "references": references
    }

def chapter_writer(state: State):
    print("\n\n============ CHAPTER WRITER ============")

    # 최근 작업이 chapter_writer인지 확인
    tasks = state.get("task_history", [])
    if not tasks:
        raise ValueError("작업 이력이 없습니다.")
    task = tasks[-1]
    if task.agent != "chapter_writer":
        raise ValueError(f"chapter_writer가 아닌 agent가 chapter_writer를 시도하고 있습니다.\n {task}")

    messages = state.get("messages", [])
    outline_text = get_outline(current_path)
    if not outline_text or outline_text.strip() == "":
        raise ValueError("아웃라인이 비어 있습니다. 먼저 content_strategist로 아웃라인을 생성/확정하세요.")

    # 1) 집필 대상 제목 결정
    # - Task.description에 'write: 섹션제목'이 있으면 우선 사용
    # - 없으면 아직 작성되지 않은 첫 항목 자동 선택(## 우선, 없으면 #)
    target_title = None
    m = re.search(r"write[:：]\s*(.+)", task.description or "", flags=re.IGNORECASE)
    if m:
        target_title = m.group(1).strip()
    if not target_title:
        target_title = next_unwritten_title(outline_text)

    if not target_title:
        # 모두 작성 완료
        messages.append(AIMessage("[Chapter Writer] 모든 목차 항목의 초안이 이미 작성되었습니다."))
        tasks[-1].done = True
        tasks[-1].done_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        tasks.append(Task(
            agent="communicator",
            done=False,
            description="집필 진행이 완료되었음을 사용자에게 보고하고, 편집/다듬기 단계로 넘어갈지 물어본다.",
            done_at=""
        ))
        return {"messages": messages, "task_history": tasks}

    print(f"👉 Target chapter: {target_title}")

    # 2) 집필 프롬프트
    chapter_writer_prompt = PromptTemplate.from_template(
        """
        너는 전문 기술서 집필 에이전트다.
        아래 '확정된 목차'와 '대화 문맥', '참고 자료', 그리고 '[RAG Retrieved]' 섹션의 스니펫을 우선적으로 참고하여, 지정된 항목의 본문 초안을 작성하라.

        요구사항:
        - 대상 독자는 "실무 초·중급" 개발자라고 가정한다.
        - 예제/절차는 단계별 번호로 정리한다.
        - 코드/명령어/파일경로는 fenced code block을 사용한다.
        - 한 섹션 분량: 1,200~2,000자 내외.
        - 마지막에 "핵심 요약" 불릿을 넣는다.

        [작성 대상 섹션 제목]
        {target_title}

        --------------------------------
        [확정된 목차]
        {outline}
        --------------------------------
        [참고 자료 요약]
        {references}
        --------------------------------
        [이전 대화]
        {messages}
        """
    )

    # 참고자료 간단 요약(너무 길면 LLM에 부담)
    references = state.get("references", {"queries": [], "docs": []})
    ref_queries = references.get("queries", [])[:5]
    ref_docs = references.get("docs", [])[:5]

    ref_preview = []
    for d in ref_docs:
        meta = getattr(d, "metadata", {}) or {}
        src = meta.get("source") or meta.get("url") or "unknown"
        snippet = (d.page_content or "")[:300].replace("\n", " ")
        ref_preview.append(f"- {src}: {snippet}")

    ref_text = "Queries:\n" + "\n".join([f"- {q}" for q in ref_queries]) \
             + "\n\nDocs:\n" + "\n".join(ref_preview)
    
    # book_writer.py > chapter_writer(state) 함수 안, inputs 구성 직전에
    from tools import retrieve

    # 1) 섹션 타깃 기반 쿼리 구성
    queries = [
        f"{target_title} 개념 정리 입문",
        "AI 정의와 역사 초보자용 요약",
        "머신러닝 딥러닝 차이 핵심",
        "NLP 컴퓨터 비전 입문 사례",
    ]

    rag_docs = []
    for q in queries:
        try:
            # 경고 없이 호출하려면 invoke 사용
            docs = retrieve.invoke({"query": q, "top_k": 4})
            rag_docs.extend(docs)
        except Exception:
            pass

    # 2) 중복 제거(간단)
    seen = set(); unique_docs = []
    for d in rag_docs:
        key = (getattr(d, "page_content", "")[:200], (getattr(d, "metadata", {}) or {}).get("source"))
        if key in seen: 
            continue
        seen.add(key); unique_docs.append(d)
    rag_docs = unique_docs[:12]   # 과도한 프롬프트 길이 방지

    # 3) 프롬프트에 들어갈 RAG 요약 문자열 생성
    rag_preview = []
    for d in rag_docs:
        meta = getattr(d, "metadata", {}) or {}
        src = meta.get("source") or meta.get("url") or "unknown"
        snippet = (d.page_content or "").replace("\n", " ")[:350]
        rag_preview.append(f"- {src}: {snippet}")
    rag_text = "\n".join(rag_preview)

    # 4) 기존 references 요약(ref_text)에 RAG 결과를 합치기
    ref_text = ref_text + ("\n\n[RAG Retrieved]\n" + rag_text if rag_text else "")

    inputs = {
        "target_title": target_title,
        "outline": outline_text,
        "references": ref_text,
        "messages": messages,
    }

    # 3) 집필 실행 (스트리밍)
    writer_chain = chapter_writer_prompt | llm | StrOutputParser()
    gathered = ''
    print("\nAI\t: ", end='')
    for chunk in writer_chain.stream(inputs):
        print(chunk, end='')
        gathered += chunk
    print()

    # 4) 파일 저장 (tools.save_chapter 사용)
    out_path = save_chapter(target_title, gathered)
    messages.append(AIMessage(f"[Chapter Writer] '{target_title}' 초안 작성 완료 → {out_path}"))

    # 5) 태스크 처리 및 다음 단계(커뮤니케이터) 연결
    tasks[-1].done = True
    tasks[-1].done_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    tasks.append(Task(
        agent="communicator",
        done=False,
        description=f"'{target_title}' 초안 작성이 완료되었음을 사용자에게 보고하고, 다음 집필 대상(또는 수정/분량조정)을 물어본다.",
        done_at=""
    ))

    return {
        "messages": messages,
        "task_history": tasks
    }

def section_writer(state: State):
    print("\n\n============ SECTION WRITER ============")

    tasks = state.get("task_history", [])
    if not tasks:
        raise ValueError("작업 이력이 없습니다.")

    # ✅ 최근 '미완료 section_writer' 태스크를 뒤에서부터 탐색
    pending = next(
        (t for t in reversed(tasks) if (not t.done) and t.agent == "section_writer"),
        None
    )
    if pending is None:
        print("[WARN] pending 'section_writer' task가 없습니다. edge 트리거로 진행합니다.")
        desc_for_parse = ""
    else:
        desc_for_parse = pending.description or ""

    messages = state.get("messages", [])
    outline_text = get_outline(current_path)
    if not outline_text or outline_text.strip() == "":
        raise ValueError("আ웃라인이 비어 있습니다. 먼저 보고서 개요(목차)를 만드세요.")

    # 1) 집필 타깃
    target_title = None
    m = re.search(r"write[:：]\s*(.+)", desc_for_parse, flags=re.IGNORECASE)
    if m:
        target_title = m.group(1).strip()
    if not target_title:
        target_title = next_unwritten_title(outline_text)
    if not target_title:
        messages.append(AIMessage("[Section Writer] 모든 섹션 초안이 이미 작성되었습니다."))
        # pending이 있으면 그 태스크만 완료 처리
        if pending:
            pending.done = True
            pending.done_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        # 다음 대화 예약
        tasks.append(Task(
            agent="communicator",
            done=False,
            description="집필 진행 완료를 사용자에게 보고하고, 편집/수정 단계로 넘어갈지 물어본다.",
            done_at=""
        ))
        return {"messages": messages, "task_history": tasks}

    print(f"👉 Target section: {target_title}")

    # 2) 프롬프트(보고서 톤/형식)
    report_writer_prompt = PromptTemplate.from_template(
        """
        너는 기업/연구용 **보고서** 집필 에이전트다.
        아래 개요(목차), 대화 기록, 참고 자료 요약을 바탕으로
        지정된 섹션의 **실무 보고서 스타일** 초안을 작성하라.

        작성 규칙:
        - 대상 독자: 의사결정자 및 실무자
        - 구성: 배경/핵심 요점/근거(데이터·사례)/시사점
        - 표나 목록은 Markdown으로 간결히 표현
        - 길이: 800~1,500 단어 내외(요약 섹션은 400~800)
        - 마지막에 **Actionable Recommendations** 3~5개 불릿
        - 참고자료 내용 인용 시 과장 없이 재서술하고 출처명을 대괄호로 표기(예: [IBM], [Stanford HAI])

        [작성 대상 섹션 제목]
        {target_title}

        --------------------------------
        [보고서 개요(목차)]
        {outline}
        --------------------------------
        [참고 자료 요약]
        {references}
        --------------------------------
        [이전 대화]
        {messages}
        """
    )

    # 3) 참고자료 요약(기존 references를 요약해 주입)
    references = state.get("references", {"queries": [], "docs": []})
    ref_queries = references.get("queries", [])[:5]
    ref_docs = references.get("docs", [])[:8]
    ref_preview = []
    for d in ref_docs:
        meta = getattr(d, "metadata", {}) or {}
        src = meta.get("source") or meta.get("url") or "unknown"
        snippet = (d.page_content or "")[:350].replace("\n", " ")
        ref_preview.append(f"- [{src}] {snippet}")
    ref_text = "Queries:\n" + "\n".join([f"- {q}" for q in ref_queries]) + "\n\nDocs:\n" + "\n".join(ref_preview)

    inputs = {
        "target_title": target_title,
        "outline": outline_text,
        "references": ref_text,
        "messages": messages,
    }

    # 4) 집필(스트리밍)
    chain = report_writer_prompt | llm | StrOutputParser()
    gathered = ''
    print("\nAI\t: ", end='')
    for chunk in chain.stream(inputs):
        print(chunk, end='')
        gathered += chunk
    print()

    # 5) 파일 저장 (sections/ 폴더)
    out_path = save_section(target_title, gathered, mode="report" if DOC_MODE == "report" else "book")
    messages.append(AIMessage(f"[Section Writer] '{target_title}' 초안 작성 완료 → {out_path}"))

    # 6) 태스크 상태 & 다음 단계
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    if pending:
        pending.done = True
        pending.done_at = now
    else:
        # 기록 유지용(선택): pending이 없었지만 실제 집필이 수행됐음을 남김
        tasks.append(Task(
            agent="section_writer",
            done=True,
            description=f"write: {target_title}",
            done_at=now
        ))

    tasks.append(Task(
        agent="communicator",
        done=False,
        description=f"'{target_title}' 초안 작성 완료를 사용자에게 보고하고, 다음 섹션/수정 범위를 물어본다.",
        done_at=""
    ))

    return {"messages": messages, "task_history": tasks}



# 사용자와 대화할 노드(agent): communicator
def communicator(state: State):
    print("\n\n============ COMMUNICATOR ============")

    # 시스템 프롬프트 정의
    communicator_system_prompt = PromptTemplate.from_template(
        """
        너는 책을 쓰는 AI팀의 커뮤니케이터로서, 
        AI팀의 진행상황을 사용자에게 보고하고, 사용자의 의견을 파악하기 위한 대화를 나눈다. 

        사용자도 outline(목차)을 이미 보고 있으므로, 다시 출력할 필요는 없다.
        outline: {outline} 
        --------------------------------
        messages: {messages}
        """
    )

    #② 시스템 프롬프트와 모델을 연결
    system_chain = communicator_system_prompt | llm

    # 상태에서 메시지를 가져옴
    messages = state["messages"]

    # 입력값 정의
    inputs = {
        "messages": messages,
        "outline": get_outline(current_path)
    }

    # 스트림되는 메시지를 출력하면서, gathered에 모으기
    gathered = None

    print('\nAI\t: ', end='')
    for chunk in system_chain.stream(inputs):
        print(chunk.content, end='')

        if gathered is None:
            gathered = chunk
        else:
            gathered += chunk

    messages.append(gathered)

    task_history = state.get("task_history", []) 
    if task_history[-1].agent != "communicator":
        raise ValueError(f"Communicator가 아닌 agent가 대화를 시도하고 있습니다.\n {task_history[-1]}")
    
    task_history[-1].done = True
    task_history[-1].done_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    return {
        "messages": messages,
        "task_history": task_history
    }


# 상태 그래프 정의
graph_builder = StateGraph(State)

# Nodes
graph_builder.add_node("supervisor", supervisor)     
graph_builder.add_node("communicator", communicator)
graph_builder.add_node("content_strategist", content_strategist)
graph_builder.add_node("vector_search_agent", vector_search_agent)
graph_builder.add_node("web_search_agent", web_search_agent)
# Nodes (기존 노드들과 함께)
graph_builder.add_node("chapter_writer", chapter_writer)
# Node
graph_builder.add_node("section_writer", section_writer)


# Edges
graph_builder.add_edge(START, "supervisor")
graph_builder.add_conditional_edges(
    "supervisor", 
    supervisor_router,
    {
        "content_strategist": "content_strategist",
        "communicator": "communicator",
        "vector_search_agent": "vector_search_agent", 
        "web_search_agent": "web_search_agent",
        "chapter_writer": "chapter_writer",
        "section_writer": "section_writer"
    }
)
graph_builder.add_edge("content_strategist", "communicator")
graph_builder.add_edge("web_search_agent", "vector_search_agent") #③
graph_builder.add_edge("vector_search_agent", "chapter_writer")    # 추가!
graph_builder.add_edge("vector_search_agent", "section_writer")    # 추가!
graph_builder.add_edge("vector_search_agent", "communicator")
# Edges (chapter_writer → communicator)
graph_builder.add_edge("chapter_writer", "communicator")
# Edge
graph_builder.add_edge("section_writer", "communicator")
graph_builder.add_edge("communicator", END)

graph = graph_builder.compile()

# graph.get_graph().draw_mermaid_png(output_file_path=absolute_path.replace('.py', '.png'))

from playwright.sync_api import sync_playwright
from string import Template
import os

HTML_TMPL = Template("""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<script src="https://cdn.jsdelivr.net/npm/mermaid/dist/mermaid.min.js"></script>
<script>mermaid.initialize({ startOnLoad: true, theme: 'default' });</script>
<style> body{margin:0;padding:16px;} </style>
</head>
<body><div class="mermaid">$mmd</div></body></html>
""")

def render_mermaid_with_playwright(mmd: str, out_path: str, width: int = 1600, height: int = 1000):
    html = HTML_TMPL.substitute(mmd=mmd)  # ← 중괄호 그대로, $mmd만 치환
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": width, "height": height})
        page.set_content(html, wait_until="networkidle")
        page.wait_for_timeout(300)
        page.locator(".mermaid").screenshot(path=out_path)
        browser.close()
    return out_path

# 호출부
mmd = graph.get_graph().draw_mermaid()
out_png = absolute_path.replace(".py", ".png")
render_mermaid_with_playwright(mmd, out_png)
print("Saved:", out_png)


# 상태 초기화
state = State(
    messages = [
        SystemMessage(
            f"""
        너희 AI들은 사용자의 요구에 맞는 책을 쓰는 작가팀이다.
        사용자가 사용하는 언어로 대화하라.

        현재시각은 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}이다.

        """
        )
    ],
    task_history=[]
)

while True:
    user_input = input("\nUser\t: ").strip()

    if user_input.lower() in ['exit', 'quit', 'q']:
        print("Goodbye!")
        break
    
    state["messages"].append(HumanMessage(user_input))
    state = graph.invoke(state)

    print('\n------------------------------------ MESSAGE COUNT\t', len(state["messages"]))

    save_state(current_path, state) # 현재 state 내용 저장