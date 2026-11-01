# Conversational PDF RAG

A small PDF question-answering application with:
- FastAPI backend
- HTML/CSS/JavaScript frontend
- LangChain PDF loading, splitting, embeddings and FAISS integration
- OpenAI answer generation and follow-up question rewriting
- New PDF session support

## 1. Requirements

- Python 3.10 or newer
- An OpenAI API key with API access/billing enabled

## 2. Install

Create and activate a virtual environment:

```bash
python -m venv .venv
```

Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

macOS/Linux:

```bash
source .venv/bin/activate
```

Install packages:

```bash
pip install -r requirements.txt
```

## 3. Configure the API key

Copy `.env.example` to `.env` and add your key:

```dotenv
OPENAI_API_KEY=your_real_key
OPENAI_MODEL=gpt-4.1-mini
```

Do not commit `.env` or share your API key.

## 4. Run

From the project root:

```bash
uvicorn app:app --reload
```

Open http://127.0.0.1:8000 in your browser.

## 5. How it works

1. Uploading a PDF creates a new session and builds a FAISS index.
2. Each question is rewritten using recent conversation history so references like "it" and "the first one" become standalone retrieval queries.
3. FAISS retrieves up to five relevant chunks.
4. OpenAI generates an answer using the retrieved PDF context, the original question and recent conversation history.
5. The **New PDF session** button deletes the active in-memory session and lets you upload another PDF.

## Notes and limitations

- Sessions and FAISS indexes are held in server memory. They disappear when the server restarts.
- This starter project is intended for local development and a single-process server. For production or multiple server workers, use persistent storage (for example PostgreSQL for sessions and a persistent vector database) and add authentication/authorization.
- Scanned/image-only PDFs need OCR; this project extracts embedded PDF text.
- The chat history is bounded to the most recent 10 messages when sent to the model.
- The API returns the rewritten query for debugging. You can remove `rewritten_query` from the response after development.
- OpenAI API usage may incur charges and is separate from a ChatGPT subscription.
