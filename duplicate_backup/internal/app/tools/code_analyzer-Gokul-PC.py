import ast


def analyze_python_code(
    code: str,
) -> dict:

    if not code.strip():

        return {
            "success": False,
            "error": "No Python code provided.",
        }

    try:

        tree = ast.parse(code)

    except SyntaxError as exc:

        return {
            "success": False,
            "syntax_error": {
                "message": exc.msg,
                "line": exc.lineno,
                "column": exc.offset,
            },
        }

    functions = []
    classes = []
    imports = []

    for node in ast.walk(tree):

        if isinstance(
            node,
            (ast.FunctionDef, ast.AsyncFunctionDef),
        ):

            functions.append(node.name)

        elif isinstance(
            node,
            ast.ClassDef,
        ):

            classes.append(node.name)

        elif isinstance(
            node,
            ast.Import,
        ):

            for alias in node.names:
                imports.append(alias.name)

        elif isinstance(
            node,
            ast.ImportFrom,
        ):

            if node.module:
                imports.append(node.module)

    return {
        "success": True,
        "syntax_valid": True,
        "functions": functions,
        "classes": classes,
        "imports": imports,
        "line_count": len(
            code.splitlines()
        ),
    }