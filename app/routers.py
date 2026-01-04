from fastapi import APIRouter, HTTPException, Header
from typing import Optional
from fastapi import Query

from app.schemas import ChatbotRequest, ChatbotResponse
from database import connection
from app.repositories import MessageRepository
from app.services import ChatbotService

router = APIRouter(prefix="/api")
message_repository = MessageRepository(connection)
chatbot_service = ChatbotService(message_repository)

@router.post("/chatbot", response_model=ChatbotResponse)
async def chatbot(payload: ChatbotRequest, authorization: str = Header(None)):
    if not payload.question:
        raise HTTPException(status_code=400, detail="O parâmetro question é obrigatório")

    if not authorization:
        raise HTTPException(status_code=401, detail="Header Authorization é obrigatório")
    
    api_key = authorization.replace("Bearer ", "").strip()
    
    response = await chatbot_service.get_response(payload, api_key)
    return response

@router.get("/history/{session_id}", response_model=list[ChatbotResponse])
async def history(
    session_id: str,
    limit: int = Query(20, le=50),
    before_id: Optional[int] = Query(None)
):
    return await chatbot_service.get_history(
        session_id=session_id,
        limit=limit,
        before_id=before_id
    )

@router.delete("/history/{session_id}", response_model=str)
async def delete_history(
    session_id: str
):
    return await chatbot_service.delete_history(
        session_id=session_id
    )