import streamlit as st
import pdfplumber
import pandas as pd
import re
from io import BytesIO

st.set_page_config(page_title="Software Requirement Traceability", layout="wide")

st.title("📑 SW Requirement Traceability Matrix")
st.write("Upload SRS and Test Protocol to generate the mapping.")

# --- SIDEBAR UPLOADS ---
with st.sidebar:
    st.header("Upload Documents")
    srs_file = st.file_uploader("1. Upload SRS", type=["pdf"])
    protocol_file = st.file_uploader("2. Upload Test Protocol", type=["pdf"])

# --- EXTRACTION LOGIC ---

def extract_master_requirements(pdf_file):
    """Extracts all unique RCM_SW-XXXXXX IDs from the SRS document."""
    req_ids = set()
    with pdfplumber.open(pdf_file) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                # Matches RCM_SW- followed by digits
                matches = re.findall(r"RCM_SW-\d+", text)
                req_ids.update(matches)
    return sorted(list(req_ids))

def extract_testcases(pdf_file):
    """Your original logic for LC2530 extraction."""
    results = []
    current = {"Scenario": "", "Id": "", "Trace": ""}
    collecting_scenario = False

    def flush():
        nonlocal current
        if any(current.values()):
            scenario = re.sub(r"\s+", " ", current["Scenario"]).strip()
            scenario = re.sub(r"\bTrace\b[\s:\.\-–—]*$", "", scenario, flags=re.IGNORECASE).strip()
            current["Scenario"] = scenario
            results.append(current.copy())
            current = {"Scenario": "", "Id": "", "Trace": ""}

    with pdfplumber.open(pdf_file) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text: continue
            lines = [l.strip() for l in text.split("\n") if l.strip()]

            for line in lines:
                trace_values = re.findall(r"RCM_SW-\d+", line)
                if trace_values:
                    if current["Trace"]:
                        current["Trace"] += "\n" + "\n".join(trace_values)
                    else:
                        current["Trace"] = "\n".join(trace_values)
                    continue

                if line.startswith("Scenario:"):
                    flush()
                    collecting_scenario = True
                    working = line.replace("Scenario:", "").strip()
                    id_match = re.search(r"\bId:\s*([A-Za-z0-9_-]+)", working)
                    if id_match:
                        current["Id"] = id_match.group(1)
                        working = working.replace(id_match.group(0), "").strip()
                    working = re.sub(r"\bTrace:\b", "", working).strip()
                    current["Scenario"] = working
                    continue

                if line.startswith("Id:"):
                    current["Id"] = line.replace("Id:", "").strip()
                    collecting_scenario = False
                    continue

                if line.startswith("Steps:"):
                    collecting_scenario = False
                    continue

                if collecting_scenario:
                    current["Scenario"] += " " + line
    flush()
    return pd.DataFrame(results)

# --- PROCESSING ---

if srs_file and protocol_file:
    with st.spinner("Analyzing documents..."):
        # 1. Get Master List from SP0570
        master_reqs = extract_master_requirements(srs_file)
        df_master = pd.DataFrame(master_reqs, columns=["SW Requirement ID"])

        # 2. Get Test Case Mappings from LC2530
        df_protocol = extract_testcases(protocol_file)
        
        # Expand protocol mapping (one row per requirement ID)
        df_protocol = df_protocol.rename(columns={"Trace": "SW Requirement ID"})
        df_protocol["SW Requirement ID"] = df_protocol["SW Requirement ID"].str.split("\n")
        df_protocol = df_protocol.explode("SW Requirement ID").dropna(subset=["SW Requirement ID"])
        df_protocol["SW Requirement ID"] = df_protocol["SW Requirement ID"].str.strip()

        # 3. Merge (Traceability Matrix)
        # We use a 'left' join on the Master list to see what is missing
        traceability_df = pd.merge(df_master, df_protocol, on="SW Requirement ID", how="left")
        
        # Add Status Column
        traceability_df["Status"] = traceability_df["Scenario"].apply(
            lambda x: "✅ Tested" if pd.notnull(x) else "❌ Not Covered"
        )

    # --- UI SUMMARY ---
    total_reqs = len(df_master)
    covered_reqs = traceability_df[traceability_df["Status"] == "✅ Tested"]["SW Requirement ID"].nunique()
    coverage_pct = (covered_reqs / total_reqs) * 100 if total_reqs > 0 else 0

    col1, col2, col3 = st.columns(3)
    col1.metric("Total Requirements", total_reqs)
    col2.metric("Tested Requirements", covered_reqs)
    col3.metric("Coverage %", f"{coverage_pct:.1f}%")

    # --- DISPLAY TABLE ---
    st.subheader("Traceability Matrix Details")
    
    # Optional: Filter by status
    status_filter = st.multiselect("Filter by Status", ["✅ Tested", "❌ Not Covered"], default=["✅ Tested", "❌ Not Covered"])
    filtered_df = traceability_df[traceability_df["Status"].isin(status_filter)]
    
    st.dataframe(filtered_df, use_container_width=True)

    # --- DOWNLOAD ---
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        filtered_df.to_excel(writer, index=False, sheet_name="Traceability_Matrix")
    
    st.download_button(
        label="⬇️ Download Traceability Excel",
        data=output.getvalue(),
        file_name="SW_Traceability_Report.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
else:
    st.info("Please upload both the SRS and Protocol files to begin.")