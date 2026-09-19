import os
import json
from typing import List
from dotenv import load_dotenv
import streamlit as st
import requests

load_dotenv()


def generate_with_llm(
    system_prompt: str,
    user_prompt: str,
    max_tokens: int = 512,
    provider: str = "ollama",
    json_mode: bool = False
) -> str:

    if provider == "ollama":
        try:
            payload = {
                "model": "qwen2.5-coder:7b-instruct",
                "messages": [
                    {
                        "role": "system",
                        "content": system_prompt
                    },
                    {
                        "role": "user",
                        "content": user_prompt
                    }
                ],
                "stream": False,
                "options": {
                    "temperature": 0.2,
                    "num_predict": max_tokens
                }
            }
        

            if json_mode:
                payload["format"] = "json"

            response = requests.post(
                "http://localhost:11434/api/chat",
                json=payload,
                timeout=120
            )

            response.raise_for_status()

            data = response.json()

            return data["message"]["content"]

        except requests.exceptions.RequestException as e:
            return f"[Ollama call failed: {e}]"

        except Exception as e:
            return f"[Ollama response error: {e}]"


    elif provider == "openai":

        try:
            openai_key = st.secrets.get("OPENAI_API_KEY")
        except:
            openai_key = os.environ.get("OPENAI_API_KEY")

        if not openai_key:
            return "[OpenAI not configured] Please set OPENAI_API_KEY"

        try:
            from openai import OpenAI

            client = OpenAI(
                api_key=openai_key
            )

            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": system_prompt
                    },
                    {
                        "role": "user",
                        "content": user_prompt
                    }
                ],
                max_tokens=max_tokens
            )

            return response.choices[0].message.content

        except Exception as e:
            return f"[OpenAI call failed: {e}]"

    else:
        return f"[Unknown LLM provider: {provider}]"

def build_test_case_prompt(context_chunks: List[str], user_query: str) -> str:
    joined = '\n\n---\n\n'.join(context_chunks)
    prompt = f"""You are a QA engineer. Use only the following context (do not hallucinate):

{joined}

User request: {user_query}

Return ONLY valid JSON.

The top-level JSON must be an array.

Do NOT wrap the array inside an object such as:
{{"test_cases": [...]}}

Required format:

[
  {{
    "Test_ID": "TC001",
    "Feature": "...",
    "Test_Scenario": "...",
    "Steps": ["...", "..."],
    "Expected_Result": "...",
    "Grounded_In": "checkout_requirements.md - REQ-008"
  }}
]"""
    return prompt


def build_script_prompt(
    html_content: str,
    selected_test_case: dict,
    context_chunks: List[str],
    target_url: str
) -> str:
    joined = '\n\n---\n\n'.join(context_chunks)

    prompt = f"""You are a Selenium (Python) expert. Use only the provided HTML and context to generate a runnable Selenium Python script that implements this test case.

Target page:
{target_url}

HTML:
{html_content}

Context:
{joined}

Test case JSON:
{json.dumps(selected_test_case, indent=2)}

Requirements:
- Use webdriver.Chrome() and Selenium best practices such as explicit waits
- Use selectors that actually exist in the provided HTML
- The script must open this exact target using:
  driver.get("{target_url}")
- Do not use placeholder paths such as file:///path/to/file.html
- The script should be runnable as 'python script.py'
- Include assertions that verify the expected result of the test case
- Always close the browser using driver.quit()

STRICT AUTOMATION GROUNDING RULES:

- Use ONLY UI elements, selectors, and behavior supported by the
  provided target application content and retrieved requirements.

- Never invent IDs, classes, buttons, fields, error containers,
  messages, or application behavior.

- Selectors used in the generated Selenium script must be supported
  by the provided application structure.

- Do not assume validation or workflows that are not documented
  in the requirements or visible in the target application.

- If a selected test case requires behavior that is not supported
  by the available application evidence, do not fabricate elements
  or expected behavior.

TEST CASE GROUNDING RULES:

- Each test case should verify one clear requirement or one closely related group of requirements.

- Every step must be necessary to test the requirement listed in Grounded_In.

- Do not add unrelated setup actions from other requirements unless they are required for the test scenario.

- Expected_Result must be directly supported by the requirement(s) listed in Grounded_In.

- Do not infer additional expected behavior that is not explicitly stated in the cited requirement.

- If a test is grounded only in REQ-004, do not include behavior from unrelated requirements such as customer validation, payment processing, or shipping.

- Prefer the minimum number of steps necessary to verify the requirement.

GROUNDING:

- Every test case must identify where its expected behavior came from.
- Grounded_In must include the source filename from the retrieved context.
- If a requirement ID such as REQ-008 is explicitly visible in the retrieved context, include it as well.
- Never invent a requirement ID that is not present in the retrieved context.
- If no requirement ID is visible, cite only the source filename.

Return only the Python script with no explanation."""
    return prompt