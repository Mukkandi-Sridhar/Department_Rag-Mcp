# ============================================================
# INSTALL DEPENDENCIES (run once in terminal / virtualenv)
# ============================================================
# Install required packages in your environment, for example:
#   pip install langchain==0.1.16 langchain-openai==0.1.7 chromadb sentence-transformers==2.5.1 gradio
# Or create a virtual environment and install from a requirements file:
#   python -m venv .venv && .venv\Scripts\activate  # (Windows)
#   pip install -r requirements.txt
# ============================================================


# ============================================================
# IMPORTS
# ============================================================

import os
import warnings
warnings.filterwarnings("ignore")

import pandas as pd
from difflib import get_close_matches

import gradio as gr

from langchain.schema import Document
from langchain.text_splitter import CharacterTextSplitter
from langchain.chains import ConversationalRetrievalChain
from langchain.prompts import PromptTemplate
from langchain.memory import ConversationBufferMemory

from langchain_openai import ChatOpenAI
from langchain_community.vectorstores import Chroma
from langchain_huggingface import HuggingFaceEmbeddings

from dotenv import load_dotenv
load_dotenv()



# ============================================================
# CONFIG (DO THIS PROPERLY)
# ============================================================

# ✅ Set your key via environment variable (recommended)
# NOTE: Do NOT hardcode your API key in source. Set it in your shell or use a .env file.
# Example (PowerShell): $env:OPENAI_API_KEY = "sk-..."
# Example (bash): export OPENAI_API_KEY="sk-..."
if not os.getenv("OPENAI_API_KEY"):
    raise ValueError("❌ OPENAI_API_KEY not found in environment variables")

CSV_FILE = "students_data_new.csv"   # upload this file first


# ============================================================
# LOAD DATA
# ============================================================

df = pd.read_csv(CSV_FILE)

ALL_NAMES = df["name"].str.lower().tolist()


# ============================================================
# BUILD DOCUMENTS
# ============================================================

documents = []

for _, row in df.iterrows():
    text = f"""
Student Name: {row['name']}
Register Number: {row['reg_no']}
Program: {row['program']}
Gender: {row['gender']}
Category: {row['category']}
Performance Level: {row['performance']}
CGPA: {row['cgpa']}
Backlogs: {row['backlogs']}
Risk Level: {row['risk']}
Strengths: {row['strengths']}
Weaknesses: {row['weaknesses']}
Activities: {row['activities']}
Certifications: {row['certifications']}
Placement Status: {row['placement']}
"""
    documents.append(Document(page_content=text))


# ============================================================
# SPLIT DOCUMENTS
# ============================================================

splitter = CharacterTextSplitter(chunk_size=600, chunk_overlap=0)
chunks = splitter.split_documents(documents)


# ============================================================
# EMBEDDINGS + VECTOR STORE
# ============================================================

embeddings = HuggingFaceEmbeddings(
    model_name="sentence-transformers/all-MiniLM-L6-v2"
)

vectordb = Chroma.from_documents(
    documents=chunks,
    embedding=embeddings
)

retriever = vectordb.as_retriever(search_kwargs={"k": 8})


# ============================================================
# FUZZY NAME RESOLUTION
# ============================================================

def resolve_name_from_question(question: str):
    q = question.lower()
    for phrase in ["who is", "tell me about", "give details of"]:
        q = q.replace(phrase, "")
    q = q.strip()

    match = get_close_matches(q, ALL_NAMES, n=1, cutoff=0.6)
    return match[0] if match else None


# ============================================================
# LLM
# ============================================================

llm = ChatOpenAI(
    model="gpt-4o-mini",
    temperature=0
)


# ============================================================
# PROMPT
# ============================================================

PROMPT = PromptTemplate(
    template="""
You are a student data assistant.

Rules:
- Answer ONLY from the context.
- If data is missing, clearly say you don't have that information.
- Keep answers short, clear, and human.
- Accept greetings politely.
- Do not hallucinate.

Context:
{context}

Question:
{question}
""",
    input_variables=["context", "question"]
)


# ============================================================
# MEMORY
# ============================================================

memory = ConversationBufferMemory(
    memory_key="chat_history",
    return_messages=True
)


# ============================================================
# CONVERSATIONAL RAG
# ============================================================

agent = ConversationalRetrievalChain.from_llm(
    llm=llm,
    retriever=retriever,
    memory=memory,
    combine_docs_chain_kwargs={"prompt": PROMPT},
    return_source_documents=False
)


# ============================================================
# ASK FUNCTION
# ============================================================

def ask_agent(question: str):
    resolved_name = resolve_name_from_question(question)

    if resolved_name:
        question = f"Who is {resolved_name}?"

    response = agent.invoke({"question": question})
    return response["answer"]


# ============================================================
# GRADIO CHAT FUNCTION
# ============================================================

def chat_fn(message, history):
    answer = ask_agent(message)
    history.append((message, answer))
    return history, history


# ============================================================
# GRADIO UI
# ============================================================

with gr.Blocks(theme=gr.themes.Soft()) as demo:
    gr.Markdown(
        """
        # 🎓 |||-YEAR CSE-AIML RGMCET
        Ask questions strictly based on the students.

        **Examples**
        - Who is Sridhar?
        - Who has more backlogs?
        - Tell me about the topper
        """
    )

    chatbot = gr.Chatbot(height=450)
    state = gr.State([])

    with gr.Row():
        txt = gr.Textbox(
            placeholder="Ask a question...",
            show_label=False,
            scale=4
        )
        btn = gr.Button("Send", scale=1)

    btn.click(chat_fn, inputs=[txt, state], outputs=[chatbot, state])
    txt.submit(chat_fn, inputs=[txt, state], outputs=[chatbot, state])

    gr.Markdown("⚠️ Answers come only from the dataset.")


# ============================================================
# RUN
# ============================================================

demo.launch(share=True, debug=True)
