import re
import pandas as pd
import streamlit as st
import plotly.graph_objects as go

# ------------------------------------------------------------
# 기본 설정
# ------------------------------------------------------------
st.set_page_config(page_title="연령별 인구현황 대시보드", layout="wide")

CSV_PATH = "202606_202606_연령별인구현황_월간.csv"  # 리포지토리 루트에 함께 업로드


@st.cache_data
def load_data(path_or_buffer):
    """행정안전부 연령별인구현황 CSV 로드 및 전처리"""
    df = pd.read_csv(path_or_buffer, encoding="cp949")

    # 숫자 컬럼의 콤마(,) 제거 후 정수 변환
    num_cols = df.columns[1:]
    for col in num_cols:
        df[col] = (
            df[col].astype(str).str.replace(",", "", regex=False).replace("nan", "0")
        )
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype("int64")

    # 행정구역 표시명 (코드 제거) 컬럼 추가
    df["표시명"] = df["행정구역"].apply(lambda x: re.sub(r"\s*\(\d+\)\s*$", "", str(x)).strip())
    return df


@st.cache_data
def get_age_series(df: pd.DataFrame, region: str, gender_key: str):
    """선택 지역/성별의 연령별 인구 시리즈(0~100세 이상) 반환"""
    row = df[df["표시명"] == region].iloc[0]

    ages, values = [], []
    for age in list(range(0, 100)) + ["100세 이상"]:
        col = f"{YEAR_MONTH}_{gender_key}_{age}세" if age != "100세 이상" else f"{YEAR_MONTH}_{gender_key}_100세 이상"
        if col in df.columns:
            ages.append(age if age != "100세 이상" else 100)
            values.append(row[col])
    return ages, values


# ------------------------------------------------------------
# 데이터 로드
# ------------------------------------------------------------
st.title("📊 지역별 연령별 인구현황")
st.caption("행정안전부 주민등록 연령별 인구현황 (월간) 데이터를 활용한 대시보드")

uploaded = st.sidebar.file_uploader("CSV 파일 업로드 (선택)", type=["csv"])

try:
    if uploaded is not None:
        df = load_data(uploaded)
    else:
        df = load_data(CSV_PATH)
except FileNotFoundError:
    st.error(
        f"'{CSV_PATH}' 파일을 찾을 수 없습니다. "
        "리포지토리에 CSV 파일을 함께 업로드하거나, 좌측 사이드바에서 파일을 직접 업로드해주세요."
    )
    st.stop()

# 데이터의 연월 접두어 자동 추출 (예: '2026년06월')
YEAR_MONTH = re.match(r"^(\d{4}년\d{2}월)", df.columns[1]).group(1)

# ------------------------------------------------------------
# 사이드바: 지역 선택 (검색 + 선택 가능)
# ------------------------------------------------------------
st.sidebar.header("🔎 지역 선택")

region_list = sorted(df["표시명"].unique().tolist())

search_text = st.sidebar.text_input("지역명 검색 (예: 창원, 종로)", "")

if search_text:
    filtered_regions = [r for r in region_list if search_text in r]
else:
    filtered_regions = region_list

if not filtered_regions:
    st.sidebar.warning("검색 결과가 없습니다. 검색어를 확인해주세요.")
    st.stop()

default_regions = filtered_regions[:1]

selected_regions = st.sidebar.multiselect(
    "지역 선택 (여러 지역 비교 가능)",
    options=filtered_regions,
    default=default_regions,
)

gender_option = st.sidebar.radio("성별", options=["전체(계)", "남", "여"], horizontal=True)
gender_map = {"전체(계)": "계", "남": "남", "여": "여"}
gender_key = gender_map[gender_option]

if not selected_regions:
    st.info("좌측 사이드바에서 지역을 선택해주세요.")
    st.stop()

# ------------------------------------------------------------
# 꺾은선 그래프 (Plotly)
# ------------------------------------------------------------
fig = go.Figure()

for region in selected_regions:
    ages, values = get_age_series(df, region, gender_key)
    fig.add_trace(
        go.Scatter(
            x=ages,
            y=values,
            mode="lines",
            name=region,
            line=dict(width=2),
            hovertemplate="%{x}세: %{y:,}명<extra>" + region + "</extra>",
        )
    )

fig.update_layout(
    title=f"{YEAR_MONTH} 연령별 인구구조 ({gender_option})",
    xaxis_title="연령(세)",
    yaxis_title="인구수(명)",
    hovermode="x unified",
    legend_title="지역",
    height=550,
)

st.plotly_chart(fig, use_container_width=True)

# ------------------------------------------------------------
# 요약 테이블
# ------------------------------------------------------------
st.subheader("📋 지역별 요약 통계")

summary_rows = []
for region in selected_regions:
    total_col = f"{YEAR_MONTH}_{gender_key}_총인구수"
    row = df[df["표시명"] == region].iloc[0]
    ages, values = get_age_series(df, region, gender_key)
    total = row[total_col]
    avg_age = sum(a * v for a, v in zip(ages, values)) / total if total > 0 else 0
    elderly_ratio = sum(v for a, v in zip(ages, values) if a >= 65) / total * 100 if total > 0 else 0

    summary_rows.append(
        {
            "지역": region,
            "총인구수": f"{total:,}",
            "평균연령(추정)": f"{avg_age:.1f}세",
            "65세 이상 비율": f"{elderly_ratio:.1f}%",
        }
    )

st.dataframe(pd.DataFrame(summary_rows), use_container_width=True, hide_index=True)

st.caption("※ 평균연령은 연령별 인구를 가중평균하여 추정한 값입니다 (100세 이상은 100세로 계산).")
