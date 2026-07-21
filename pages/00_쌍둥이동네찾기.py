"""
지역별 연령별 인구구조 시각화 웹앱 (Streamlit + Plotly)

실행 방법:
    streamlit run app.py

주의:
    데이터 파일 "202606_202606_연령별인구현황_월간.csv"가
    이 스크립트(app.py)와 같은 폴더에 있어야 합니다.
"""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# -----------------------------
# 기본 설정
# -----------------------------
st.set_page_config(page_title="지역별 연령별 인구구조", layout="wide")

DATA_FILE = "202606_202606_연령별인구현황_월간.csv"  # 업로드한 파일명 그대로 사용


# -----------------------------
# 데이터 로드 & 전처리
# -----------------------------
@st.cache_data
def load_data(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, encoding="cp949", low_memory=False)
    df.columns = df.columns.str.strip()

    region_col = df.columns[0]
    num_cols = df.columns[1:]

    for c in num_cols:
        df[c] = (
            df[c]
            .astype(str)
            .str.replace(",", "", regex=False)
            .str.replace("(", "", regex=False)
            .str.replace(")", "", regex=False)
        )
        df[c] = pd.to_numeric(df[c], errors="coerce")

    return df


def get_age_columns(df: pd.DataFrame, gender: str) -> list[str]:
    """성별(계/남/여)에 해당하는 연령 컬럼만 나이순으로 정렬해서 반환"""
    cols = [
        c
        for c in df.columns
        if f"_{gender}_" in c
        and "세" in c
        and "총인구수" not in c
        and "연령구간인구수" not in c
    ]

    def age_value(col: str) -> int:
        label = col.split("_")[-1]
        label = label.replace("세 이상", "").replace("세", "")
        return int(label)

    cols_sorted = sorted(cols, key=age_value)
    return cols_sorted


def age_label(col: str) -> str:
    label = col.split("_")[-1]
    return label  # 예: "0세", "100세 이상"


@st.cache_data
def compute_age_proportions(df: pd.DataFrame, age_cols: list[str]) -> pd.DataFrame:
    """지역별 인구수를 '연령대별 비율'로 정규화 (지역 규모 차이를 제거하기 위함)"""
    mat = df[age_cols].astype(float)
    row_sum = mat.sum(axis=1)
    proportions = mat.div(row_sum.replace(0, np.nan), axis=0)
    return proportions


def find_similar_regions(
    df: pd.DataFrame,
    region_col: str,
    age_cols: list[str],
    base_region: str,
    top_n: int = 5,
) -> pd.DataFrame:
    """기준 지역과 연령 구조(비율)가 가장 비슷한 상위 top_n개 지역을 유클리드 거리 기준으로 반환"""
    proportions = compute_age_proportions(df, age_cols)

    valid_mask = proportions.notna().all(axis=1)
    proportions = proportions[valid_mask]
    df_valid = df.loc[valid_mask, [region_col]].reset_index(drop=True)
    proportions = proportions.reset_index(drop=True)

    base_matches = df_valid.index[df_valid[region_col] == base_region]
    if len(base_matches) == 0:
        return pd.DataFrame(columns=[region_col, "거리(유사도)"])

    base_vec = proportions.iloc[base_matches[0]].values
    diffs = proportions.values - base_vec
    distances = np.sqrt((diffs**2).sum(axis=1))

    result = pd.DataFrame({region_col: df_valid[region_col], "거리(유사도)": distances})
    result = result[result[region_col] != base_region]
    result = result.sort_values("거리(유사도)").head(top_n).reset_index(drop=True)
    return result


# -----------------------------
# 메인
# -----------------------------
try:
    df = load_data(DATA_FILE)
except FileNotFoundError:
    st.error(f"'{DATA_FILE}' 파일을 찾을 수 없습니다. app.py와 같은 폴더에 데이터를 넣어주세요.")
    st.stop()

region_col = df.columns[0]
region_list = df[region_col].tolist()

st.title("📊 지역별 연령별 인구구조")
st.caption("행정안전부 연령별 인구현황 데이터를 기반으로 합니다.")

# --- 사이드바: 지역/성별 선택 ---
st.sidebar.header("🔎 지역 선택")

search_text = st.sidebar.text_input("지역명 검색 (예: 서울, 강남구)", "")

if search_text:
    filtered_regions = [r for r in region_list if search_text in r]
    if not filtered_regions:
        st.sidebar.warning("검색 결과가 없습니다. 전체 목록을 표시합니다.")
        filtered_regions = region_list
