from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import require_grammar_access
from app.models.user import User
from app.schemas.grammar import GrammarCheckRequest, GrammarCheckResponse
from app.services.grammar_check import GrammarRequestError, GrammarServiceError, check_text

router = APIRouter(prefix="/grammar", tags=["grammar"])


@router.post("/check", response_model=GrammarCheckResponse)
async def check_grammar(
    body: GrammarCheckRequest,
    _user: Annotated[User, Depends(require_grammar_access)],
) -> GrammarCheckResponse:
    try:
        return await check_text(body.text)
    except GrammarRequestError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=exc.message) from exc
    except GrammarServiceError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=exc.message) from exc
