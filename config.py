# Configuration settings for the AI Assistant

# --- AI Provider Selection ---
# Choose the AI provider to use.
# Options: "ollama", "openrouter", "gemini", "openai"
# Ensure the corresponding _SETTINGS dictionary below is correctly configured.
AI_PROVIDER = "ollama" 

# --- Ollama Settings ---
# Used if AI_PROVIDER is "ollama"
OLLAMA_SETTINGS = {
    "BASE_URL": "http://localhost:11434", # Default Ollama API URL
    "MODEL": "gemma3:1b" # Default Ollama model
}

# --- OpenRouter Settings ---
# Used if AI_PROVIDER is "openrouter"
# Replace "YOUR_OPENROUTER_API_KEY_HERE" with your actual OpenRouter API key.
OPENROUTER_SETTINGS = {
    "API_KEY": "YOUR_OPENROUTER_API_KEY_HERE",
    "MODEL": "openrouter/auto"  # Example: "mistralai/mistral-7b-instruct", "openrouter/auto" for auto-selection
}

# --- Gemini Settings ---
# Used if AI_PROVIDER is "gemini"
# Replace "YOUR_GEMINI_API_KEY_HERE" with your actual Google AI Studio API key for Gemini.
GEMINI_SETTINGS = {
    "API_KEY": "YOUR_GEMINI_API_KEY_HERE",
    "MODEL": "gemini-pro" # Example: "gemini-1.5-flash", "gemini-pro"
}

# --- OpenAI Settings ---
# Used if AI_PROVIDER is "openai"
# Replace "YOUR_OPENAI_API_KEY_HERE" with your actual OpenAI API key.
OPENAI_SETTINGS = {
    "API_KEY": "YOUR_OPENAI_API_KEY_HERE",
    "MODEL": "gpt-3.5-turbo" # Example: "gpt-4", "gpt-3.5-turbo"
}

# --- Old Ollama Global Settings (Commented out as they are now in OLLAMA_SETTINGS) ---
# OLLAMA_API_BASE_URL = "http://localhost:11434"
# OLLAMA_MODEL = "gemma3:1b"

# Directory settings (for future safety features, not fully implemented in this basic example)
# ALLOWED_READ_PATHS = ["/home/user/Documents", "/mnt/data"] # Example
# ALLOWED_WRITE_PATHS = ["/home/user/AI_Assistant_Output"] # Example