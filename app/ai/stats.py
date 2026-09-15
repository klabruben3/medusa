def token_count(response, functionName):
    usage = response.usage
    print(f"Prompt tokens for {functionName}: {usage.prompt_tokens}")
    print(f"Completion tokens for {functionName}: {usage.completion_tokens}")
    print(f"Total tokens for {functionName}: {usage.total_tokens}")
