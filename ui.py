import streamlit as st
import requests
import json
from pathlib import Path
from parser_utils import parse_file_to_text
from rag_agent import (
    build_test_case_prompt,
    generate_with_llm,
    build_script_prompt
)
from vectorstore import VectorStore
import subprocess
import sys
import time


# ---------------------------------------------------------
# Paths
# ---------------------------------------------------------

BASE = Path(__file__).parent

UPLOAD_DIR = BASE / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

GENERATED_TESTS_DIR = BASE / "generated_tests"
GENERATED_TESTS_DIR.mkdir(exist_ok=True)


# ---------------------------------------------------------
# Streamlit configuration
# ---------------------------------------------------------

st.set_page_config(
    page_title="RAG Test Case Generator",
    page_icon="🤖",
    layout="wide"
)


# ---------------------------------------------------------
# Session state initialization
# ---------------------------------------------------------

if "vector_store" not in st.session_state:
    st.session_state.vector_store = VectorStore()

if "test_cases" not in st.session_state:
    st.session_state.test_cases = []

if "context_chunks" not in st.session_state:
    st.session_state.context_chunks = []

if "generated_scripts" not in st.session_state:
    st.session_state.generated_scripts = {}


# ---------------------------------------------------------
# Page title
# ---------------------------------------------------------

st.title("🤖 RAG-Based Test Case Generator")


# =========================================================
# SIDEBAR - DOCUMENT INGESTION
# =========================================================

st.sidebar.header("📁 Document Upload")

uploaded_files = st.sidebar.file_uploader(
    "Upload documents",
    type=["txt", "md", "json", "pdf", "html", "htm"],
    accept_multiple_files=True
)


if uploaded_files:

    if st.sidebar.button("Ingest Documents"):

        with st.spinner("Processing documents..."):

            docs = []

            for file in uploaded_files:

                save_path = UPLOAD_DIR / file.name

                with open(save_path, "wb") as f:
                    f.write(file.getbuffer())

                text = parse_file_to_text(str(save_path))

                docs.append(
                    {
                        "text": text,
                        "meta": {
                            "source": file.name
                        }
                    }
                )

            st.session_state.vector_store.ingest_documents(docs)

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
        "e.g., Generate test cases for checkout functionality "
        "with valid and invalid inputs"
    )
)


col1, col2 = st.columns([1, 1])

with col1:

    top_k = st.slider(
        "Number of context chunks",
        1,
        10,
        5
    )


with col2:

    max_tokens = st.slider(
        "Max tokens for generation",
        256,
        2048,
        1024
    )


