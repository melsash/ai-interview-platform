import uuid

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, require_role
from app.core.database import get_db
from app.core.websocket import ws_manager
from app.schemas.assessment import (
    QuestionCreate, QuestionResponse,
    SessionCreate, SessionResponse, SessionDetailResponse, SessionStartResponse,
    SubmissionCreate, SubmissionResponse,
)
from app.services.assessment_service import QuestionService, SessionService, SubmissionService

router = APIRouter()


# ---- Questions ----

@router.post("/questions", response_model=QuestionResponse, status_code=201, tags=["questions"])
async def create_question(
    data: QuestionCreate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_role("interviewer", "admin")),
):
    """Create a new interview question. Interviewers only."""
    service = QuestionService(db)
    return await service.create(data, created_by=uuid.UUID(user["sub"]))


@router.get("/questions", response_model=list[QuestionResponse], tags=["questions"])
async def list_questions(
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """List all active questions."""
    service = QuestionService(db)
    return await service.list_active(limit=limit, offset=offset)


@router.get("/questions/{question_id}", response_model=QuestionResponse, tags=["questions"])
async def get_question(
    question_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    service = QuestionService(db)
    return await service.get_by_id(question_id)


# ---- Sessions ----

@router.post("/sessions", response_model=SessionResponse, status_code=201, tags=["sessions"])
async def create_session(
    data: SessionCreate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_role("interviewer", "admin")),
):
    """Create a new interview session. Interviewers only."""
    service = SessionService(db)
    return await service.create_session(data, interviewer_id=uuid.UUID(user["sub"]))


@router.post("/sessions/{session_id}/start", response_model=SessionStartResponse, tags=["sessions"])
async def start_session(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Start an interview session. Returns WebSocket URL for realtime updates."""
    service = SessionService(db)
    result = await service.start_session(session_id, uuid.UUID(user["sub"]))
    return result


@router.get("/sessions", response_model=list[SessionResponse], tags=["sessions"])
async def list_my_sessions(
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """List sessions for current user."""
    service = SessionService(db)
    return await service.list_my_sessions(uuid.UUID(user["sub"]))


@router.get("/sessions/{session_id}", response_model=SessionDetailResponse, tags=["sessions"])
async def get_session(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Get session details with questions."""
    service = SessionService(db)
    session = await service.get_session_detail(session_id, uuid.UUID(user["sub"]))

    questions = [sq.question for sq in session.session_questions]
    return {
        **session.__dict__,
        "questions": questions,
    }


# ---- Submissions ----

@router.post(
    "/sessions/{session_id}/questions/{session_question_id}/submit",
    response_model=SubmissionResponse,
    status_code=202,   # 202 Accepted — обработка асинхронная
    tags=["submissions"],
)
async def submit_code(
    session_id: uuid.UUID,
    session_question_id: uuid.UUID,
    data: SubmissionCreate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """
    Submit code for evaluation.
    Returns 202 Accepted immediately — evaluation happens asynchronously via AI Worker.
    Track progress via WebSocket /ws/sessions/{session_id}
    """
    service = SubmissionService(db)
    return await service.submit_code(
        session_id=session_id,
        session_question_id=session_question_id,
        data=data,
        candidate_id=uuid.UUID(user["sub"]),
    )


# ---- WebSocket ----

@router.websocket("/ws/sessions/{session_id}")
async def websocket_session(
    websocket: WebSocket,
    session_id: uuid.UUID,
):
    """
    WebSocket endpoint for realtime session updates.

    Connect here to receive:
    - submission.queued   — code submitted, waiting in queue
    - submission.evaluating — AI Worker picked up the task
    - submission.completed  — evaluation done, score + feedback available
    - session.completed     — all questions answered

    Auth via query param: ws://host/ws/sessions/{id}?token=<access_token>
    """
    token = websocket.query_params.get("token")

    # TODO: validate token via Auth Service
    # Для MVP просто принимаем соединение
    await ws_manager.connect(websocket, session_id)

    try:
        # Приветственное сообщение
        await ws_manager.send_to_connection(websocket, {
            "type": "connected",
            "data": {
                "session_id": str(session_id),
                "message": "Connected to session. Waiting for updates...",
            },
        })

        # Держим соединение открытым
        while True:
            # Принимаем пинги от клиента (keepalive)
            data = await websocket.receive_text()

    except WebSocketDisconnect:
        ws_manager.disconnect(websocket, session_id)
