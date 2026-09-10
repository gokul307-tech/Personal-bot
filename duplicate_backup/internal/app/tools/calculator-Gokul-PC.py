import ast
import math
import operator


_ALLOWED_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
    ast.FloorDiv: operator.floordiv,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


_ALLOWED_FUNCTIONS = {
    "sqrt": math.sqrt,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "log": math.log,
    "log10": math.log10,
    "abs": abs,
    "round": round,
}


def _evaluate(node):

    if isinstance(node, ast.Constant):

        if isinstance(node.value, (int, float)):

            return node.value

        raise ValueError(
            "Only numeric values are allowed."
        )

    if isinstance(node, ast.BinOp):

        operator_type = type(node.op)

        if operator_type not in _ALLOWED_OPERATORS:
            raise ValueError(
                "Operator is not allowed."
            )

        left = _evaluate(node.left)
        right = _evaluate(node.right)

        return _ALLOWED_OPERATORS[operator_type](
            left,
            right,
        )

    if isinstance(node, ast.UnaryOp):

        operator_type = type(node.op)

        if operator_type not in _ALLOWED_OPERATORS:
            raise ValueError(
                "Unary operator is not allowed."
            )

        operand = _evaluate(node.operand)

        return _ALLOWED_OPERATORS[operator_type](
            operand
        )

    if isinstance(node, ast.Call):

        if not isinstance(
            node.func,
            ast.Name,
        ):
            raise ValueError(
                "Invalid function."
            )

        function_name = node.func.id

        if function_name not in _ALLOWED_FUNCTIONS:
            raise ValueError(
                f"Function '{function_name}' is not allowed."
            )

        arguments = [
            _evaluate(argument)
            for argument in node.args
        ]

        return _ALLOWED_FUNCTIONS[
            function_name
        ](*arguments)

    raise ValueError(
        "Unsupported mathematical expression."
    )


def calculator(expression: str) -> str:

    """
    Safely evaluate a mathematical expression.

    Supported examples:

    10 + 20
    25 * 4
    sqrt(144)
    2 ** 10
    """

    try:

        expression = expression.strip()

        if not expression:
            return "Error: Empty expression."

        if len(expression) > 500:
            return "Error: Expression is too long."

        tree = ast.parse(
            expression,
            mode="eval",
        )

        result = _evaluate(tree.body)

        return str(result)

    except Exception as exc:

        return f"Calculation error: {exc}"