import os
import warnings
warnings.filterwarnings("ignore")

import gradio as gr

from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import Chroma
from langchain_community.document_loaders import PyPDFLoader
from langchain.chains import RetrievalQA
from dotenv import load_dotenv
load_dotenv()


# ============================================================
# ENV CHECK
# ============================================================

if not os.getenv("OPENAI_API_KEY"):
    raise ValueError("❌ OPENAI_API_KEY not found in environment variables")


# ============================================================
# LLM
# ============================================================

def get_llm():
    return ChatOpenAI(
        model="gpt-4o-mini",
        temperature=0.5,
        max_tokens=256
    )


# ============================================================
# DOCUMENT LOADER
# ============================================================

def document_loader(file_path):
    loader = PyPDFLoader(file_path)
    return loader.load()


# ============================================================
# TEXT SPLITTER
# ============================================================

def text_splitter(docs):
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200,
        length_function=len
    )
    return splitter.split_documents(docs)


# ============================================================
# EMBEDDINGS
# ============================================================

def get_embeddings():
    return OpenAIEmbeddings(
        model="text-embedding-3-small"
    )


# ============================================================
# VECTOR DATABASE
# ============================================================

def vector_database(chunks):
    embeddings = get_embeddings()
    return Chroma.from_documents(chunks, embeddings)


# ============================================================
# RETRIEVER
# ============================================================

def retriever(file_path):
    docs = document_loader(file_path)
    chunks = text_splitter(docs)
    vectordb = vector_database(chunks)
    return vectordb.as_retriever()


# ============================================================
# QA CHAIN
# ============================================================

def retriever_qa(file_path, query):
    llm = get_llm()
    retriever_obj = retriever(file_path)

    qa = RetrievalQA.from_chain_type(
        llm=llm,
        chain_type="stuff",
        retriever=retriever_obj,
        return_source_documents=False
    )

    response = qa.invoke(query)
    return response["result"]


# ============================================================
# GRADIO INTERFACE
# ============================================================

rag_app = gr.Interface(
    fn=retriever_qa,
    allow_flagging="never",
    inputs=[
        gr.File(
            label="Upload PDF",
            file_types=[".pdf"],
            type="filepath"
        ),
        gr.Textbox(
            label="Your Question",
            lines=2,
            placeholder="Ask something from the document..."
        )
    ],
    outputs=gr.Textbox(label="Answer"),
    title="📄 PDF Question Answering Bot",
    description="Upload a PDF and ask questions strictly based on its content."
)


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    rag_app.launch(share=True)
