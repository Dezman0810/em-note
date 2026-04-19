import uuid

from enum import Enum



from fastapi import HTTPException, status

from sqlalchemy import select

from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy.orm import selectinload



from app.models.note import Note

from app.models.share import NoteShare





class Access(str, Enum):

    none = "none"

    read = "read"

    edit = "edit"

    owner = "owner"





async def _load_note(db: AsyncSession, note_id: uuid.UUID) -> Note | None:

    result = await db.execute(

        select(Note)

        .options(selectinload(Note.tags), selectinload(Note.shares))

        .where(Note.id == note_id)

    )

    return result.scalar_one_or_none()





async def get_note_access(

    db: AsyncSession, note_id: uuid.UUID, user_id: uuid.UUID

) -> tuple[Note, Access]:

    note = await _load_note(db, note_id)

    if note is None:

        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")

    if note.deleted_at is not None:

        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")



    if note.owner_id == user_id:

        return note, Access.owner



    share_result = await db.execute(

        select(NoteShare).where(

            NoteShare.note_id == note_id,

            NoteShare.shared_with_user_id == user_id,

        )

    )

    share = share_result.scalar_one_or_none()

    if share is None:

        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")



    if share.role == "editor":

        return note, Access.edit

    return note, Access.read





async def get_note_for_read(

    db: AsyncSession, note_id: uuid.UUID, user_id: uuid.UUID

) -> tuple[Note, Access]:

    note = await _load_note(db, note_id)

    if note is None:

        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")

    if note.deleted_at is not None:

        if note.owner_id == user_id:

            return note, Access.owner

        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")



    if note.owner_id == user_id:

        return note, Access.owner



    share_result = await db.execute(

        select(NoteShare).where(

            NoteShare.note_id == note_id,

            NoteShare.shared_with_user_id == user_id,

        )

    )

    share = share_result.scalar_one_or_none()

    if share is None:

        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")



    if share.role == "editor":

        return note, Access.edit

    return note, Access.read





async def require_note_edit(

    db: AsyncSession, note_id: uuid.UUID, user_id: uuid.UUID

) -> Note:

    note, access = await get_note_access(db, note_id, user_id)

    if access not in (Access.owner, Access.edit):

        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Edit not allowed")

    return note





async def require_note_owner(

    db: AsyncSession, note_id: uuid.UUID, user_id: uuid.UUID

) -> Note:

    note, access = await get_note_access(db, note_id, user_id)

    if access != Access.owner:

        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Owner only")

    return note





async def require_trashed_note_owner(

    db: AsyncSession, note_id: uuid.UUID, user_id: uuid.UUID

) -> Note:

    note = await _load_note(db, note_id)

    if note is None:

        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")

    if note.deleted_at is None:

        raise HTTPException(

            status_code=status.HTTP_400_BAD_REQUEST, detail="Note is not in trash"

        )

    if note.owner_id != user_id:

        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Owner only")

    return note


