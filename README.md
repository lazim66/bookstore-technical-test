# Backend & Agents Technical Test

## Submission Notes from Lazim

All technical decisions, trade-offs, and implementation details are documented in **[TECHNICAL_COMMENTARY.md](./TECHNICAL_COMMENTARY.md)**.

To run the project, add your OpenAI API key to `.env` (required for summary generation and semantic search):
```bash
cp .env.example .env
# Edit .env and set OPENAI_API_KEY=your-key-here
```

To see every feature in action, please run the end-to-end smoke test:
```bash
just start             # Start all services
just smoke-test        # 42 checks across all features with real LLM calls (~1 min)
```

The smoke test exercises permissions, summary generation (real OpenAI), and semantic search (real embeddings) against the live Docker stack, showing actual outputs. It cleans up after itself automatically.

---

Welcome! This is a **backend and agents-focused technical test** designed to assess your ability to:

1. **Produce production-ready code** - Write clean, maintainable, well-tested code that follows best practices
2. **Clearly articulate your work** - Document your decisions, approach, and implementation details
3. **Make sound, product-focused, engineering decisions** - Choose appropriate solutions and justify your technical choices

You'll be working with a pre-built FastAPI backend that powers a bookstore application. Your task will be to extend this system with role-based access control and intelligent LLM-powered features that enhance the customer experience.

## Before You Begin

**📖 Read the [SYSTEM_OVERVIEW.md](./SYSTEM_OVERVIEW.md) first!**

This document contains everything you need to know about the existing system architecture, database schema, and API patterns.

## Quick Start

### Prerequisites

- Docker and Docker Compose installed
- [Just](https://github.com/casey/just) command runner (optional but recommended)
- LLM API key from a provider of your choice (OpenAI, Anthropic, etc.). If you don't have one or would prefer not to use your own, let us know and we'll arrange one.

### Setup

1. **Copy environment file:**
   ```bash
   cp .env.example .env
   # Add your LLM API credentials (OpenAI, Anthropic, or other provider)
   ```

2. **Start the application:**
   ```bash
   just start
   ```

3. **Verify setup:**
   ```bash
   just test
   ```

   You should see all 59 tests passing.

4. **Explore the API:**
   - API: http://localhost:8080
   - Interactive docs: http://localhost:8080/docs

### Development Commands

```bash
just build          # Build Docker images
just start          # Start all services and tail logs
just stop           # Stop all services
just restart        # Restart all services
just shell          # Open bash shell in API container
just test           # Run tests inside container
just test-cov       # Run tests with coverage report
just db-reset       # Reset database (drops all data)
just logs           # Follow API logs
```

## Test Deliverables

You'll extend the existing bookstore API with security enhancements and intelligent features that improve the customer experience. This involves implementing role-based access control, adding book summaries to help customers make reading decisions, and enabling semantic search so customers can find books using natural language.

### Backend: Permissions

Currently, all API endpoints are open to any authenticated user. The bookstore needs a simple permissions system. This should make browsing the catalog and placing orders possible for any customer can do, but managing books and authors in the catalog should be restricted to admins.

Design and implement a simple permissions model that makes sense for this application. Decide what operations need protecting, and how permissions are assigned and checked.

### Book Summaries

Books need summaries that help customers decide what to read. When admins add books to the catalog, they'll include the full book text. Your system should automatically generate customer-friendly summaries from this text using an LLM.

Additionally, we need a way to generate summaries for books that were added before this feature existed - a backfill operation that admins can trigger to process multiple books.

The system needs to handle situations where many books are being added or summarized concurrently.

### Semantic Search

Customers should be able to find books using natural language, not just exact keyword matches. For example, they might search for "mystery novels set in Tokyo" or "science fiction about time travel" and get relevant results even if those exact words don't appear in book titles or descriptions.

Build a search feature that understands the meaning of queries and matches them against books in the catalog. The search results should be ranked by relevance.

**Note:** The database supports vector storage through the `pgvector` extension if you want to use it.

### Technical Commentary Document

As you work through the test, create a `TECHNICAL_COMMENTARY.md` file with three sections:

**1. Approach**
- How you plan to tackle each deliverable
- Key technical decisions and trade-offs you're considering
- Reasoning behind your decisions considering: development pace, outcome quality, ease of implementation, scalability, maintainability

**2. Implementation**
- What you actually built and how
- Any deviations from your original approach and why
- Challenges encountered and how you solved them

**3. Discussion**
- Reflection on how the implementation went
- What was particularly challenging or time-consuming
- What you would do differently in the future
- How you would extend or improve the application given more time

**Tip:** Consider using AI note-taking tools or voice dictation software to capture your thoughts more quickly as you work. Speaking through your reasoning can often be faster and more natural than typing everything out.

### Use of AI Tools

We encourage you to use AI tools (like ChatGPT, Claude, Copilot, etc.) as productivity aids throughout this test. Modern software development involves leveraging these tools effectively, and we want to see how you use them. What matters is your ability to make sound technical decisions, understand the code you're writing, and articulate your reasoning - whether you wrote every character yourself or collaborated with AI to get there faster.

## Evaluation

We'll be assessing your submission holistically, looking at how well you've solved the problem and how clearly you've communicated your thinking.

**What we care most about:** Does the application work? Are catalog management operations properly protected? Can customers search for books semantically and see helpful summaries? The API should be functional and reliable. We're not evaluating architectural perfection or premature optimization; a clean implementation that works well is what matters. What's important is that the API accomplishes the required tasks effectively.

**Your technical commentary is crucial.** We want to understand how you approached the problem, what trade-offs you considered, and why you made particular decisions. For example, how did you handle concurrent summarization requests? Which LLM provider did you choose and why? How did you balance speed of implementation with code quality? What would you do differently with more time? Your ability to articulate these decisions and reflect honestly on the work is just as important as the code itself.

**Code quality matters**, but in service of building something that works. We expect clean, maintainable code that follows best practices. Overall, we're most interested in seeing a working application with thoughtful decisions than perfect code that doesn't quite deliver on the requirements.

Finally, we're evaluating your product thinking. Did you make pragmatic choices? Can you explain the trade-offs between different approaches? Do you understand the implications of your decisions on maintainability and scalability? The best submissions demonstrate not just technical skill, but an understanding of how to build software that solves real problems effectively.

## Questions?

Review the [SYSTEM_OVERVIEW.md](./SYSTEM_OVERVIEW.md) for detailed technical documentation about the existing system.

If you have any questions about the test, please email ryan@meetdex.ai

---

**A note on scope:** This is an ambitious test by design. We're not expecting perfection across every deliverable in a single sitting - we want to see how you navigate a meaningfully sized problem, make trade-offs under time pressure, and demonstrate fluency across backend and AI/agents work. We suggest spending no more than 4 hours on it, focusing on delivering a working system and articulating your decisions clearly - that matters more than completeness.

Good luck! 🚀
