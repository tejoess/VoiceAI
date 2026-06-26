"""Knowledge document management endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Path, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.knowledge import KnowledgeDocument
from app.services.knowledge_service import detect_file_type, ingest_document, delete_document

router = APIRouter(prefix="/agents/{agent_id}/knowledge", tags=["knowledge"])


class DocumentRead(BaseModel):
    id: uuid.UUID
    agent_id: uuid.UUID
    filename: str
    file_type: str
    chunk_count: int
    status: str
    error_message: str | None

    model_config = {"from_attributes": True}


@router.post("", response_model=DocumentRead, status_code=status.HTTP_201_CREATED)
async def upload_document(
    agent_id: uuid.UUID = Path(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
) -> DocumentRead:
    """Upload a PDF, DOCX, or TXT file to the agent's knowledge base."""
    filename = file.filename or "upload"
    content_type = file.content_type or "application/octet-stream"
    file_type = detect_file_type(filename, content_type)
    if file_type is None:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Unsupported file type. Upload PDF, DOCX, or TXT files.",
        )

    data = await file.read()
    if len(data) > 50 * 1024 * 1024:  # 50 MB cap
        raise HTTPException(status_code=413, detail="File too large (max 50 MB).")

    doc = await ingest_document(db, str(agent_id), filename, file_type, data)
    return DocumentRead.model_validate(doc)


@router.get("", response_model=list[DocumentRead])
async def list_documents(
    agent_id: uuid.UUID = Path(...),
    db: AsyncSession = Depends(get_db),
) -> list[DocumentRead]:
    result = await db.execute(
        select(KnowledgeDocument)
        .where(KnowledgeDocument.agent_id == agent_id)
        .order_by(KnowledgeDocument.created_at.desc())
    )
    docs = result.scalars().all()
    return [DocumentRead.model_validate(d) for d in docs]


@router.delete("/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_doc(
    agent_id: uuid.UUID = Path(...),
    doc_id: uuid.UUID = Path(...),
    db: AsyncSession = Depends(get_db),
):
    ok = await delete_document(db, str(agent_id), str(doc_id))
    if not ok:
        raise HTTPException(status_code=404, detail="Document not found.")
