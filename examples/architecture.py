"""Run: asciio-python run examples/architecture.py -o architecture.pasciio"""

from asciio import Element
from asciio.editor import Editor


def build(editor: Editor) -> None:
    browser = Element(x=2, y=2, title="Browser", text="Web UI", style="unicode")
    api = Element(x=28, y=2, title="API", text="Python service", style="unicode")
    database = Element(kind="ellipse", x=62, y=1, text="Database")
    worker = Element(x=28, y=13, title="Worker", text="Background jobs", style="unicode")
    with editor.change():
        editor.diagram.elements.extend([browser, api, database, worker])
    editor.link(browser, api)
    editor.link(api, database)
    editor.link(api, worker, "bottom", "top")
    editor.select(set())


if __name__ == "__main__":
    build(globals()["editor"])
