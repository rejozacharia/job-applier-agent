# src/genai_handler.py
import os
from src.utils import logger # Import the configured logger

class GenAIHandler:
    """
    Handles interactions with various GenAI providers.
    API keys are sourced from environment variables (e.g., GEMINI_API_KEY).
    Other configurations like model names and base URLs can be passed via DB config.
    """

    def __init__(self, db_configs=None):
        """
        Initializes the GenAIHandler.
        
        Args:
            db_configs (list of GenAIConfig objects, optional):
                Configurations loaded from the database, including provider_name,
                model_name, base_url, is_enabled, purpose.
                API keys are NOT expected here; they are fetched from environment variables.
        """
        self.db_configs = db_configs if db_configs else []
        # We can build a more structured internal config from db_configs if needed,
        # for quick lookups by provider and purpose.
        # For now, we'll iterate or filter db_configs directly where needed,
        # or expect specific provider_config to be passed to methods.

        # Example: Pre-process db_configs into a more usable dictionary
        self.provider_settings = {}
        for conf in self.db_configs:
            if conf.is_enabled:
                # Store settings by (provider_name, purpose) tuple for easy lookup
                # This assumes one config per provider/purpose. If multiple are allowed,
                # this structure would need to be a list of configs.
                self.provider_settings[(conf.provider_name, conf.purpose)] = {
                    'model_name': conf.model_name,
                    'base_url': conf.base_url
                }
        logger.info("[GenAI Handler] Initialized. API keys will be sourced from environment variables.")

    def _get_active_config(self, provider_name, purpose):
        """
        Retrieves the active configuration for a given provider and purpose from db_configs.
        Returns the GenAIConfig object if found and enabled, else None.
        """
        for config_item in self.db_configs:
            if config_item.provider_name == provider_name and \
               config_item.purpose == purpose and \
               config_item.is_enabled:
                return config_item
        return None

    def _get_api_key_for_provider(self, provider_name):
        """
        Fetches the API key for a given provider from environment variables.
        Uses the convention PROVIDERNAME_API_KEY (e.g., GEMINI_API_KEY).
        """
        env_var_name = f"{provider_name.upper()}_API_KEY"
        api_key = os.getenv(env_var_name)
        if not api_key:
            logger.warning(f"[GenAI Handler] API key for {provider_name} not found in environment variable {env_var_name}.")
        return api_key

    def generate_cover_letter_content(self, job_details, user_profile, provider_name, purpose="cover_letter"):
        """
        Generates cover letter content using a specified GenAI provider and purpose.
        """
        logger.info(f"[GenAI Handler] Generating cover letter for job: {job_details.get('title', 'N/A')} using {provider_name} for purpose '{purpose}'.")

        active_config = self._get_active_config(provider_name, purpose)
        if not active_config:
            logger.error(f"[GenAI Handler] No active configuration found for provider '{provider_name}' and purpose '{purpose}'.")
            return f"Error: No active configuration for {provider_name} ({purpose})."

        api_key = self._get_api_key_for_provider(provider_name)
        # For Ollama, API key might not be needed if it's a local instance without auth.
        if provider_name != 'ollama' and not api_key:
            return f"Error: API key for {provider_name} not configured in environment."

        prompt = f"Generate a cover letter based on job details: {job_details} and user profile: {user_profile}"
        
        model_name = active_config.model_name
        base_url = active_config.base_url

        if provider_name == 'gemini':
            return self._call_gemini(prompt, api_key, model_name)
        elif provider_name == 'ollama':
            return self._call_ollama(prompt, base_url, model_name) # api_key might not be used by _call_ollama
        elif provider_name == 'openrouter':
            return self._call_openrouter(prompt, api_key, model_name)
        else:
            logger.error(f"[GenAI Handler - Error] Unknown provider: {provider_name}")
            return "Error: Unknown provider specified."

    def suggest_form_field_answer(self, field_label, context, user_profile, provider_name, purpose="form_fill_assist"):
        """
        Suggests an answer for a form field using a specified GenAI provider and purpose.
        """
        logger.info(f"[GenAI Handler] Suggesting answer for field: {field_label} using {provider_name} for purpose '{purpose}'.")

        active_config = self._get_active_config(provider_name, purpose)
        if not active_config:
            logger.error(f"[GenAI Handler] No active configuration found for provider '{provider_name}' and purpose '{purpose}'.")
            return f"Error: No active configuration for {provider_name} ({purpose})."

        api_key = self._get_api_key_for_provider(provider_name)
        if provider_name != 'ollama' and not api_key:
            return f"Error: API key for {provider_name} not configured in environment."

        prompt = f"Suggest an answer for the form field '{field_label}' with context: {context}, based on user profile: {user_profile}"
        
        model_name = active_config.model_name
        base_url = active_config.base_url

        if provider_name == 'gemini':
            return self._call_gemini(prompt, api_key, model_name)
        elif provider_name == 'ollama':
            return self._call_ollama(prompt, base_url, model_name)
        elif provider_name == 'openrouter':
            return self._call_openrouter(prompt, api_key, model_name)
        else:
            logger.error(f"[GenAI Handler - Error] Unknown provider: {provider_name}")
            return "Error: Unknown provider specified."

    # --- Provider-Specific Placeholder Methods ---

    def _call_gemini(self, prompt, api_key, model_name):
        """Placeholder for calling Google Gemini API."""
        if not api_key: # This check is now somewhat redundant due to the calling method's check, but good for direct calls.
            logger.error("[GenAI Handler - Gemini] API key not provided for call.")
            return "Error: Gemini API key not available for this call."
        logger.info(f"[GenAI Handler] Calling Gemini with model {model_name if model_name else 'default'}")
        # Actual API call would go here
        return f"Gemini response placeholder for prompt: '{prompt[:50]}...'"

    def _call_ollama(self, prompt, base_url, model_name):
        """Placeholder for calling local Ollama API."""
        if not base_url:
            logger.error("[GenAI Handler - Ollama] Base URL not configured.")
            return "Error: Ollama base URL not configured."
        logger.info(f"[GenAI Handler] Calling Ollama at {base_url} with model {model_name if model_name else 'default'}")
        # Actual API call would go here
        return f"Ollama response placeholder for prompt: '{prompt[:50]}...'"
            
    def _call_openrouter(self, prompt, api_key, model_name):
        """Placeholder for calling OpenRouter API."""
        if not api_key:
            logger.error("[GenAI Handler - OpenRouter] API key not provided for call.")
            return "Error: OpenRouter API key not available for this call."
        logger.info(f"[GenAI Handler] Calling OpenRouter with model {model_name if model_name else 'default'}")
        # Actual API call would go here
        return f"OpenRouter response placeholder for prompt: '{prompt[:50]}...'"