if st.button(
    "Generate Test Cases",
    type="primary"
):

    if not user_query:

        st.warning(
            "Please enter a query"
        )

    else:

        # -------------------------------------------------
        # Retrieve context from Chroma
        # -------------------------------------------------

        with st.spinner(
            "Searching knowledge base..."
        ):

            results = (
                st.session_state
                .vector_store
                .search(
                    user_query,
                    top_k=top_k
                )
            )

            st.session_state.context_chunks = [
                r["document"]
                for r in results
            ]


        # -------------------------------------------------
        # Generate test cases using LLM
        # -------------------------------------------------

        with st.spinner(
            "Generating test cases..."
        ):

            prompt = build_test_case_prompt(
                st.session_state.context_chunks,
                user_query
            )

            response = generate_with_llm(
                "You are a QA test case generator.",
                prompt,
                max_tokens,
                json_mode=True
            )


        st.subheader("LLM Output")

        st.text_area(
            "Raw Response:",
            response,
            height=300
        )


        # -------------------------------------------------
        # Parse LLM JSON response
        # -------------------------------------------------

        try:

            response_clean = response.strip()

            if response_clean.startswith(
                "```json"
            ):
                response_clean = (
                    response_clean[7:]
                )

            if response_clean.startswith(
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

            parsed_response = json.loads(response_clean)

            if isinstance(parsed_response, list):
                test_cases = parsed_response
            elif (
                isinstance(parsed_response, dict)
                and "test_cases" in parsed_response
                and isinstance(parsed_response["test_cases"], list)
            ):
                test_cases = parsed_response["test_cases"]
            else:
            # Treat a single valid test-case object
            # as one test case
                test_cases = [parsed_response]

            st.session_state.test_cases = test_cases

            # Clear scripts generated for previous test cases
            st.session_state.generated_scripts = {}

            st.success(
                f"✅ Generated "
                f"{len(st.session_state.test_cases)} "
                f"test case(s)!"
            )


        except json.JSONDecodeError as e:

            st.error(
                f"Failed to parse test cases "
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
    # Target application entered ONCE
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
        )
    )


    # -----------------------------------------------------
    # Each generated test case
    # -----------------------------------------------------

    for idx, tc in enumerate(
        st.session_state.test_cases
    ):

        test_title = tc.get(
            "Test_Scenario",
            "N/A"
        )

        with st.expander(
            f"Test Case {idx + 1}: "
            f"{test_title}",
            expanded=False
        ):

            st.json(tc)


            # =================================================
            # GENERATE SELENIUM SCRIPT
            # =================================================

            st.subheader(
                "Generate Selenium Script"
            )


            if st.button(
                "🔧 Generate Selenium Script",
                key=f"gen_script_{idx}"
            ):

                if not target_input:

                    st.warning(
                        "Please enter a target URL "
                        "or HTML file path above"
                    )

                else:

                    # Remove accidental quotes
                    clean_target = (
                        target_input
                        .strip()
                        .strip('"')
                        .strip("'")
                    )


                    try:

                        # -------------------------------------
                        # Load target HTML
                        # -------------------------------------

                        with st.spinner(
                            "Fetching HTML content..."
                        ):

                            if clean_target.startswith(
                                (
                                    "http://",
                                    "https://"
                                )
                            ):

                                response = requests.get(
                                    clean_target,
                                    timeout=10
                                )

                                response.raise_for_status()

                                html_content = (
                                    response.text
                                )

                                selenium_target = (
                                    clean_target
                                )

                            else:

                                target_path = (
                                    Path(clean_target)
                                    .expanduser()
                                    .resolve()
                                )

                                html_content = (
                                    target_path
                                    .read_text(
                                        encoding="utf-8"
                                    )
                                )

                                # Converts:
                                #
                                # D:\Projects\...\checkout.html
                                #
                                # into:
                                #
                                # file:///D:/Projects/.../checkout.html
                                selenium_target = (
                                    target_path.as_uri()
                                )


                        # -------------------------------------
                        # Generate Selenium code
                        # -------------------------------------

                        with st.spinner(
                            "Generating Selenium script..."
                        ):

                            script_prompt = (
                                build_script_prompt(
                                    html_content,
                                    tc,
                                    st.session_state.context_chunks,
                                    selenium_target
                                )
                            )

                            script = generate_with_llm(
                                (
                                    "You are a Selenium "
                                    "automation expert."
                                ),
                                script_prompt,
                                2048
                            )


                            # ---------------------------------
                            # Remove Markdown code fences
                            # ---------------------------------

                            script_clean = (
                                script.strip()
                            )

                            if script_clean.startswith(
                                "```python"
                            ):
                                script_clean = (
                                    script_clean[9:]
                                )

                            if script_clean.startswith(
                                "```"
                            ):
                                script_clean = (
                                    script_clean[3:]
                                )

                            if script_clean.endswith(
                                "```"
                            ):
                                script_clean = (
                                    script_clean[:-3]
                                )

                            script_clean = (
                                script_clean.strip()
                            )


                            # ---------------------------------
                            # Save in Streamlit session
                            # ---------------------------------

                            st.session_state.generated_scripts[
                                idx
                            ] = script_clean


                            st.success(
                                "✅ Script generated "
                                "successfully!"
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
                            f"File not found: "
                            f"{clean_target}"
                        )


                    except Exception as e:

                        st.error(
                            f"Error: {e}"
                        )


            # =================================================
            # DISPLAY SAVED SCRIPT
            # =================================================

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
                    language="python"
                )


                st.download_button(
                    "⬇️ Download Script",
                    saved_script,
                    file_name=(
                        f"test_case_{idx + 1}.py"
                    ),
                    mime="text/x-python",
                    key=f"saved_download_{idx}"
                )


                # =================================================
                # RUN GENERATED TEST
                # =================================================

                st.subheader(
                    "Run Selenium Test"
                )


                if st.button(
                    "▶️ Run Test",
                    key=f"run_test_{idx}"
                ):

                    script_path = (
                        GENERATED_TESTS_DIR
                        / f"test_case_{idx + 1}.py"
                    )


                    # Save generated script
                    # as an actual Python file
                    script_path.write_text(
                        saved_script,
                        encoding="utf-8"
                    )


                    start_time = (
                        time.perf_counter()
                    )


                    try:

                        with st.spinner(
                            "Running Selenium test..."
                        ):

                            result = subprocess.run(
                                [
                                    sys.executable,
                                    str(script_path)
                                ],
                                capture_output=True,
                                text=True,
                                timeout=30
                            )


                        execution_time = (
                            time.perf_counter()
                            - start_time
                        )


                        # -----------------------------------------
                        # PASS
                        # -----------------------------------------

                        if result.returncode == 0:

                            st.success(
                                f"✅ TEST PASSED — "
                                f"{execution_time:.2f} seconds"
                            )


                        # -----------------------------------------
                        # FAIL / ERROR
                        # -----------------------------------------

                        else:

                            st.error(
                                f"❌ TEST FAILED — "
                                f"{execution_time:.2f} seconds"
                            )


                        # -----------------------------------------
                        # stdout
                        # -----------------------------------------

                        if result.stdout:

                            st.subheader(
                                "Console Output"
                            )

                            st.code(
                                result.stdout
                            )


                        # -----------------------------------------
                        # stderr
                        # -----------------------------------------

                        if result.stderr:

                            st.subheader(
                                "Error Output"
                            )

                            st.code(
                                result.stderr
                            )


                    # ---------------------------------------------
                    # Timeout
                    # ---------------------------------------------

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


                    # ---------------------------------------------
                    # Unexpected execution problem
                    # ---------------------------------------------

                    except Exception as e:

                        st.error(
                            f"Execution error: {e}"
                        )


# =========================================================
# SIDEBAR FOOTER
# =========================================================

st.sidebar.markdown("---")

st.sidebar.info(
    "📌 Upload documents → "
    "Generate test cases → "
    "Generate Selenium scripts → "
    "Run tests"
)