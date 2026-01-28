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
            
            # Clean Scenario whitespace
            scenario = re.sub(r"\s+", " ", current["Scenario"]).strip()

            # Remove trailing 'Trace' word if present
            scenario = re.sub(r"\bTrace\b[\s:\.\-–—]*$", "", scenario, flags=re.IGNORECASE).strip()

            current["Scenario"] = scenario

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
                    continue

                # -----------------------------
                # NEW SCENARIO
                # -----------------------------
                if line.startswith("Scenario:"):
                    flush()
                    collecting_scenario = True
                    collecting_trace = False

                    working = line.replace("Scenario:", "").strip()

                    # Extract ID if present inline
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
                # TRACE label only (omit word)
                # -----------------------------
                if line.startswith("Trace:"):
                    collecting_trace = True
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

    flush()
    return pd.DataFrame(results)

# -----------------------------
# STREAMLIT UI
# -----------------------------
if uploaded_file:
    with st.spinner("Extracting test cases..."):
        df = extract_testcases(uploaded_file)

        # Rename Trace column
        df = df.rename(columns={"Trace": "SW Requirement ID"})

        # Split multiple SW requirement IDs into rows
        df["SW Requirement ID"] = df["SW Requirement ID"].str.split("\n")
        df = df.explode("SW Requirement ID")

        # Clean
        df["SW Requirement ID"] = df["SW Requirement ID"].str.strip()
        df = df[df["SW Requirement ID"] != ""]

    if df.empty:
        st.warning("No test cases found.")
    else:
        st.success(f"Extracted {len(df)} Scenario–Requirement mappings")

        # Count unique SW requirements
        total_reqs = df["SW Requirement ID"].nunique()
        st.info(f"✅ Total unique SW Requirement IDs covered: **{total_reqs}**")

        st.dataframe(df, use_container_width=True)

        output = BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="TestCases")

            worksheet = writer.sheets["TestCases"]
            for col in worksheet.columns:
                for cell in col:
                    cell.alignment = cell.alignment.copy(wrapText=True)

        st.download_button(
            label="⬇️ Download Excel",
            data=output.getvalue(),
            file_name="Extracted_TestCases.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