else:
    filtered_regions = region_list

selected_regions = st.sidebar.multiselect(
    "지역 선택 (여러 개 선택 시 비교 가능)",
    options=filtered_regions,
    default=[filtered_regions[0]] if filtered_regions else [],
)

gender = st.sidebar.radio("성별", ["계", "남", "여"], horizontal=True)

if not selected_regions:
    st.info("왼쪽 사이드바에서 지역을 하나 이상 선택해주세요.")
    st.stop()

# --- 그래프 생성 ---
age_cols = get_age_columns(df, gender)
age_labels = [age_label(c) for c in age_cols]

fig = go.Figure()

for region in selected_regions:
    row = df[df[region_col] == region]
    if row.empty:
        continue
    row = row.iloc[0]
    values = [row[c] for c in age_cols]
    fig.add_trace(
        go.Scatter(
            x=age_labels,
            y=values,
            mode="lines",
            name=region,
        )
    )

fig.update_layout(
    title=f"연령별 인구구조 ({gender})",
    xaxis_title="연령",
    yaxis_title="인구수(명)",
    hovermode="x unified",
    template="plotly_white",
    legend_title="지역",
    height=600,
)

st.plotly_chart(fig, use_container_width=True)

# -----------------------------
# 인구구조 유사 지역 Top N
# -----------------------------
st.markdown("---")
st.header("🧭 인구구조가 가장 비슷한 지역 Top N")
st.caption("연령별 인구 '비율'(구성비)을 기준으로 전국 지역(읍면동 포함) 중 유클리드 거리가 가장 가까운 지역을 찾습니다.")

sim_col1, sim_col2 = st.columns([2, 1])

with sim_col1:
    sim_search = st.text_input("기준 지역 검색 (읍면동 포함, 예: 청운효자동)", "", key="sim_search")
    if sim_search:
        sim_options = [r for r in region_list if sim_search in r]
        if not sim_options:
            st.warning("검색 결과가 없습니다. 전체 목록을 표시합니다.")
            sim_options = region_list
    else:
        sim_options = region_list

    default_base = selected_regions[0] if selected_regions[0] in sim_options else sim_options[0]
    base_region = st.selectbox(
        "기준 지역 선택",
        options=sim_options,
        index=sim_options.index(default_base),
    )

with sim_col2:
    top_n = st.slider("표시할 유사 지역 개수", min_value=3, max_value=10, value=5)

similar_df = find_similar_regions(df, region_col, age_cols, base_region, top_n=top_n)

if similar_df.empty:
    st.warning("유사 지역을 계산할 수 없습니다 (해당 지역의 인구 데이터가 없거나 0명입니다).")
else:
    st.dataframe(similar_df, use_container_width=True, hide_index=True)

    proportions_all = compute_age_proportions(df, age_cols) * 100  # 비율(%)로 표시
    proportions_all[region_col] = df[region_col]

    fig_sim = go.Figure()

    base_row = proportions_all[proportions_all[region_col] == base_region]
    if not base_row.empty:
        fig_sim.add_trace(
            go.Scatter(
                x=age_labels,
                y=base_row.iloc[0][age_cols].values,
                mode="lines",
                name=f"⭐ {base_region} (기준)",
                line=dict(width=4, dash="solid"),
            )
        )

    for region in similar_df[region_col]:
        row = proportions_all[proportions_all[region_col] == region]
        if row.empty:
            continue
        fig_sim.add_trace(
            go.Scatter(
                x=age_labels,
                y=row.iloc[0][age_cols].values,
                mode="lines",
                name=region,
                line=dict(width=2, dash="dot"),
            )
        )

    fig_sim.update_layout(
        title=f"'{base_region}'과 인구구조(연령 비율)가 유사한 지역 Top {top_n} ({gender})",
        xaxis_title="연령",
        yaxis_title="비율(%)",
        hovermode="x unified",
        template="plotly_white",
        legend_title="지역",
        height=600,
    )

    st.plotly_chart(fig_sim, use_container_width=True)

# --- 원본 데이터 확인 ---
with st.expander("📋 선택 지역 원본 데이터 보기"):
    display_df = df[df[region_col].isin(selected_regions)].set_index(region_col)
    st.dataframe(display_df[["".join([c]) for c in df.columns if "총인구수" in c and gender in c]])
