from langchain_openai import ChatOpenAI
from langchain_groq import ChatGroq
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnableWithMessageHistory

from app.schemas import ModelProvider
from prompt import prompt
from memory import get_memory

def chat_config(api_key: str, model_provider: ModelProvider):
    if model_provider == ModelProvider.chatgpt:
        llm = ChatOpenAI(
                model="gpt-4o-mini",
                temperature=0.3,
                openai_api_key=api_key
            )
    elif model_provider == ModelProvider.groq:
        llm = ChatGroq(
            model="llama-3.1-8b-instant",
            temperature=0.3,
            groq_api_key=api_key
        )
    else:
        raise ValueError("Model provider não suportado")

    chain_base = prompt | llm | StrOutputParser()

    chatbot = RunnableWithMessageHistory(
        chain_base,
        get_memory,
        input_messages_key="question",
        history_messages_key="history"
    )

    return chatbot