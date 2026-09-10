TOOL_USAGE_PROMPT = """
When using tools:

1. Select the most appropriate tool.
2. Provide valid arguments.
3. Use the returned result rather than guessing.
4. If multiple tools are needed, use them sequentially.
5. After receiving tool results, determine whether another
   tool is necessary.
6. Only provide the final answer after completing the required
   tool operations.
"""