import requests
import logging
import time
import uuid
import yaml

logger = logging.getLogger("LLMConverter")


# ==========================================
# 🔧 PROMPT LOADER
# ==========================================
def load_prompt(prompt_obj):
    if isinstance(prompt_obj, dict):
        return prompt_obj

    if isinstance(prompt_obj, str):
        with open(prompt_obj, "r") as f:
            return yaml.safe_load(f)

    raise ValueError("Invalid prompt input")


# ==========================================
# 🔧 ISSUE FORMATTER
# ==========================================
def format_issues(issues):
    if not issues:
        return "None"

    formatted = []
    for i in issues:
        formatted.append(
            f"[{i.get('severity')}] {i.get('category')} → {i.get('message')}"
        )
    return "\n".join(formatted)


# ==========================================
# 🔧 MAIN ENGINE
# ==========================================
class LLMConverter:
    DEFAULT_MODEL = "databricks-claude-sonnet-4-6"
    DEFAULT_MAX_RETRIES = 3
    DEFAULT_TIMEOUT = 300
    DEFAULT_MAX_TOKENS = 12000
    
    def __init__(self,
        api_key: str,
        endpoint: str,
        model: str | None = None,
        max_retries: int | None = None,
        timeout: int | None = None,
        max_tokens: int | None = None) :

        self.api_key = api_key
        self.endpoint = endpoint
        self.session = requests.Session()
        # Use passed values OR fallback to defaults
        self.model = model or self.DEFAULT_MODEL
        self.MAX_RETRIES = max_retries or self.DEFAULT_MAX_RETRIES
        self.TIMEOUT = timeout or self.DEFAULT_TIMEOUT
        self.max_tokens = max_tokens or self.DEFAULT_MAX_TOKENS

    # ==========================================
    # 🔧 BUILD PROMPT
    # ==========================================
    def build_prompt(self, prompt_config, code, issues=None):

        if "template" not in prompt_config:
            raise ValueError("Prompt config missing 'template'")

        issue_text = format_issues(issues)

        return prompt_config["template"].format(
            code=code,
            issues=issue_text
        )

    # ==========================================
    # 🔧 CALL LLM
    # ==========================================
    def call_llm(self, system_prompt, user_prompt):

        payload = {
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0,
            "max_tokens": self.max_tokens
        }

        # optional model (for Databricks endpoints)
        if self.model:
            payload["model"] = self.model

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        request_id = str(uuid.uuid4())
        start = time.time()

        for attempt in range(self.MAX_RETRIES):
            try:
                response = self.session.post(
                    self.endpoint,
                    headers=headers,
                    json=payload,
                    timeout=self.TIMEOUT
                )

                response.raise_for_status()
                result = response.json()

                # ---- response safety ----
                if "choices" not in result:
                    raise ValueError(f"Invalid LLM response: {result}")

                output = result["choices"][0]["message"]["content"]

                if not output.strip():
                    raise ValueError("Empty LLM response")

                latency = round(time.time() - start, 2)
                logger.info(f"[{request_id}] LLM latency: {latency}s")

                return output.strip()

            except Exception as e:
                logger.warning(f"[{request_id}] Retry {attempt+1}: {e}")
                time.sleep(2 ** attempt)

        raise Exception("LLM call failed after retries")

    # ==========================================
    # 🔧 SAFE CONVERT (MAIN ENTRY)
    # ==========================================
    def code_convert_llm(
        self,
        code: str,
        prompt,
        issues: list | None = None,
        fallback: bool = True
    ):
        """
        Enhancement mode:
        - uses issues to improve SQL
        - falls back to original code on failure
        """

        try:
            prompt_config = load_prompt(prompt)

            system_prompt = f"""{prompt_config.get('system', '')}
                                STRICT RULES:{prompt_config.get('rules', '')}"""

            user_prompt = self.build_prompt(
                prompt_config,
                code,
                issues
            )

            llm_output = self.call_llm(system_prompt, user_prompt)

            # ---- basic safety: avoid total corruption ----
            if len(llm_output) < 5:
                logger.warning("LLM output too small, using fallback")
                return code if fallback else llm_output

            return llm_output

        except Exception as e:
            logger.error(f"LLM conversion failed: {e}")

            if fallback:
                return code

            raise