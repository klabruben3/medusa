def token_count(response):
    usage = response.usage
    print(f"Prompt tokens for extract_modules: {usage.prompt_tokens}")
    print(f"Completion tokens for extract_modules: {usage.completion_tokens}")
    print(f"Total tokens for extract_modules: {usage.total_tokens}")
