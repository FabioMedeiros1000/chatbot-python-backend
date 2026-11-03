from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough, RunnableWithMessageHistory

from prompt import prompt, STYLE_DEFAULT, STYLE_CONCISE
from memory import get_memory


def chat_config(llm, history_window: int, concise: bool = False):
    """Monta a chain a partir de um LLM já criado (ver app.providers.build_llm).

    history_window limita quantas mensagens do histórico vão ao modelo,
    para o custo em tokens não crescer com a conversa.
    """
    style = STYLE_CONCISE if concise else STYLE_DEFAULT

    chain_base = (
        RunnablePassthrough.assign(
            history=lambda x: x["history"][-history_window:],
            style=lambda _: style,
        )
        | prompt
        | llm
        | StrOutputParser()
    )

    return RunnableWithMessageHistory(
        chain_base,
        get_memory,
        input_messages_key="question",
        history_messages_key="history"
    )
