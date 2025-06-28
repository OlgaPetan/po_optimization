

   
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta

# --- Load and process data ---
@st.cache_data

def load_data(path, target_wos):
    df = pd.read_csv(path, delimiter=";")
    df.columns = [col.strip() for col in df.columns]
    df["Sales Rate Per Week"] = pd.to_numeric(df["Sales Rate Per Week"], errors="coerce").fillna(0)
    df["Current Quantity"] = pd.to_numeric(df["Current Quantity"], errors="coerce").fillna(0)
    df["WOS"] = df["Current Quantity"] / df["Sales Rate Per Week"]
    df["Target WOS"] = target_wos
    df = df.sort_values("Week Number").groupby("SKU").tail(1).reset_index(drop=True)
    df["Suggested Replan Qty"] = (df["Target WOS"] * df["Sales Rate Per Week"] - df["Current Quantity"]).clip(lower=0).round()
    df["Color"] = df["SKU"].apply(lambda x: x.split(" ")[0])
    df["Size"] = df["SKU"].apply(lambda x: x.split(" ")[1] if " " in x else "Unknown")
    df["Velocity Tier"] = df["Velocity"].fillna("Unknown")
    return df

# PO Validation ---
def validate_po(po_df):
    issues = []
    total_units = po_df["Suggested Replan Qty"].sum()
    if total_units < 5000:
        issues.append(f"⚠️ Total PO units below minimum: {total_units} < 5000")

    for color, group in po_df.groupby("Color"):
        if group["Suggested Replan Qty"].sum() < 1000:
            issues.append(f"⚠️ Color '{color}' has less than 1,000 units")

    for _, row in po_df.iterrows():
        if row["Suggested Replan Qty"] < 25:
            issues.append(f"⚠️ SKU {row['SKU']} has less than 25 units")
    return issues

# Suggest PO based on rules 
def suggest_po(df):
    total_volume = df["Sales Rate Per Week"].sum()
    df["% of Volume"] = df["Sales Rate Per Week"] / total_volume
    df["Reason"] = ""

    included = []

    # High-velocity SKUs with WOS < 10
    high = df[(df["% of Volume"] >= 0.05) & (df["WOS"] < 10)]
    high["Reason"] = "High velocity & WOS < 10"
    included.append(high)

    # Low-velocity SKUs < 10 WOS — only if cumulative volume > 5%
    low = df[(df["% of Volume"] < 0.05) & (df["WOS"] < 10)]
    low_cumulative = low["% of Volume"].sum()
    if low_cumulative > 0.05:
        low["Reason"] = "Low velocity & collectively understocked"
        included.append(low)

    po_df = pd.concat(included).drop_duplicates(subset="SKU")

    # Fill to 5,000 units if needed
    if po_df["Suggested Replan Qty"].sum() < 5000:
        needed = 5000 - po_df["Suggested Replan Qty"].sum()
        candidates = df[~df["SKU"].isin(po_df["SKU"])].copy()
        candidates = candidates.sort_values("WOS")
        for _, row in candidates.iterrows():
            if row["Suggested Replan Qty"] >= 25:
                po_df = pd.concat([po_df, pd.DataFrame([row])])
                if po_df["Suggested Replan Qty"].sum() >= 5000:
                    break

    return po_df

# --- App ---
st.title("🧠 Honeylove PO Optimizer (Local Data)")
target_wos = st.slider("Target Weeks of Supply (WOS)", 8, 20, 15)

# Automatically load local CSV
df = load_data("data.csv", target_wos)

if st.button("Suggest Optimal PO"):
    po_df = suggest_po(df)

    st.subheader("📦 Suggested PO")
    st.dataframe(po_df[["SKU", "Color", "Size", "Velocity Tier", "WOS", "Suggested Replan Qty", "Reason"]])

    # Validation
    st.subheader("✅ PO Validation")
    issues = validate_po(po_df)
    if issues:
        for issue in issues:
            st.warning(issue)
    else:
        st.success("PO meets all constraints!")

    # Totals
    st.metric("Total Units", int(po_df["Suggested Replan Qty"].sum()))
    st.metric("Colors", po_df["Color"].nunique())
    st.metric("SKUs", po_df["SKU"].nunique())

    # Download
    st.download_button(
        "📥 Download PO CSV",
        data=po_df[["SKU", "Color", "Size", "Suggested Replan Qty", "Reason"]].to_csv(index=False),
        file_name="optimized_po.csv",
        mime="text/csv"
    )

else:
    st.info("Click 'Suggest Optimal PO' to generate a recommendation based on Honeylove rules.")
