# -*- coding: utf-8 -*-
"""
pages/00_시군구별 복지사업수급권자.py

시군구별 복지사업 수급권자 현황 대시보드
- 인구 데이터(KOSIS 연령별인구현황 월간) + 복지 수급 데이터(한국사회보장정보원)를 결합하여
  고령화율, 수급률, 가구당 평균 수급인원 등을 인터랙티브하게 시각화한다.

⚠️ 주의 (인구 데이터 컬럼 자동인식 관련)
KOSIS '연령별인구현황' 파일은 배포 시점에 따라 컬럼명이 조금씩 다르다
(예: "2026년06월_계_총인구수", "2026년06월_남_65세", "2026년06월_여_100세 이상" 등).
아래 load_population() 은 정규식으로 "총인구수/연령대" 컬럼을 자동 탐지하도록 작성했지만,
실제 업로드하는 파일의 헤더가 크게 다르면 REGEX 부분(NOTE 주석 참고)을 파일에 맞게 수정해야 한다.
"""

import re
import io
import unicodedata

import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# -----------------------------------------------------------------------
# 기본 설정
# -----------------------------------------------------------------------
st.set_page_config(
    page_title="시군구별 복지사업 수급권자 현황",
    page_icon="📊",
    layout="wide",
)

PLOTLY_TEMPLATE = "plotly_white"
FONT_FAMILY = "Malgun Gothic, AppleGothic, NanumGothic, sans-serif"  # 한글 폰트 우선순위

WELFARE_FILE_DEFAULT = "한국사회보장정보원_복지사업_시군구별_수급권자_현황_20251231.csv"
POP_FILE_DEFAULT = "202606_202606_연령별인구현황_월간.csv"

WELFARE_PROGRAMS = [
    "기초생활보장(맞춤형급여)",
    "기초생계급여",
    "기초의료급여",
    "기초주거급여",
    "기초교육급여",
    "차상위장애인",
    "차상위자활",
    "차상위본인부담경감대상자",
    "기초연금",
    "장애인연금",
]

# 시도명 정규화용 매핑 (표기 차이 흡수)
SIDO_ALIASES = {
    "강원도": "강원특별자치도",
    "전라북도": "전북특별자치도",
}


# -----------------------------------------------------------------------
# 유틸 함수
# -----------------------------------------------------------------------
def normalize_text(x: str) -> str:
    """공백/유니코드 정규화 (NFC), 괄호 안 행정코드 제거."""
    if pd.isna(x):
        return x
    x = str(x)
    x = unicodedata.normalize("NFC", x)
    x = re.sub(r"\(.*?\)", "", x)  # (1111000000) 같은 코드 제거
    x = re.sub(r"\s+", " ", x).strip()
    return x


def split_sido_sigungu(admin_name: str):
    """'서울특별시 종로구' 같은 문자열을 (시도, 시군구)로 분리."""
    admin_name = normalize_text(admin_name)
    if not admin_name:
        return admin_name, ""
    parts = admin_name.split(" ", 1)
    sido = parts[0]
    sigungu = parts[1] if len(parts) > 1 else ""
    sido = SIDO_ALIASES.get(sido, sido)
    return sido, sigungu


def read_csv_any_encoding(file) -> pd.DataFrame:
    """CP949 / EUC-KR / UTF-8(-SIG) 순으로 시도하여 CSV를 읽는다."""
    encodings = ["cp949", "euc-kr", "utf-8-sig", "utf-8"]
    raw = file.read() if hasattr(file, "read") else open(file, "rb").read()
    last_err = None
    for enc in encodings:
        try:
            return pd.read_csv(io.BytesIO(raw), encoding=enc)
        except Exception as e:  # noqa: BLE001
            last_err = e
            continue
    raise ValueError(f"CSV 인코딩을 인식할 수 없습니다 (시도: {encodings}) / 마지막 오류: {last_err}")


