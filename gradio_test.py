import gradio as gr
def greet(name,intensity):
    return f"Hello {name}! " + "!" * intensity
demo = gr.Interface(fn=greet, inputs=["text", gr.Slider(0,10,1)], outputs="text")
demo.launch()
