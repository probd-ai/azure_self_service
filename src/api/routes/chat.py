import json
import asyncio
import threading
from fastapi import APIRouter
from fastapi.responses import StreamingResponse, JSONResponse
from src.models.schemas import ChatRequest, ChatResponse
from src.agent.conversation import conversation_manager
from src.agent.agent import run_agent, stream_agent
from loguru import logger

router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    try:
        session = conversation_manager.get_or_create(request.session_id)
        reply = run_agent(session, request.message)
        return ChatResponse(reply=reply, session_id=session.session_id)
    except Exception as e:
        logger.exception(f"Unhandled error in /chat: {e}")
        return JSONResponse(status_code=500, content={"detail": "An unexpected error occurred. Please try again."})


@router.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """SSE endpoint — streams agent status events then the final reply."""
    session = conversation_manager.get_or_create(request.session_id)
    sid = session.session_id

    async def event_generator():
        yield f"data: {json.dumps({'type': 'session', 'session_id': sid})}\n\n"

        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue()

        def run_sync():
            """Runs the blocking stream_agent generator in a background thread."""
            try:
                for event in stream_agent(session, request.message):
                    loop.call_soon_threadsafe(queue.put_nowait, event)
            except Exception as e:
                logger.exception(f"Unhandled error in stream_agent thread: {e}")
                loop.call_soon_threadsafe(
                    queue.put_nowait,
                    {"type": "done", "reply": "An unexpected error occurred. Please try again."},
                )
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, None)  # sentinel

        thread = threading.Thread(target=run_sync, daemon=True)
        thread.start()

        while True:
            event = await queue.get()
            if event is None:
                break
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.delete("/sessions/{session_id}")
def delete_session(session_id: str):
    conversation_manager.delete(session_id)
    return {"deleted": session_id}

