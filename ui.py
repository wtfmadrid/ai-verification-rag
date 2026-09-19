import json
import subprocess
import sys
import time
from pathlib import Path

import requests
import streamlit as st

from parser_utils import parse_file_to_text
from rag_agent import (
    build_test_case_prompt,
    build_script_prompt,
    generate_with_llm,
)
from vectorstore import VectorStore


# =========================================================
# PATHS
# =========================================================

BASE = Path(__file__).parent

UPLOAD_DIR = BASE / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

GENERATED_TESTS_DIR = BASE / "generated_tests"
GENERATED_TESTS_DIR.mkdir(exist_ok=True)


# =========================================================
# STREAMLIT CONFIG
# =========================================================

st.set_page_config(
    page_title="RAG QA Agent",
    page_icon="🤖",
    layout="wide",
)


# =========================================================
# SESSION STATE
# =========================================================

if "vector_store" not in st.session_state:
    st.session_state.vector_store = VectorStore()

if "test_cases" not in st.session_state:
    st.session_state.test_cases = []

if "context_chunks" not in st.session_state:
    st.session_state.context_chunks = []

if "generated_scripts" not in st.session_state:
    st.session_state.generated_scripts = {}


# =========================================================
# HELPER FUNCTIONS
# =========================================================

def clean_llm_code(script: str) -> str:
    """Remove Markdown code fences from generated Python code."""

    script_clean = script.strip()

    if script_clean.startswith("```python"):
        script_clean = script_clean[9:]

    elif script_clean.startswith("```"):
        script_clean = script_clean[3:]

    if script_clean.endswith("```"):
        script_clean = script_clean[:-3]

    return script_clean.strip()


def load_target_content(target_input: str):
    """
    Load HTML from either:
    - a URL
    - a local HTML file

    Returns:
        html_content
        selenium_target
    """

    clean_target = (
        target_input
        .strip()
        .strip('"')
        .strip("'")
    )

    if clean_target.startswith(("http://", "https://")):
        response = requests.get(
            clean_target,
            timeout=10,
        )

        response.raise_for_status()

        return response.text, clean_target

    target_path = (
        Path(clean_target)
        .expanduser()
        .resolve()
    )

    html_content = target_path.read_text(
        encoding="utf-8"
    )

    # Converts:
    #
    # D:\Projects\...\checkout.html
    #
    # into:
    #
    # file:///D:/Projects/.../checkout.html
    selenium_target = target_path.as_uri()

    return html_content, selenium_target


