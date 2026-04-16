import os

import gradio as gr
import requests
from dotenv import load_dotenv


load_dotenv()

API_URL = os.getenv("API_URL", "http://127.0.0.1:8000")


def chat(message: str, token: str):
    if not token.strip():
        return "Enter a Firebase token, or use dev token dev:<reg_no> when AUTH_MODE=dev."

    response = requests.post(
        f"{API_URL}/chat",
        json={"message": message},
        headers={"Authorization": f"Bearer {token.strip()}"},
        timeout=15,
    )

    try:
        body = response.json()
    except ValueError:
        return f"API returned non-JSON response: {response.text}"

    if response.status_code >= 400:
        return body.get("detail", "Request failed.")

    return body.get("answer", "No answer returned.")


with gr.Blocks() as demo:
    gr.Markdown("# Department AI MVP")
    gr.Markdown(
        "Ask about your backlogs, CGPA, placement readiness, or uploaded documents."
    )

    token = gr.Textbox(
        label="Auth token",
        placeholder="Firebase ID token, or dev:23091A3349 in local dev mode",
        type="password",
    )
    question = gr.Textbox(
        label="Question",
        placeholder="Do I have backlogs?",
    )
    answer = gr.Textbox(label="Answer")
    submit = gr.Button("Ask")

    submit.click(chat, inputs=[question, token], outputs=answer)
    question.submit(chat, inputs=[question, token], outputs=answer)


if __name__ == "__main__":
    demo.launch()
