"""LLM executor abstraction for making Claude API calls.

This module provides an abstraction layer for executing LLM queries with different
implementations including Anthropic's Claude API and mock executors for testing.
"""

import logging
import re
from abc import ABC, abstractmethod
from typing import Dict, Optional

import anthropic

logger = logging.getLogger(__name__)


class LLMExecutor(ABC):
    """Abstract base class for LLM executors."""

    @abstractmethod
    def execute(self, prompt: str, system: Optional[str] = None) -> str:
        """Execute an LLM query with the given prompt.

        Args:
            prompt: The user prompt to send to the LLM
            system: Optional system prompt to guide the LLM's behavior

        Returns:
            The LLM's response text

        Raises:
            Exception: If the LLM execution fails
        """
        pass

    @abstractmethod
    def estimate_tokens(self, text: str) -> int:
        """Estimate the number of tokens in the given text.

        Args:
            text: The text to estimate tokens for

        Returns:
            Estimated number of tokens
        """
        pass


class AnthropicExecutor(LLMExecutor):
    """Executor for Anthropic's Claude API."""

    def __init__(
        self,
        model: str = "claude-sonnet-4-20250514",
        max_tokens: int = 4096,
        api_key: Optional[str] = None,
    ):
        """Initialize the Anthropic executor.

        Args:
            model: The Claude model to use (default: claude-sonnet-4-20250514)
            max_tokens: Maximum tokens in the response (default: 4096)
            api_key: Optional API key (uses ANTHROPIC_API_KEY env var if not provided)
        """
        self.model = model
        self.max_tokens = max_tokens
        self.input_tokens = 0
        self.output_tokens = 0

        # Initialize the Anthropic client
        if api_key:
            self.client = anthropic.Anthropic(api_key=api_key)
        else:
            self.client = anthropic.Anthropic()  # Uses ANTHROPIC_API_KEY env var

        logger.info(f"Initialized AnthropicExecutor with model={model}, max_tokens={max_tokens}")

    def execute(self, prompt: str, system: Optional[str] = None) -> str:
        """Execute a Claude API call with the given prompt.

        Args:
            prompt: The user prompt to send to Claude
            system: Optional system prompt to guide Claude's behavior

        Returns:
            Claude's response text

        Raises:
            anthropic.APIError: If the API call fails
        """
        try:
            logger.debug(f"Executing prompt (length: {len(prompt)} chars)")

            # Build the API call parameters
            api_params = {
                "model": self.model,
                "max_tokens": self.max_tokens,
                "messages": [{"role": "user", "content": prompt}],
            }

            # Add system prompt if provided
            if system:
                api_params["system"] = system
                logger.debug(f"Using system prompt (length: {len(system)} chars)")

            # Make the API call
            message = self.client.messages.create(**api_params)

            # Extract the response text
            response_text = message.content[0].text

            # Track token usage
            self.input_tokens = message.usage.input_tokens
            self.output_tokens = message.usage.output_tokens

            logger.info(
                f"API call successful - Input tokens: {self.input_tokens}, "
                f"Output tokens: {self.output_tokens}"
            )
            logger.debug(f"Response length: {len(response_text)} chars")

            return response_text

        except anthropic.APIError as e:
            logger.error(f"Anthropic API error: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error during LLM execution: {e}")
            raise

    def estimate_tokens(self, text: str) -> int:
        """Estimate the number of tokens in the given text.

        Uses a simple heuristic: approximately 4 characters per token.
        This is a rough estimate and may not be perfectly accurate.

        Args:
            text: The text to estimate tokens for

        Returns:
            Estimated number of tokens
        """
        # Simple heuristic: ~4 characters per token
        # This is a rough estimate for English text
        estimated = len(text) // 4
        logger.debug(f"Estimated {estimated} tokens for text of length {len(text)}")
        return estimated

    def parse_yaml_response(self, response: str) -> Dict:
        """Extract YAML content from markdown code blocks in the response.

        Looks for YAML content within ```yaml or ```yml code blocks.

        Args:
            response: The LLM response text

        Returns:
            Parsed YAML as a dictionary

        Raises:
            ValueError: If no YAML code block is found or YAML parsing fails
        """
        import yaml

        logger.debug("Parsing YAML from response")

        # Try to find YAML in markdown code blocks
        yaml_pattern = r"```(?:yaml|yml)\s*\n(.*?)\n```"
        matches = re.findall(yaml_pattern, response, re.DOTALL | re.IGNORECASE)

        if not matches:
            logger.warning("No YAML code block found in response")
            # Try parsing the entire response as YAML
            try:
                parsed = yaml.safe_load(response)
                logger.info("Successfully parsed entire response as YAML")
                return parsed
            except yaml.YAMLError as e:
                logger.error(f"Failed to parse response as YAML: {e}")
                raise ValueError(f"No YAML code block found and response is not valid YAML: {e}")

        # Use the first YAML block found
        yaml_content = matches[0]
        logger.debug(f"Found YAML block (length: {len(yaml_content)} chars)")

        try:
            parsed = yaml.safe_load(yaml_content)
            logger.info("Successfully parsed YAML from code block")
            return parsed
        except yaml.YAMLError as e:
            logger.error(f"Failed to parse YAML content: {e}")
            raise ValueError(f"Invalid YAML in code block: {e}")

    def get_token_usage(self) -> Dict[str, int]:
        """Get the token usage from the last API call.

        Returns:
            Dictionary with 'input_tokens' and 'output_tokens' keys
        """
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
        }


