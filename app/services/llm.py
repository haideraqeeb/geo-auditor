import json
import time
import logging
from pathlib import Path
from typing import Type
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from openai import OpenAI
from pydantic import BaseModel

from config import settings

logger = logging.getLogger(__name__)


class LLMService:
    """
    Handles all LLM interactions for the GEO Auditor.
    """

    def __init__(self):
        self.client = OpenAI(
            api_key=settings.OPENAI_API_KEY
        )

        self.model = settings.OPENAI_MODEL
        self.temperature = settings.OPENAI_TEMPERATURE
        self.max_retries = settings.OPENAI_MAX_RETRIES

        self._prompt_cache = {}

    def evaluate(
        self,
        prompt_name: str,
        input_data: dict,
        response_model: Type[BaseModel],
    ):
        """
        Runs an evaluator prompt and returns a validated
        Pydantic response.
        """

        prompt = self._load_prompt(prompt_name)

        messages = self._build_messages(prompt, input_data)

        # Per-call timeout (seconds). Use settings if available, else default to 30s.
        request_timeout = getattr(settings, "OPENAI_REQUEST_TIMEOUT", 180)

        for attempt in range(self.max_retries):
            attempt_idx = attempt + 1
            start_time = time.time()
            try:
                logger.info(
                    "LLM evaluate attempt %d/%d for prompt '%s' (timeout=%ds)",
                    attempt_idx,
                    self.max_retries,
                    prompt_name,
                    request_timeout,
                )

                # Log approximate token size of the input (rough estimate)
                try:
                    import tiktoken

                    enc = tiktoken.get_encoding("cl100k_base")
                    input_text = "\n".join(m["content"] for m in messages)
                    approx_input_tokens = len(enc.encode(input_text))
                    logger.debug("Approx input tokens for prompt '%s': %d", prompt_name, approx_input_tokens)
                except Exception:
                    approx_input_tokens = None
                    logger.debug("tiktoken not available; skipping token estimate for prompt '%s'", prompt_name)

                # Run the network call in a separate thread so we can enforce a timeout
                with ThreadPoolExecutor(max_workers=1) as ex:
                    future = ex.submit(
                        self.client.responses.parse,
                        model=self.model,
                        input=messages,
                        text_format=response_model,
                    )

                    try:
                        response = future.result(timeout=request_timeout)
                    except FutureTimeout:
                        logger.warning(
                            "LLM evaluate timed out after %ds on attempt %d for prompt '%s'",
                            request_timeout,
                            attempt_idx,
                            prompt_name,
                        )
                        # allow retry to happen below after backoff
                        raise

                # If we got here, we have a response. Log timing and usage info.
                recv_time = time.time()
                elapsed_ms = int((recv_time - start_time) * 1000)

                resp_id = getattr(response, "id", "<unknown>")
                logger.info(
                    "LLM evaluate success for prompt '%s' (response id=%s) in %dms",
                    prompt_name,
                    resp_id,
                    elapsed_ms,
                )

                # Log usage/token counts if available
                try:
                    usage = getattr(response, "usage", None) or getattr(response, "_raw", None,)
                    if usage:
                        logger.debug("LLM response usage for %s: %s", prompt_name, usage)
                except Exception:
                    logger.debug("Could not read usage metadata from response for %s", prompt_name)

                # If the SDK returns output_parsed, measure parse timing
                parsed = getattr(response, "output_parsed", None)
                if parsed is not None:
                    parse_elapsed_ms = int((time.time() - recv_time) * 1000)
                    logger.debug(
                        "LLM response parsed for prompt '%s' in %dms; total %dms",
                        prompt_name,
                        parse_elapsed_ms,
                        elapsed_ms + parse_elapsed_ms,
                    )
                    return parsed

                return response

            except FutureTimeout:
                # apply backoff before next retry
                backoff = min(2 ** attempt, 60)
                logger.info("Backing off %ds before retrying (attempt %d)", backoff, attempt_idx)
                time.sleep(backoff)
                if attempt == self.max_retries - 1:
                    logger.error("LLM evaluate exhausted retries (timeout) for prompt '%s'", prompt_name)
                    raise
            except Exception as exc:
                logger.warning(
                    "LLM evaluate failed attempt %d/%d for prompt '%s': %s",
                    attempt_idx,
                    self.max_retries,
                    prompt_name,
                    exc,
                )

                # if last attempt, raise; otherwise backoff then retry
                if attempt == self.max_retries - 1:
                    logger.error("LLM evaluate exhausted retries for prompt '%s'", prompt_name)
                    raise
                backoff = min(2 ** attempt, 60)
                logger.info("Backing off %ds before retrying (attempt %d)", backoff, attempt_idx)
                time.sleep(backoff)

    def _load_prompt(
        self,
        prompt_name: str,
    ) -> str:
        """
        Loads and caches prompts.
        """

        if prompt_name in self._prompt_cache:
            return self._prompt_cache[prompt_name]

        prompt_path = (
            Path(__file__).parent.parent
            / "prompts"
            / f"{prompt_name}.md"
        )

        prompt = prompt_path.read_text(
            encoding="utf-8"
        )

        self._prompt_cache[prompt_name] = prompt

        return prompt

    def _build_messages(
        self,
        prompt: str,
        input_data: dict,
    ):
        """
        Constructs OpenAI messages.
        """

        return [
            {
                "role": "system",
                "content": prompt,
            },
            {
                "role": "user",
                "content": json.dumps(
                    input_data,
                    indent=2,
                    ensure_ascii=False,
                ),
            },
        ]