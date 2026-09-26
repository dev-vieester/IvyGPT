import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ivy_gpt.config import UPLOADS_DIR
from ivy_gpt.db.crud import create_or_update_conversation
from ivy_gpt.db.models import User
from ivy_gpt.db.session import get_db
from ivy_gpt.schemas.responses import UploadResponse
from ivy_gpt.services.auth import get_current_user
from ivy_gpt.services.rag import add_document_to_rag


router = APIRouter()


@router.post(
    "/upload",
    response_model=UploadResponse,
    responses={
        400: {"model": UploadResponse},
        500: {"model": UploadResponse}
    }
)
async def upload_document(
    file: UploadFile = File(...),
    thread_id: str = Form(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    try:
        allowed_extensions = [".pdf", ".docx", ".txt", ".md", ".py", ".csv"]

        filename = file.filename or "uploaded_file"
        suffix = Path(filename).suffix.lower()

        if suffix not in allowed_extensions:
            return JSONResponse(
                UploadResponse(
                    success=False,
                    message="Unsupported file type. Upload PDF, DOCX, TXT, MD, PY, or CSV."
                ).model_dump(),
                status_code=400
            )

        file_id = str(uuid.uuid4())
        safe_filename = filename.replace(" ", "_")
        file_path = UPLOADS_DIR / f"{file_id}_{safe_filename}"

        with open(file_path, "wb") as f:
            f.write(await file.read())

        await create_or_update_conversation(db, current_user.id, thread_id, "Uploaded document")

        result = add_document_to_rag(
            file_path=str(file_path),
            thread_id=thread_id
        )

        return UploadResponse(
            success=True,
            message=f"Uploaded {result['filename']} and created {result['chunks']} chunks."
        )

    except Exception as e:
        return JSONResponse(
            UploadResponse(success=False, message=str(e)).model_dump(),
            status_code=500
        )
