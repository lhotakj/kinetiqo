"""Safe normalized errors exposed by the chat feature."""


class ChatError(Exception):
    error_code = "chat_error"
    user_message = "Chat could not complete. Please try again."

    def __init__(self, message: str | None = None):
        super().__init__(message or self.user_message)
        if message:
            self.user_message = message


class ChatConfigurationError(ChatError):
    error_code = "configuration_error"
    user_message = "Configure a Gemini API key in Settings before using chat."


class ChatAuthenticationError(ChatError):
    error_code = "provider_authentication_error"
    user_message = "The provider rejected the configured API key."


class ChatRateLimitError(ChatError):
    error_code = "rate_limited"
    user_message = "The provider rate limit was reached. Please try again shortly."


class ChatTimeoutError(ChatError):
    error_code = "provider_timeout"
    user_message = "The provider took too long to respond."


class ChatProviderUnavailableError(ChatError):
    error_code = "provider_unavailable"
    user_message = "The provider is currently unavailable. Please try again later."


class ChatProviderResponseError(ChatError):
    error_code = "provider_response_error"
    user_message = "The provider returned an unexpected response."


class ChatContextLimitError(ChatError):
    error_code = "context_limit"
    user_message = "This conversation is too large to send. Start a new chat."


class ChatCancelledError(ChatError):
    error_code = "cancelled"
    user_message = "Generation was stopped."


class ChatSafetyBlockedError(ChatError):
    error_code = "safety_blocked"
    user_message = "The provider withheld this response for safety reasons."

