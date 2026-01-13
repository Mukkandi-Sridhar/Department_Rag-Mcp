# RAG AIML Projects

This repository contains two AI-powered applications demonstrating Retrieval-Augmented Generation (RAG) using LangChain, OpenAI, and Gradio.

## Projects

### 1. Student Data Assistant (`app.py`)
A chatbot that answers questions about student performance, backlog, and other details based on a structured CSV dataset (`students_data_new.csv`).

**Features:**
- **Conversational Interface:** Chat with the bot using natural language.
- **Data-Driven:** Strictly answers from the provided CSV data.
- **Fuzzy Name Matching:** Intelligently resolves misspelled or partial student names.
- **Memory:** Maintains conversation context.

### 2. PDF QA Bot (`app2.py`)
A document assistant that allows users to upload a PDF and ask questions based on its content.

**Features:**
- **PDF Upload:** Upload any PDF document interactively.
- **Content Retrieval:** Uses vector search to find relevant sections of the PDF.
- **Source-Based Answers:** Generates answers strictly from the uploaded document.

## Prerequisites

- Python 3.9+
- OpenAI API Key

## Installation

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/Mukkandi-Sridhar/RAG_AIML.git
    cd RAG_AIML
    ```

2.  **Create a virtual environment (optional but recommended):**
    ```bash
    python -m venv .venv
    # Windows
    .venv\Scripts\activate
    # Mac/Linux
    source .venv/bin/activate
    ```

3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
    *Note: If `requirements.txt` is missing, install the core packages:*
    ```bash
    pip install langchain langchain-openai chromadb sentence-transformers gradio pandas python-dotenv langchain-community langchain-huggingface pypdf
    ```

## Configuration

1.  **Set up Environment Variables:**
    Create a `.env` file in the root directory and add your OpenAI API key:
    ```env
    OPENAI_API_KEY=sk-your-api-key-here
    ```

## Usage

### Running the Student Data Assistant
```bash
python app.py
```
Open the Gradio URL (usually `http://127.0.0.1:7860`) in your browser.

### Running the PDF QA Bot
```bash
python app2.py
```
Open the Gradio URL and upload a PDF to start asking questions.

## Project Structure

- `app.py`: Main script for the Student Data Assistant.
- `app2.py`: Main script for the PDF QA Bot.
- `students_data_new.csv`: Dataset for the Student Data Assistant.
- `.env`: (Not included in repo) Store your API keys here.