# -----------------------------------------------------------------------
# 데이터 로딩 - 복지 수급 데이터
# -----------------------------------------------------------------------
@st.cache_data(show_spinner="복지 수급 데이터를 불러오는 중...")
def load_welfare(file) -> pd.DataFrame:
    df = read_csv_any_encoding(file)
    df.columns = [normalize_text(c) for c in df.columns]

    rename_map = {}
    for c in df.columns:
        if "사업" in c:
            rename_map[c] = "사업명"
        elif "기준" in c and "년월" in c:
            rename_map[c] = "기준년월"
        elif c == "시도":
            rename_map[c] = "시도"
        elif "시군구" in c:
            rename_map[c] = "시군구"
        elif "수급권자" in c:
            rename_map[c] = "수급권자수"
        elif "수급가구" in c:
            rename_map[c] = "수급가구수"
    df = df.rename(columns=rename_map)

    required = ["사업명", "시도", "시군구", "수급권자수", "수급가구수"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"복지 데이터에 필요한 컬럼이 없습니다: {missing} / 실제 컬럼: {df.columns.tolist()}")

    df["시도"] = df["시도"].apply(normalize_text).replace(SIDO_ALIASES)
    df["시군구"] = df["시군구"].apply(normalize_text)
    df["사업명"] = df["사업명"].apply(normalize_text)

    df["수급권자수"] = pd.to_numeric(df["수급권자수"], errors="coerce").fillna(0).astype(int)
    df["수급가구수"] = pd.to_numeric(df["수급가구수"], errors="coerce").fillna(0).astype(int)

    # 가구당 평균 수급인원
    df["가구당평균수급인원"] = np.where(
        df["수급가구수"] > 0, df["수급권자수"] / df["수급가구수"], np.nan
    ).round(2)

    return df


# -----------------------------------------------------------------------
# 데이터 로딩 - 인구 데이터 (KOSIS 연령별인구현황)
# -----------------------------------------------------------------------
@st.cache_data(show_spinner="인구 데이터를 불러오는 중...")
def load_population(file) -> pd.DataFrame:
    """
    KOSIS '연령별인구현황' 월간 파일을 읽어
    [시도, 시군구, 전체_계, 전체_남, 전체_여, 65세이상_계, 65세이상_남, 65세이상_여] 형태로 변환.

    NOTE: 실제 파일 헤더가 예시와 크게 다르면 아래 정규식(REGEX)을 파일에 맞게 수정할 것.
    """
    df = read_csv_any_encoding(file)
    df.columns = [normalize_text(c) for c in df.columns]

    # 행정구역 컬럼 탐지
    admin_col = None
    for c in df.columns:
        if "행정구역" in c:
            admin_col = c
            break
    if admin_col is None:
        admin_col = df.columns[0]  # fallback: 첫 컬럼을 행정구역으로 가정

    sido_list, sigungu_list = [], []
    for v in df[admin_col]:
        sido, sigungu = split_sido_sigungu(v)
        sido_list.append(sido)
        sigungu_list.append(sigungu)
    df["시도"] = sido_list
    df["시군구"] = sigungu_list

    # 전체(계/남/여) 총인구수 컬럼 탐지: "총인구수" 포함, 성별 접두/접미어로 구분
    def find_total_col(gender_key: str):
        # gender_key: '계' | '남' | '여'
        candidates = [
            c for c in df.columns
            if "총인구수" in c and gender_key in c
        ]
        if not candidates:
            # 성별 표기가 없는 경우(계 전용 단일 컬럼) 처리
            candidates = [c for c in df.columns if "총인구수" in c] if gender_key == "계" else []
        return candidates[0] if candidates else None

    total_col_all = find_total_col("계")
    total_col_m = find_total_col("남")
    total_col_f = find_total_col("여")

    # 연령대 컬럼 탐지: "OO세" 패턴에서 65세 이상 합산
    age_pattern = re.compile(r"(\d+)\s*세\s*(이상)?")

    def gender_of_col(col: str):
        if "_남_" in col or col.endswith("_남") or "남자" in col:
            return "남"
        if "_여_" in col or col.endswith("_여") or "여자" in col:
            return "여"
        return "계"

    age_cols_65plus = {"계": [], "남": [], "여": []}
    for c in df.columns:
        m = age_pattern.search(c)
        if not m:
            continue
        age_num = int(m.group(1))
        is_over = m.group(2) is not None or age_num >= 100
        if age_num >= 65 or is_over:
            g = gender_of_col(c)
            age_cols_65plus[g].append(c)

    def to_numeric_sum(cols):
        if not cols:
            return pd.Series(np.nan, index=df.index)
        sub = df[cols].apply(lambda s: pd.to_numeric(
            s.astype(str).str.replace(",", "").str.strip(), errors="coerce"
        ))
        return sub.sum(axis=1)

    pop = pd.DataFrame()
    pop["시도"] = df["시도"]
    pop["시군구"] = df["시군구"]

    pop["전체_계"] = (
        pd.to_numeric(df[total_col_all].astype(str).str.replace(",", ""), errors="coerce")
        if total_col_all else np.nan
    )
    pop["전체_남"] = (
        pd.to_numeric(df[total_col_m].astype(str).str.replace(",", ""), errors="coerce")
        if total_col_m else np.nan
    )
    pop["전체_여"] = (
        pd.to_numeric(df[total_col_f].astype(str).str.replace(",", ""), errors="coerce")
        if total_col_f else np.nan
    )

    pop["65세이상_계"] = to_numeric_sum(age_cols_65plus["계"])
    pop["65세이상_남"] = to_numeric_sum(age_cols_65plus["남"])
    pop["65세이상_여"] = to_numeric_sum(age_cols_65plus["여"])

    # 계(전체) 컬럼이 비어있으면 남+여로 대체
    if pop["전체_계"].isna().all():
        pop["전체_계"] = pop["전체_남"].fillna(0) + pop["전체_여"].fillna(0)
    if pop["65세이상_계"].isna().all():
        pop["65세이상_계"] = pop["65세이상_남"].fillna(0) + pop["65세이상_여"].fillna(0)

    # 시군구가 비어있는 행(시도 전체 합계 행 등)은 제외
    pop = pop[pop["시군구"].astype(str).str.len() > 0].copy()

    # 고령화율(%), 남녀비율
    pop["고령화율"] = np.where(
        pop["전체_계"] > 0, pop["65세이상_계"] / pop["전체_계"] * 100, np.nan
    ).round(2)
    pop["남비율"] = np.where(
        pop["전체_계"] > 0, pop["전체_남"] / pop["전체_계"] * 100, np.nan
    ).round(2)
    pop["여비율"] = np.where(
        pop["전체_계"] > 0, pop["전체_여"] / pop["전체_계"] * 100, np.nan
    ).round(2)

    return pop.reset_index(drop=True)


