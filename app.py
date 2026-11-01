import os
import tempfile
import uuid
from typing import Dict, Any

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from openai import OpenAI
from pydantic import BaseModel

from langchain_community.document_loaders import PyPDFLoader
from langchain_community.vectorstores import FAISS
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")

if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY is missing. Add it to your .env file.")

app = FastAPI(title="Conversational PDF RAG")
app.mount("/static", StaticFiles(directory="static"), name="static")

# Shared model/client instances. Each uploaded PDF gets its own vector store and history.
openai_client = OpenAI(api_key=OPENAI_API_KEY)
embeddings = HuggingFaceEmbeddings(
    model_name="sentence-transformers/all-MiniLM-L6-v2",
    model_kwargs={"device": "cpu"},
    encode_kwargs={"normalize_embeddings": True},
)
splitter = RecursiveCharacterTextSplitter(
    chunk_size=1000,
    chunk_overlap=200,
)

# In-memory session store. Sessions disappear when the server restarts.
sessions: Dict[str, Dict[str, Any]] = {}


class ChatRequest(BaseModel):
    session_id: str
    question: str


@app.get("/")
def home():
    return FileResponse("static/index.html")


def rewrite_question(question: str, history: list) -> str:
    """Resolve references in a follow-up question before vector retrieval."""
    if not history:
        return question

    messages = [
        {
            "role": "system",
            "content": (
                "Rewrite the latest user question as a standalone search query "
                "using the conversation history. Resolve references such as "
                "'it', 'they', 'the first one', and 'that method'. Preserve the "
                "meaning. Do not answer the question or add facts. If it is "
                "already standalone, return it unchanged. Return only the query."
            ),
        }
    ]
    # Keep a bounded recent history (10 messages = up to 5 exchanges).
    messages.extend(history[-10:])
    messages.append({"role": "user", "content": question})

    response = openai_client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=messages,
        temperature=0,
    )
    rewritten = response.choices[0].message.content
    return rewritten.strip() if rewritten else question


@app.post("/api/sessions/upload")
def upload_pdf(file: UploadFile = File(...)):
    """Uploading a PDF creates a completely new conversation session."""
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Please upload a PDF file.")

    temp_path = None
    try:
        contents = file.file.read()
        if not contents:
            raise HTTPException(status_code=400, detail="The uploaded PDF is empty.")

        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_file:
            temp_file.write(contents)
            temp_path = temp_file.name

        pages = PyPDFLoader(temp_path).load()
        if not pages or not any(page.page_content.strip() for page in pages):
            raise HTTPException(
                status_code=400,
                detail="No extractable text was found. If this is a scanned PDF, OCR is required.",
            )

        chunks = splitter.split_documents(pages)
        if not chunks:
            raise HTTPException(status_code=400, detail="No text chunks could be created.")

        vectorstore = FAISS.from_documents(chunks, embeddings)
        session_id = str(uuid.uuid4())

        sessions[session_id] = {
            "filename": file.filename,
            "vectorstore": vectorstore,
            "history": [],
        }

        return {
            "session_id": session_id,
            "filename": file.filename,
            "pages": len(pages),
            "chunks": len(chunks),
            "message": "PDF processed. You can start asking questions.",
        }

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"PDF processing failed: {exc}")
    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)


@app.post("/api/chat")
def chat(request: ChatRequest):
    session = sessions.get(request.session_id)
    if session is None:
        raise HTTPException(
            status_code=404,
            detail="This session was not found. Upload a PDF to start a new session.",
        )

    question = request.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Please enter a question.")

    history = session["history"]
    try:
        # Rewrite follow-ups so the retriever can understand their references.
        search_query = rewrite_question(question, history)

        # Retrieve relevant chunks from this session's PDF only.
        docs = session["vectorstore"].similarity_search(search_query, k=5)

        context_parts = []
        sources = []
        for index, doc in enumerate(docs, start=1):
            page_number = int(doc.metadata.get("page", 0)) + 1
            context_parts.append(
                f"[Source {index} | Page {page_number}]\n{doc.page_content}"
            )
            sources.append({
                "source": index,
                "page": page_number,
                "preview": doc.page_content[:350].strip(),
            })

        context = "\n\n".join(context_parts)

        messages = [
            {
                "role": "system",
                "content": (
                    "You are a helpful assistant answering questions about an "
                    "uploaded PDF. Use the supplied PDF context as the factual "
                    "source. Use conversation history to understand follow-up "
                    "questions, but do not treat earlier assistant answers as "
                    "proof if the PDF context does not support them. If the "
                    "answer is not present in the retrieved context, say that "
                    "you could not find it in the uploaded PDF. Do not invent "
                    "facts. Cite page numbers when useful."
                ),
            },
            {
                "role": "system",
                "content": f"Retrieved PDF context:\n\n{context}",
            },
        ]
        messages.extend(history[-10:])
        messages.append({"role": "user", "content": question})

        response = openai_client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=messages,
            temperature=0,
        )
        answer = response.choices[0].message.content or "I couldn't generate an answer."

        # Store the original user wording and the answer, not the rewritten query.
        history.append({"role": "user", "content": question})
        history.append({"role": "assistant", "content": answer})

        return {
            "answer": answer,
            "sources": sources,
            "rewritten_query": search_query,
        }

    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Question answering failed: {exc}")


@app.delete("/api/sessions/{session_id}")
def close_session(session_id: str):
    """Remove the session's history and in-memory vector store."""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found.")
    del sessions[session_id]
    return {"message": "Session closed."}