class SubagentExecutor(LLMExecutor):
    """
    Executor that spawns Claude Code subagents for expert tasks.

    This executor is designed to be called from within Claude Code,
    where it will spawn Task agents for each expert query. The results
    are collected and returned.

    Usage:
        executor = SubagentExecutor(expert_type="creative")
        result = executor.execute(prompt, system)
    """

    def __init__(self, expert_type: str = "general-purpose", output_dir: Optional[str] = None):
        """Initialize the subagent executor.

        Args:
            expert_type: The type of expert agent to spawn
            output_dir: Directory to save agent outputs
        """
        self.expert_type = expert_type
        self.output_dir = output_dir
        self.call_count = 0
        self.last_prompt = None
        self.last_system = None
        self.pending_prompts = []  # Queue of prompts to execute
        self.results = []  # Results from executed prompts

        logger.info(f"Initialized SubagentExecutor for expert_type={expert_type}")

    def queue_prompt(self, prompt: str, system: Optional[str] = None, expert_name: str = "expert") -> int:
        """Queue a prompt for execution by a subagent.

        Args:
            prompt: The prompt to send to the subagent
            system: Optional system prompt for context
            expert_name: Name of the expert for logging

        Returns:
            Index of the queued prompt
        """
        self.pending_prompts.append({
            "prompt": prompt,
            "system": system,
            "expert_name": expert_name,
            "index": len(self.pending_prompts)
        })
        logger.info(f"Queued prompt {len(self.pending_prompts)-1} for {expert_name}")
        return len(self.pending_prompts) - 1

    def get_pending_prompts(self) -> list:
        """Get all pending prompts that need to be executed as subagents.

        Returns:
            List of pending prompt dictionaries
        """
        return self.pending_prompts

    def set_result(self, index: int, result: str) -> None:
        """Set the result for a completed subagent execution.

        Args:
            index: Index of the prompt that was executed
            result: The result from the subagent
        """
        while len(self.results) <= index:
            self.results.append(None)
        self.results[index] = result
        logger.info(f"Set result for prompt {index}")

    def execute(self, prompt: str, system: Optional[str] = None) -> str:
        """Queue a prompt and return a placeholder.

        In subagent mode, this queues the prompt for external execution.
        The actual result must be set via set_result() after the subagent completes.

        Args:
            prompt: The user prompt
            system: Optional system prompt

        Returns:
            Placeholder string indicating the prompt was queued
        """
        self.call_count += 1
        self.last_prompt = prompt
        self.last_system = system

        index = self.queue_prompt(prompt, system, self.expert_type)
        return f"[SUBAGENT_PENDING:{index}:{self.expert_type}]"

    def estimate_tokens(self, text: str) -> int:
        """Estimate tokens (same as other executors)."""
        return len(text) // 4

    def get_queued_count(self) -> int:
        """Get number of queued prompts."""
        return len(self.pending_prompts)

    def clear_queue(self) -> None:
        """Clear the pending prompts queue."""
        self.pending_prompts = []
        self.results = []


class MockExecutor(LLMExecutor):
    """Mock executor for testing purposes."""

    def __init__(self, response_map: Optional[Dict[str, str]] = None, default_response: str = "Mock response"):
        """Initialize the mock executor.

        Args:
            response_map: Optional dictionary mapping prompt substrings to responses
            default_response: Default response if no mapping matches
        """
        self.response_map = response_map or {}
        self.default_response = default_response
        self.call_count = 0
        self.last_prompt = None
        self.last_system = None

        logger.info("Initialized MockExecutor")

    def execute(self, prompt: str, system: Optional[str] = None) -> str:
        """Execute a mock LLM call.

        Args:
            prompt: The user prompt (checked against response_map)
            system: Optional system prompt (stored but not used)

        Returns:
            A mock response based on the response_map or default_response
        """
        self.call_count += 1
        self.last_prompt = prompt
        self.last_system = system

        logger.debug(f"Mock execution #{self.call_count} (prompt length: {len(prompt)} chars)")

        # Check if any key in response_map is a substring of the prompt
        for key, response in self.response_map.items():
            if key in prompt:
                logger.debug(f"Matched response map key: '{key}'")
                return response

        logger.debug("Using default response")
        return self.default_response

    def estimate_tokens(self, text: str) -> int:
        """Estimate the number of tokens in the given text.

        Uses the same heuristic as AnthropicExecutor for consistency.

        Args:
            text: The text to estimate tokens for

        Returns:
            Estimated number of tokens
        """
        estimated = len(text) // 4
        logger.debug(f"Estimated {estimated} tokens for text of length {len(text)}")
        return estimated

    def get_call_count(self) -> int:
        """Get the number of times execute was called.

        Returns:
            The call count
        """
        return self.call_count

    def get_last_call(self) -> Dict[str, Optional[str]]:
        """Get the parameters from the last execute call.

        Returns:
            Dictionary with 'prompt' and 'system' keys
        """
        return {
            "prompt": self.last_prompt,
            "system": self.last_system,
        }


__all__ = [
    "LLMExecutor",
    "AnthropicExecutor",
    "SubagentExecutor",
    "MockExecutor",
]
