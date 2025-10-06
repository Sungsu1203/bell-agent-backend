from __future__ import annotations
import os
from langchain_openai import ChatOpenAI

# 단일 LLM 인스턴스(모든 에이전트가 공유)
llm = ChatOpenAI(model=os.getenv("OPENAI_MODEL", "gpt-4o"), temperature=0.3)
