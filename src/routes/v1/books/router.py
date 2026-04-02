from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from src.db.models import DBUser
from src.routes.v1.books.schema import BookCreateInput, BookDetailOutput, BookOutput, BookUpdateInput
from src.routes.v1.books.service import BookService, get_book_service
from src.routes.v1.books.summary_service import BackfillResult, SummaryService
from src.utils.auth import authenticate_user, require_admin
from src.utils.llm import LLMService, get_llm_service

router = APIRouter(prefix="/books", tags=["books"])


def _get_summary_service(llm_service: LLMService = Depends(get_llm_service)) -> SummaryService:
    return SummaryService(llm_service=llm_service)


@router.post("", response_model=BookDetailOutput, status_code=201)
async def create_book(
    book_input: BookCreateInput,
    background_tasks: BackgroundTasks,
    book_service: BookService = Depends(get_book_service),
    summary_service: SummaryService = Depends(_get_summary_service),
    current_user: DBUser = Depends(require_admin),
):
    book = await book_service.create(data=book_input)

    if book.full_text:
        background_tasks.add_task(summary_service.generate_for_book, book.id)

    return BookDetailOutput(**book.model_dump())


@router.get("", response_model=list[BookOutput])
async def list_books(
    book_service: BookService = Depends(get_book_service),
    current_user: DBUser = Depends(authenticate_user),
):
    books = await book_service.list()
    return [BookOutput(**book.model_dump()) for book in books]


# Static paths before parameterised paths to avoid FastAPI matching
# "backfill-summaries" as a {book_id} UUID parameter.


@router.post("/backfill-summaries", response_model=BackfillResult)
async def backfill_summaries(
    summary_service: SummaryService = Depends(_get_summary_service),
    current_user: DBUser = Depends(require_admin),
):
    """Generate summaries for all books that have full_text but no summary.

    Processes books concurrently with a configurable concurrency limit
    (LLM_MAX_CONCURRENT_REQUESTS).
    """
    return await summary_service.backfill()


@router.get("/{book_id}", response_model=BookDetailOutput)
async def get_book(
    book_id: UUID,
    book_service: BookService = Depends(get_book_service),
    current_user: DBUser = Depends(authenticate_user),
):
    book = await book_service.retrieve(book_id=book_id)
    return BookDetailOutput(**book.model_dump())


@router.patch("/{book_id}", response_model=BookDetailOutput)
async def update_book(
    book_id: UUID,
    update_input: BookUpdateInput,
    book_service: BookService = Depends(get_book_service),
    current_user: DBUser = Depends(require_admin),
):
    book = await book_service.update(book_id=book_id, data=update_input)
    return BookDetailOutput(**book.model_dump())


@router.delete("/{book_id}", status_code=204)
async def delete_book(
    book_id: UUID,
    book_service: BookService = Depends(get_book_service),
    current_user: DBUser = Depends(require_admin),
):
    await book_service.delete(book_id=book_id)


@router.post("/{book_id}/summarize", response_model=BookDetailOutput)
async def summarize_book(
    book_id: UUID,
    book_service: BookService = Depends(get_book_service),
    summary_service: SummaryService = Depends(_get_summary_service),
    current_user: DBUser = Depends(require_admin),
):
    """Trigger summary generation for a single book.

    Uses the request's DB session for persistence (not a background task),
    so the response includes the generated summary immediately.
    """
    book = await book_service.retrieve(book_id=book_id)

    if not book.full_text:
        raise HTTPException(status_code=400, detail="Book has no full_text to summarize")

    summary = await summary_service.generate_summary_text(book.full_text)
    book = await book_service.update(book_id=book_id, data=BookUpdateInput(summary=summary))
    return BookDetailOutput(**book.model_dump())