if __name__ == '__main__':
    # Example usage (for testing purposes)
    # Ensure you have environment variables like GEMINI_API_KEY, OPENROUTER_API_KEY set for this test.
    # Also, create some mock GenAIConfig objects as they would come from the DB.

    # Mock GenAIConfig objects (simulating what comes from the database)
    class MockGenAIConfig:
        def __init__(self, provider_name, purpose, model_name, base_url, is_enabled):
            self.provider_name = provider_name
            self.purpose = purpose
            self.model_name = model_name
            self.base_url = base_url
            self.is_enabled = is_enabled

    mock_db_configs = [
        MockGenAIConfig("gemini", "cover_letter", "gemini-1.5-flash", None, True),
        MockGenAIConfig("ollama", "cover_letter", "gemma:2b", "http://localhost:11434", True),
        MockGenAIConfig("openrouter", "cover_letter", "mistralai/mistral-7b-instruct", None, True),
        MockGenAIConfig("gemini", "form_fill_assist", "gemini-pro", None, True),
        MockGenAIConfig("ollama", "form_fill_assist", "llama2", "http://localhost:11434", False), # Disabled
    ]

    # Initialize handler with mock DB configurations
    # API keys are expected to be in the environment (e.g., os.environ['GEMINI_API_KEY'])
    handler = GenAIHandler(db_configs=mock_db_configs)

    job_example = {"title": "Software Engineer", "description": "Develop amazing software."}
    profile_example = {"name": "AI Enthusiast", "skills": ["Python", "AI", "Problem Solving"]}
    
    logger.info("\n--- Testing Cover Letter Generation ---")
    # Test with GEMINI_API_KEY set in your environment
    logger.info(f"Gemini: {handler.generate_cover_letter_content(job_example, profile_example, provider_name='gemini', purpose='cover_letter')}")
    logger.info(f"Ollama: {handler.generate_cover_letter_content(job_example, profile_example, provider_name='ollama', purpose='cover_letter')}")
    # Test with OPENROUTER_API_KEY set in your environment
    logger.info(f"OpenRouter: {handler.generate_cover_letter_content(job_example, profile_example, provider_name='openrouter', purpose='cover_letter')}")
    logger.info(f"Unknown Provider: {handler.generate_cover_letter_content(job_example, profile_example, provider_name='unknown_provider', purpose='cover_letter')}")
    logger.info(f"Disabled Config (Ollama form_fill): {handler.generate_cover_letter_content(job_example, profile_example, provider_name='ollama', purpose='form_fill_assist')}") # Should fail due to purpose mismatch or disabled

    logger.info("\n--- Testing Form Field Suggestion ---")
    field_label_example = "Years of experience with Python"
    context_example = "Job application for a Senior Python Developer role."
    logger.info(f"Gemini: {handler.suggest_form_field_answer(field_label_example, context_example, profile_example, provider_name='gemini', purpose='form_fill_assist')}")
    # Ollama for form_fill_assist is disabled in mock_db_configs, so this should indicate an error or no config.
    logger.info(f"Ollama (disabled): {handler.suggest_form_field_answer(field_label_example, context_example, profile_example, provider_name='ollama', purpose='form_fill_assist')}")

    # Example of how to test missing API key (ensure the respective env var is NOT set when running this)
    # logger.info("\n--- Testing Missing API Key (Gemini) ---")
    # # Temporarily unset env var for testing if possible, or run in an env where it's not set.
    # # current_gemini_key = os.environ.pop('GEMINI_API_KEY', None)
    # logger.info(handler.generate_cover_letter_content(job_example, profile_example, provider_name='gemini', purpose='cover_letter'))
    # # if current_gemini_key: os.environ['GEMINI_API_KEY'] = current_gemini_key # Restore if popped

    logger.info("\n--- Testing with a provider not in mock DB config ---")
    logger.info(f"Anthropic (not in mock): {handler.generate_cover_letter_content(job_example, profile_example, provider_name='anthropic', purpose='cover_letter')}")
