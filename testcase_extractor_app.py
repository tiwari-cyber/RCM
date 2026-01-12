import streamlit as st
import pdfplumber
import pandas as pd
import re
from io import BytesIO

st.set_page_config(page_title="Test Case Extractor", layout="wide")

st.title("📄 Test Case Scenario Extractor")
st.write("Upload a **Test Protocol PDF** to extract Scenario, Id, and Trace.")

uploaded_file = st.file_uploader(
    "Upload Test Case PDF",
    type=["pdf"]
)

def extract_testcases(pdf_file):
    results = []

    current = {"Scenario": "", "Id": "", "Trace": ""}
    collecting_scenario = False
    collecting_trace = False

    def flush():
        nonlocal current
        if any(current.values()):
            # Clean extra whitespace
            current["Scenario"] = re.sub(r"\s+", " ", current["Scenario"]).strip()
            current["Trace"] = re.sub(r"\s+", " ", current["Trace"]).strip()
            results.append(current.copy())
            current = {"Scenario": "", "Id": "", "Trace": ""}

    with pdfplumber.open(pdf_file) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text:
                continue

            lines = [l.strip() for l in text.split("\n") if l.strip()]

            for line in lines:

                # -----------------------------
                # ALWAYS extract TRACE first
                # -----------------------------
                trace_values = re.findall(r"RCM_SW-\d+", line)
                if trace_values:
                    if current["Trace"]:
                        current["Trace"] += "\n" + "\n".join(trace_values)
                    else:
                        current["Trace"] = "\n".join(trace_values)
                    # Do not let trace lines pollute scenario
                    continue

                # -----------------------------
                # NEW SCENARIO
                # -----------------------------
                if line.startswith("Scenario:"):
                    flush()
                    collecting_scenario = True
                    collecting_trace = False

                    working = line.replace("Scenario:", "").strip()

                    # Extract ID if present
                    id_match = re.search(r"\bId:\s*([A-Za-z0-9_-]+)", working)
                    if id_match:
                        current["Id"] = id_match.group(1)
                        working = working.replace(id_match.group(0), "").strip()

                    # Remove literal 'Trace:' text if present
                    working = re.sub(r"\bTrace:\b", "", working).strip()

                    current["Scenario"] = working
                    continue

                # -----------------------------
                # ID on separate line
                # -----------------------------
                if line.startswith("Id:"):
                    current["Id"] = line.replace("Id:", "").strip()
                    collecting_scenario = False
                    continue

                # -----------------------------
                # TRACE label only
                # -----------------------------
                if line.startswith("Trace:"):
                    collecting_trace = True
                    # Also extract traces in the same line
                    trace_values = re.findall(r"RCM_SW-\d+", line)
                    if trace_values:
                        if current["Trace"]:
                            current["Trace"] += "\n" + "\n".join(trace_values)
                        else:
                            current["Trace"] = "\n".join(trace_values)
                    continue

                # -----------------------------
                # STOP AT STEPS
                # -----------------------------
                if line.startswith("Steps:"):
                    collecting_scenario = False
                    collecting_trace = False
                    continue

                # -----------------------------
                # SCENARIO CONTINUATION
                # -----------------------------
                if collecting_scenario:
                    current["Scenario"] += " " + line
                    continue

    flush()
    return pd.DataFrame(results)


# -----------------------------
# STREAMLIT UI
# -----------------------------
if uploaded_file:
    with st.spinner("Extracting test cases..."):
        df = extract_testcases(uploaded_file)

    if df.empty:
        st.warning("No test cases found.")
    else:
        st.success(f"Extracted {len(df)} test cases")

        # Show dataframe with multi-line traces
        st.dataframe(df, use_container_width=True)

        output = BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="TestCases")

            # Enable wrap text in Excel for trace column
            worksheet = writer.sheets["TestCases"]
            for idx, col in enumerate(df.columns):
                if col == "Trace":
                    for row in range(2, len(df) + 2):
                        cell = worksheet.cell(row=row, column=idx+1)
                        cell.alignment = cell.alignment.copy(wrapText=True)

        st.download_button(
            label="⬇️ Download Excel",
            data=output.getvalue(),
            file_name="Extracted_TestCases.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