def run_selenium_test(
    saved_script: str,
    test_index: int,
):
    """Save and execute a generated Selenium test."""

    script_path = (
        GENERATED_TESTS_DIR
        / f"test_case_{test_index + 1}.py"
    )

    script_path.write_text(
        saved_script,
        encoding="utf-8",
    )

    start_time = time.perf_counter()

    try:
        with st.spinner("Running Selenium test..."):
            result = subprocess.run(
                [
                    sys.executable,
                    str(script_path),
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )

        execution_time = (
            time.perf_counter()
            - start_time
        )

        error_output = result.stderr or ""

        # -------------------------------------------------
        # PASS
        # -------------------------------------------------

        if result.returncode == 0:
            st.success(
                f"✅ TEST PASSED — "
                f"{execution_time:.2f} seconds"
            )

        # -------------------------------------------------
        # FAILED EXECUTION
        # -------------------------------------------------

        else:
            if "AssertionError" in error_output:
                st.error(
                    f"❌ VERIFICATION FAILED — "
                    f"{execution_time:.2f} seconds"
                )

                st.info(
                    "The test completed, but the observed "
                    "application behavior did not match "
                    "the expected result."
                )

            else:
                st.warning(
                    f"⚠️ AUTOMATION ERROR — "
                    f"{execution_time:.2f} seconds"
                )

                st.info(
                    "The generated Selenium test could not "
                    "complete successfully. This may be caused "
                    "by an unsupported generated scenario, "
                    "invalid selector, missing element, browser "
                    "issue, or application timing problem."
                )

        # -------------------------------------------------
        # STDOUT
        # -------------------------------------------------

        if result.stdout:
            st.subheader("Console Output")
            st.code(result.stdout)

        # -------------------------------------------------
        # STDERR
        # -------------------------------------------------

        if error_output:
            st.subheader("Error Output")
            st.code(error_output)

    except subprocess.TimeoutExpired:
        execution_time = (
            time.perf_counter()
            - start_time
        )

        st.error(
            "⏱️ TEST TIMEOUT — "
            "exceeded 30 seconds "
            f"({execution_time:.2f}s)"
        )

    except Exception as e:
        st.error(
            f"Execution error: {e}"
        )


# =========================================================
# PAGE TITLE
# =========================================================

st.title("🤖 RAG-Based QA Agent")


# =========================================================
# SIDEBAR - DOCUMENT INGESTION
# =========================================================

st.sidebar.header("📁 Document Upload")

uploaded_files = st.sidebar.file_uploader(
    "Upload documents",
    type=[
        "txt",
        "md",
        "json",
        "pdf",
        "html",
        "htm",
    ],
    accept_multiple_files=True,
)


if uploaded_files:
    if st.sidebar.button("Ingest Documents"):
        with st.spinner(
            "Processing documents..."
        ):
            docs = []

            for file in uploaded_files:
                save_path = (
                    UPLOAD_DIR
                    / file.name
                )

                with open(
                    save_path,
                    "wb",
                ) as f:
                    f.write(
                        file.getbuffer()
                    )

                text = parse_file_to_text(
                    str(save_path)
                )

                docs.append(
                    {
                        "text": text,
                        "meta": {
                            "source": file.name
                        },
                    }
                )

            st.session_state.vector_store.ingest_documents(
                docs
            )

            st.sidebar.success(
                f"Ingested {len(docs)} documents!"
            )


# =========================================================
# TEST CASE GENERATION
# =========================================================

st.header("Generate Test Cases")

user_query = st.text_area(
    "Enter your test case requirements:",
    placeholder=(
        "e.g., Generate 7 test cases for "
        "checkout functionality"
    ),
)


col1, col2 = st.columns(
    [1, 1]
)


with col1:
    top_k = st.slider(
        "Number of context chunks",
        1,
        10,
        5,
    )


with col2:
    max_tokens = st.slider(
        "Max tokens for generation",
        256,
        2048,
        1024,
    )


if st.button(
    "Generate Test Cases",
    type="primary",
):

    if not user_query:
        st.warning(
            "Please enter a query"
        )

    else:
        # -------------------------------------------------
        # RETRIEVE CONTEXT
        # -------------------------------------------------

        with st.spinner(
            "Searching knowledge base..."
        ):
            results = (
                st.session_state
                .vector_store
                .search(
                    user_query,
                    top_k=top_k,
                )
            )

            st.session_state.context_chunks = [
                (
                    f"SOURCE: {r.get('meta', {}).get('source', 'unknown')}\n"
                    f"CONTENT:\n{r['document']}"
                )
                for r in results
            ]

        # -------------------------------------------------
        # GENERATE TEST CASES
        # -------------------------------------------------

        with st.spinner(
            "Generating test cases..."
        ):
            prompt = build_test_case_prompt(
                st.session_state.context_chunks,
                user_query,
            )

            response = generate_with_llm(
                "You are a QA test case generator.",
                prompt,
                max_tokens,
                json_mode=True,
            )

        st.subheader("LLM Output")

        st.text_area(
            "Raw Response:",
            response,
            height=300,
        )

        # -------------------------------------------------
        # PARSE JSON RESPONSE
        # -------------------------------------------------

        try:
            response_clean = (
                response.strip()
            )

            if response_clean.startswith(
                "```json"
            ):
                response_clean = (
                    response_clean[7:]
                )

            elif response_clean.startswith(
                "```"
            ):
                response_clean = (
                    response_clean[3:]
                )

            if response_clean.endswith(
                "```"
            ):
                response_clean = (
                    response_clean[:-3]
                )

            response_clean = (
                response_clean.strip()
            )

            parsed_response = json.loads(
                response_clean
            )

            # Direct JSON array
            if isinstance(
                parsed_response,
                list,
            ):
                test_cases = (
                    parsed_response
                )

            # Wrapped:
            # {"test_cases": [...]}
            elif (
                isinstance(
                    parsed_response,
                    dict,
                )
                and "test_cases"
                in parsed_response
                and isinstance(
                    parsed_response[
                        "test_cases"
                    ],
                    list,
                )
            ):
                test_cases = (
                    parsed_response[
                        "test_cases"
                    ]
                )

            # Single test-case object
            else:
                test_cases = [
                    parsed_response
                ]

            st.session_state.test_cases = (
                test_cases
            )

            # Remove scripts belonging to
            # an older set of test cases
            st.session_state.generated_scripts = {}

            st.success(
                f"✅ Generated "
                f"{len(test_cases)} "
                f"test case(s)!"
            )

        except json.JSONDecodeError as e:
            st.error(
                "Failed to parse test cases "
                f"as JSON: {e}"
            )


# =========================================================
# GENERATED TEST CASES
# =========================================================

if st.session_state.test_cases:

    st.header(
        "📋 Generated Test Cases"
    )

    # -----------------------------------------------------
    # TARGET ENTERED ONCE
    # -----------------------------------------------------

    st.subheader(
        "🎯 Target Application"
    )

    target_input = st.text_input(
        "Enter target page URL or local HTML file path:",
        key="selenium_target",
        placeholder=(
            "https://example.com/checkout "
            "or D:/path/to/checkout.html"
        ),
    )

    # -----------------------------------------------------
    # EACH TEST CASE
    # -----------------------------------------------------

    for idx, tc in enumerate(
        st.session_state.test_cases
    ):

        test_title = tc.get(
            "Test_Scenario",
            "N/A",
        )

        with st.expander(
            (
                f"Test Case {idx + 1}: "
                f"{test_title}"
            ),
            expanded=False,
        ):

            st.json(tc)

            # =============================================
            # GENERATE SELENIUM SCRIPT
            # =============================================

            st.subheader(
                "Generate Selenium Script"
            )

            if st.button(
                "🔧 Generate Selenium Script",
                key=f"gen_script_{idx}",
            ):

                if not target_input:
                    st.warning(
                        "Please enter a target URL "
                        "or HTML file path above"
                    )

                else:
                    try:
                        # ---------------------------------
                        # LOAD TARGET CONTENT
                        # ---------------------------------

                        with st.spinner(
                            "Fetching target content..."
                        ):
                            (
                                html_content,
                                selenium_target,
                            ) = load_target_content(
                                target_input
                            )

                        # ---------------------------------
                        # GENERATE SCRIPT
                        # ---------------------------------

                        with st.spinner(
                            "Generating Selenium script..."
                        ):
                            script_prompt = (
                                build_script_prompt(
                                    html_content,
                                    tc,
                                    st.session_state.context_chunks,
                                    selenium_target,
                                )
                            )

                            script = (
                                generate_with_llm(
                                    (
                                        "You are a Selenium "
                                        "automation expert."
                                    ),
                                    script_prompt,
                                    2048,
                                )
                            )

                            script_clean = (
                                clean_llm_code(
                                    script
                                )
                            )

                            st.session_state.generated_scripts[
                                idx
                            ] = script_clean

                        st.success(
                            "✅ Script generated successfully!"
                        )

                    except (
                        requests.exceptions
                        .RequestException
                    ) as e:
                        st.error(
                            f"Error fetching URL: {e}"
                        )

                    except FileNotFoundError:
                        st.error(
                            "Target file was not found."
                        )

                    except Exception as e:
                        st.error(
                            f"Error: {e}"
                        )

            # =============================================
            # DISPLAY SAVED SCRIPT
            # =============================================

            if (
                idx
                in st.session_state.generated_scripts
            ):

                saved_script = (
                    st.session_state
                    .generated_scripts[idx]
                )

                st.subheader(
                    "Generated Selenium Script"
                )

                st.code(
                    saved_script,
                    language="python",
                )

                st.download_button(
                    "⬇️ Download Script",
                    saved_script,
                    file_name=(
                        f"test_case_{idx + 1}.py"
                    ),
                    mime="text/x-python",
                    key=f"saved_download_{idx}",
                )

                # =========================================
                # RUN TEST
                # =========================================

                st.subheader(
                    "Run Selenium Test"
                )

                if st.button(
                    "▶️ Run Test",
                    key=f"run_test_{idx}",
                ):
                    run_selenium_test(
                        saved_script,
                        idx,
                    )


# =========================================================
# SIDEBAR FOOTER
# =========================================================

st.sidebar.markdown("---")

st.sidebar.info(
    "Upload documents → "
    "Generate test cases → "
    "Generate Selenium scripts → "
    "Run tests"
)