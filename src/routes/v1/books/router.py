import logging
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query

from src.db.models import DBUser
from src.routes.v1.books.schema import BookCreateInput, BookDetailOutput, BookOutput, BookUpdateInput, SearchResultOutput
from src.routes.v1.books.service import BookService, get_book_service
from src.routes.v1.books.summary_service import BackfillResult, SummaryService
from src.utils.auth import authenticate_user, require_admin
from src.utils.llm import LLMService, get_llm_service

logger = logging.getLogger(__name__)

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
        # Background: generate summary, then embedding (chained)
        background_tasks.add_task(summary_service.generate_for_book, book.id)
    else:
        # No full_text — generate embedding from title + description.
        # Non-critical: if embedding fails, book is still created and
        # can be embedded later via backfill.
        try:
            embedding = await summary_service.generate_embedding_for_text(
                title=book.title, description=book.description, summary=None,
            )
            await book_service.update(book_id=book.id, data=BookUpdateInput(embedding=embedding))
        except Exception:
            logger.warning("Embedding generation failed for book %s, will retry via backfill", book.id)

    return BookDetailOutput(**book.model_dump())


@router.get("", response_model=list[BookOutput])
async def list_books(
    book_service: BookService = Depends(get_book_service),
    current_user: DBUser = Depends(authenticate_user),
):
    books = await book_service.list()
    return [BookOutput(**book.model_dump()) for book in books]


# Static paths before parameterised paths to avoid FastAPI matching
# "backfill-summaries" or "search" as a {book_id} UUID parameter.


@router.post("/backfill-summaries", response_model=BackfillResult)
async def backfill_summaries(
    summary_service: SummaryService = Depends(_get_summary_service),
    current_user: DBUser = Depends(require_admin),
):
    """Generate summaries and embeddings for all books that have full_text
    but no summary. Processes concurrently with configurable limit."""
    return await summary_service.backfill()


@router.get("/search", response_model=list[SearchResultOutput])
async def search_books(
    q: str,
    limit: int = Query(default=10, ge=1, le=100),
    book_service: BookService = Depends(get_book_service),
    summary_service: SummaryService = Depends(_get_summary_service),
    current_user: DBUser = Depends(authenticate_user),
):
    """Semantic search for books using natural language.

    Embeds the query, then finds the most similar books by cosine similarity.
    Returns results ranked by relevance with a similarity score.
    """
    if not q.strip():
        return []

    query_embedding = await summary_service.generate_query_embedding(q)
    results = await book_service.semantic_search(
        query_embedding=query_embedding, limit=limit,
    )

    return [
        SearchResultOutput(**book.model_dump(), relevance=score)
        for book, score in results
    ]


@router.post("/backfill-embeddings", response_model=BackfillResult)
async def backfill_embeddings(
    summary_service: SummaryService = Depends(_get_summary_service),
    current_user: DBUser = Depends(require_admin),
):
    """Regenerate embeddings for all books missing them."""
    return await summary_service.backfill_embeddings()


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
    summary_service: SummaryService = Depends(_get_summary_service),
    current_user: DBUser = Depends(require_admin),
):
    # Strip embedding from client input — only the system sets embeddings
    changed_fields = update_input.model_dump(exclude_unset=True)
    changed_fields.pop("embedding", None)

    # Regenerate embedding if any searchable field changed
    if any(f in changed_fields for f in ("title", "description", "summary")):
        current_book = await book_service.retrieve(book_id=book_id)
        title = changed_fields.get("title", current_book.title)
        description = changed_fields.get("description", current_book.description)
        summary = changed_fields.get("summary", current_book.summary)
        try:
            embedding = await summary_service.generate_embedding_for_text(title, description, summary)
            changed_fields["embedding"] = embedding
        except Exception:
            logger.warning("Embedding regeneration failed for book %s", book_id)

    book = await book_service.update(book_id=book_id, data=BookUpdateInput(**changed_fields))

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
    """Generate summary and regenerate embedding for a single book."""
    book = await book_service.retrieve(book_id=book_id)

    if not book.full_text:
        raise HTTPException(status_code=400, detail="Book has no full_text to summarize")

    summary = await summary_service.generate_summary_text(book.full_text)
    embedding = await summary_service.generate_embedding_for_text(
        title=book.title, description=book.description, summary=summary,
    )
    book = await book_service.update(
        book_id=book_id, data=BookUpdateInput(summary=summary, embedding=embedding),
    )
    return BookDetailOutput(**book.model_dump())
