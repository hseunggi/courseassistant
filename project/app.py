from flask import Flask, request, render_template
from ai import answer_question, answer_kb

app = Flask(__name__)

@app.route("/", methods=["GET", "POST"])
def index():
    db_answer = ""
    kb_answer = ""
    question = ""

    if request.method == "POST":
        question = request.form["question"]
        db_answer = answer_question(question)
        kb_answer = answer_kb(question)

    return render_template("index.html",
                           question=question,
                           db_answer=db_answer,
                           kb_answer=kb_answer)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=80)