# -----------------------------------------------------------------------
# 데이터 결합
# -----------------------------------------------------------------------
@st.cache_data(show_spinner="데이터를 결합하는 중...")
def merge_data(welfare_df: pd.DataFrame, pop_df: pd.DataFrame) -> pd.DataFrame:
    merged = welfare_df.merge(
        pop_df, on=["시도", "시군구"], how="left", suffixes=("", "_pop")
    )
    merged["인구대비수급률"] = np.where(
        merged["전체_계"] > 0, merged["수급권자수"] / merged["전체_계"] * 100, np.nan
    ).round(2)
    return merged


# -----------------------------------------------------------------------
# 사이드바 - 파일 업로드 & 필터
# -----------------------------------------------------------------------
st.sidebar.header("📁 데이터 업로드")
welfare_upload = st.sidebar.file_uploader(
    "복지 수급 데이터 (CSV, CP949/EUC-KR)", type=["csv"], key="welfare_upload"
)
pop_upload = st.sidebar.file_uploader(
    "인구 데이터 (CSV)", type=["csv"], key="pop_upload"
)

st.title("📊 시군구별 복지사업 수급권자 현황")
st.caption("행정구역별 고령화율 · 복지 수급률 · 가구당 평균 수급인원 분석")

if welfare_upload is None or pop_upload is None:
    st.info(
        "왼쪽 사이드바에서 **복지 수급 데이터**와 **인구 데이터** CSV 파일을 각각 업로드해 주세요.\n\n"
        f"- 복지 수급 데이터 예시 파일명: `{WELFARE_FILE_DEFAULT}`\n"
        f"- 인구 데이터 예시 파일명: `{POP_FILE_DEFAULT}`"
    )
    st.stop()

try:
    welfare_df = load_welfare(welfare_upload)
    pop_df = load_population(pop_upload)
    merged_df = merge_data(welfare_df, pop_df)
except Exception as e:  # noqa: BLE001
    st.error(f"데이터 처리 중 오류가 발생했습니다: {e}")
    st.stop()

# 시도/사업 필터
st.sidebar.header("🔎 필터")
sido_options = sorted(merged_df["시도"].dropna().unique().tolist())
selected_sido = st.sidebar.multiselect("시도 선택", sido_options, default=sido_options)

