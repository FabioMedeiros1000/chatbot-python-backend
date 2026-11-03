from langchain_core.prompts import ChatPromptTemplate

prompt = ChatPromptTemplate.from_messages([
    ("system",
    "Você é um assistente especializado em programação Python. "
    "Use o histórico da conversa para manter contexto. "
    "Responda com detalhes e exemplos de código. {style}"
    ),
    ("placeholder", "{history}"),
    ("human", "{question}")
])

STYLE_DEFAULT = ""
STYLE_CONCISE = (
    "Seja objetivo: responda em até cerca de 300 palavras, "
    "com exemplos de código curtos."
)
