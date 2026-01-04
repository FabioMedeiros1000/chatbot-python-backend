from langchain_core.prompts import ChatPromptTemplate

prompt = ChatPromptTemplate.from_messages([
    ("system",
    "Você é um assistente especializado em programação Python. "
    "Use o histórico da conversa para manter contexto. "
    "Responda com detalhes e exemplos de código."
    ),
    ("placeholder", "{history}"),
    ("human", "{question}")
])
