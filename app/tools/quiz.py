import json

from app.llm.client import ask_llm


def generate_quiz(
    topic: str,
    number_of_questions: int = 5,
    difficulty: str = "medium",
) -> dict:

    if number_of_questions < 1:
        return {
            "success": False,
            "error": "At least one question is required.",
        }

    if number_of_questions > 20:
        return {
            "success": False,
            "error": "Maximum 20 questions are allowed.",
        }

    prompt = f"""
Create a multiple-choice quiz.

Topic: {topic}
Number of questions: {number_of_questions}
Difficulty: {difficulty}

Return ONLY valid JSON in this structure:

{{
    "questions": [
        {{
            "question": "...",
            "options": [
                "A. ...",
                "B. ...",
                "C. ...",
                "D. ..."
            ],
            "correct_answer": "A",
            "explanation": "..."
        }}
    ]
}}
"""

    try:

        response = ask_llm(
            [
                {
                    "role": "system",
                    "content": (
                        "You are an educational quiz generator. "
                        "Return valid JSON only."
                    ),
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ]
        )

        content = response.content or ""

        data = json.loads(content)

        return {
            "success": True,
            "topic": topic,
            "difficulty": difficulty,
            "questions": data.get(
                "questions",
                [],
            ),
        }

    except json.JSONDecodeError:

        return {
            "success": False,
            "error": "The model returned invalid quiz JSON.",
        }

    except Exception as exc:

        return {
            "success": False,
            "error": f"Quiz generation failed: {exc}",
        }