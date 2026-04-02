from uuid import UUID

from fastapi import APIRouter, Depends
from src.db.models import DBUser
from src.routes.v1.authors.schema import AuthorCreateInput, AuthorOutput, AuthorUpdateInput
from src.routes.v1.authors.service import AuthorService, get_author_service
from src.utils.auth import authenticate_user, require_admin

router = APIRouter(prefix="/authors", tags=["authors"])


@router.post("", response_model=AuthorOutput, status_code=201)
async def create_author(
    author_input: AuthorCreateInput,
    author_service: AuthorService = Depends(get_author_service),
    current_user: DBUser = Depends(require_admin),
):
    author = await author_service.create(data=author_input)
    return AuthorOutput(**author.model_dump())


@router.get("", response_model=list[AuthorOutput])
async def list_authors(
    author_service: AuthorService = Depends(get_author_service),
    current_user: DBUser = Depends(authenticate_user),
):
    authors = await author_service.list()
    return [AuthorOutput(**author.model_dump()) for author in authors]


@router.get("/{author_id}", response_model=AuthorOutput)
async def get_author(
    author_id: UUID,
    author_service: AuthorService = Depends(get_author_service),
    current_user: DBUser = Depends(authenticate_user),
):
    author = await author_service.retrieve(author_id=author_id)
    return AuthorOutput(**author.model_dump())


@router.patch("/{author_id}", response_model=AuthorOutput)
async def update_author(
    author_id: UUID,
    update_input: AuthorUpdateInput,
    author_service: AuthorService = Depends(get_author_service),
    current_user: DBUser = Depends(require_admin),
):
    author = await author_service.update(author_id=author_id, data=update_input)
    return AuthorOutput(**author.model_dump())


@router.delete("/{author_id}", status_code=204)
async def delete_author(
    author_id: UUID,
    author_service: AuthorService = Depends(get_author_service),
    current_user: DBUser = Depends(require_admin),
):
    await author_service.delete(author_id=author_id)