program_options = [p for p in WELFARE_PROGRAMS if p in merged_df["사업명"].unique()]
if not program_options:
    program_options = sorted(merged_df["사업명"].unique().tolist())
selected_program = st.sidebar.selectbox("복지사업 선택", program_options, index=0)

filtered_all_programs = merged_df[merged_df["시도"].isin(selected_sido)].copy()
filtered = filtered_all_programs[filtered_all_programs["사업명"] == selected_program].copy()

if filtered.empty:
    st.warning("선택한 조건에 해당하는 데이터가 없습니다. 필터를 조정해 주세요.")
    st.stop()

# 시군구 선택 (③ 차트용)
sigungu_options = sorted(filtered["시군구"].dropna().unique().tolist())
selected_sigungu = st.sidebar.selectbox(
    "시군구 선택 (사업별 분포 비교용)", sigungu_options, index=0
)


# -----------------------------------------------------------------------
# KPI 카드
# -----------------------------------------------------------------------
total_pop = filtered.drop_duplicates(subset=["시도", "시군구"])["전체_계"].sum()
total_recipients = filtered["수급권자수"].sum()
total_households = filtered["수급가구수"].sum()
recipient_rate = (total_recipients / total_pop * 100) if total_pop and total_pop > 0 else np.nan
avg_per_household = (total_recipients / total_households) if total_households and total_households > 0 else np.nan

k1, k2, k3, k4 = st.columns(4)
k1.metric("선택 지역 전체 인구", f"{total_pop:,.0f} 명" if pd.notna(total_pop) else "N/A")
k2.metric(f"{selected_program} 수급권자수", f"{total_recipients:,.0f} 명")
k3.metric("인구 대비 수급률", f"{recipient_rate:.2f} %" if pd.notna(recipient_rate) else "N/A")
k4.metric("가구당 평균 수급인원", f"{avg_per_household:.2f} 명" if pd.notna(avg_per_household) else "N/A")

st.divider()


# -----------------------------------------------------------------------
# ① 시군구별 수급권자수 및 인구 대비 수급률(%) 비교
# -----------------------------------------------------------------------
st.subheader("① 시군구별 수급권자수 및 인구 대비 수급률")

chart1_df = filtered.groupby(["시도", "시군구"], as_index=False).agg(
    수급권자수=("수급권자수", "sum"),
    인구대비수급률=("인구대비수급률", "mean"),
).sort_values("수급권자수", ascending=False)

fig1 = go.Figure()
fig1.add_trace(
    go.Bar(
        x=chart1_df["시군구"],
        y=chart1_df["수급권자수"],
        name="수급권자수",
        marker_color="#4C78A8",
        yaxis="y1",
    )
)
fig1.add_trace(
    go.Scatter(
        x=chart1_df["시군구"],
        y=chart1_df["인구대비수급률"],
        name="인구 대비 수급률(%)",
        mode="lines+markers",
        marker_color="#E45756",
        yaxis="y2",
    )
)
fig1.update_layout(
    template=PLOTLY_TEMPLATE,
    font=dict(family=FONT_FAMILY),
    xaxis=dict(title="시군구", tickangle=-45),
    yaxis=dict(title="수급권자수 (명)"),
    yaxis2=dict(title="인구 대비 수급률 (%)", overlaying="y", side="right"),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    height=500,
    margin=dict(t=40),
)
st.plotly_chart(fig1, use_container_width=True)


# -----------------------------------------------------------------------
# ② 고령화율 vs 수급률 상관관계 산점도
# -----------------------------------------------------------------------
st.subheader("② 고령화율(%) vs 복지 수급률(%) 상관관계")

chart2_df = filtered.groupby(["시도", "시군구"], as_index=False).agg(
    고령화율=("고령화율", "mean"),
    인구대비수급률=("인구대비수급률", "mean"),
    수급권자수=("수급권자수", "sum"),
    전체_남=("전체_남", "mean"),
    전체_여=("전체_여", "mean"),
).dropna(subset=["고령화율", "인구대비수급률"])

fig2 = px.scatter(
    chart2_df,
    x="고령화율",
    y="인구대비수급률",
    size="수급권자수",
    color="시도",
    hover_name="시군구",
    hover_data={
        "전체_남": ":,.0f",
        "전체_여": ":,.0f",
        "고령화율": ":.2f",
        "인구대비수급률": ":.2f",
        "수급권자수": ":,.0f",
    },
    labels={"고령화율": "고령화율 (%)", "인구대비수급률": "복지 수급률 (%)"},
    template=PLOTLY_TEMPLATE,
    trendline="ols" if len(chart2_df) > 2 else None,
)
fig2.update_layout(font=dict(family=FONT_FAMILY), height=550, margin=dict(t=40))
st.plotly_chart(fig2, use_container_width=True)


# -----------------------------------------------------------------------
# ③ 선택 시군구의 복지사업별 수급 분포 비교
# -----------------------------------------------------------------------
st.subheader(f"③ '{selected_sigungu}'의 복지사업별 수급 분포")

chart3_df = filtered_all_programs[filtered_all_programs["시군구"] == selected_sigungu].copy()
chart3_df = chart3_df.groupby("사업명", as_index=False)["수급권자수"].sum()
chart3_df = chart3_df.set_index("사업명").reindex(program_options).fillna(0).reset_index()

tab_bar, tab_radar = st.tabs(["막대 차트", "레이더 차트"])

with tab_bar:
    fig3a = px.bar(
        chart3_df,
        x="사업명",
        y="수급권자수",
        color="사업명",
        template=PLOTLY_TEMPLATE,
        labels={"수급권자수": "수급권자수 (명)", "사업명": "복지사업"},
    )
    fig3a.update_layout(font=dict(family=FONT_FAMILY), showlegend=False, height=480, margin=dict(t=40))
    st.plotly_chart(fig3a, use_container_width=True)

with tab_radar:
    fig3b = go.Figure()
    fig3b.add_trace(
        go.Scatterpolar(
            r=chart3_df["수급권자수"],
            theta=chart3_df["사업명"],
            fill="toself",
            name=selected_sigungu,
            marker_color="#4C78A8",
        )
    )
    fig3b.update_layout(
        template=PLOTLY_TEMPLATE,
        font=dict(family=FONT_FAMILY),
        polar=dict(radialaxis=dict(visible=True)),
        height=480,
        margin=dict(t=40),
    )
    st.plotly_chart(fig3b, use_container_width=True)


# -----------------------------------------------------------------------
# ④ 가구당 평균 수급인원 분석 (1인 가구 수급 비중 추정)
# -----------------------------------------------------------------------
st.subheader("④ 가구당 평균 수급인원 분석 (1인 가구 수급 비중 추정)")
st.caption(
    "※ 가구당 평균 수급인원이 1명에 가까울수록 1인 가구 수급 비중이 높은 것으로 추정할 수 있음"
)

chart4_df = filtered.groupby(["시도", "시군구"], as_index=False).agg(
    수급권자수=("수급권자수", "sum"),
    수급가구수=("수급가구수", "sum"),
)
chart4_df["가구당평균수급인원"] = np.where(
    chart4_df["수급가구수"] > 0, chart4_df["수급권자수"] / chart4_df["수급가구수"], np.nan
).round(2)
# 1인 가구 수급 비중 추정치: 평균 수급인원이 1에 가까울수록 100%에 근접하도록 역수 기반 지표 산출
chart4_df["1인가구비중_추정(%)"] = np.where(
    chart4_df["가구당평균수급인원"] > 0, 1 / chart4_df["가구당평균수급인원"] * 100, np.nan
).round(1)
chart4_df = chart4_df.sort_values("가구당평균수급인원")

fig4 = px.bar(
    chart4_df,
    x="시군구",
    y="가구당평균수급인원",
    color="1인가구비중_추정(%)",
    color_continuous_scale="RdYlBu_r",
    template=PLOTLY_TEMPLATE,
    labels={"가구당평균수급인원": "가구당 평균 수급인원 (명)", "시군구": "시군구"},
    hover_data={"1인가구비중_추정(%)": ":.1f", "수급가구수": ":,.0f", "수급권자수": ":,.0f"},
)
fig4.add_hline(y=1.0, line_dash="dash", line_color="gray", annotation_text="1인 가구 기준선")
fig4.update_layout(
    font=dict(family=FONT_FAMILY),
    xaxis=dict(tickangle=-45),
    height=520,
    margin=dict(t=40),
)
st.plotly_chart(fig4, use_container_width=True)


# -----------------------------------------------------------------------
# 원본 데이터 미리보기
# -----------------------------------------------------------------------
with st.expander("📄 결합된 원본 데이터 미리보기"):
    st.dataframe(filtered, use_container_width=True)
