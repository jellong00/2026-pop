# pages/2_시도별_급여지급_현황.py
"""
시도별 복지급여 지급 현황 대시보드
데이터: 한국사회보장정보원_복지사업 시도별 급여지급 현황_20251231.csv
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

# -----------------------------------------------------------------------
# 기본 페이지 설정
# -----------------------------------------------------------------------
st.set_page_config(
    page_title="시도별 급여지급 현황",
    page_icon="💰",
    layout="wide",
)

DATA_PATH = "한국사회보장정보원_복지사업 시도별 급여지급 현황_20251231.csv"


# -----------------------------------------------------------------------
# 데이터 로드 (인코딩 예외처리 + 캐싱)
# -----------------------------------------------------------------------
@st.cache_data(show_spinner="데이터를 불러오는 중입니다...")
def load_data(path: str) -> pd.DataFrame:
    """CP949/EUC-KR 인코딩을 순차적으로 시도하여 CSV를 로드하고 파생변수를 생성한다."""
    encodings_to_try = ["cp949", "euc-kr", "utf-8-sig", "utf-8"]
    df = None
    last_err = None

    for enc in encodings_to_try:
        try:
            df = pd.read_csv(path, encoding=enc)
            break
        except (UnicodeDecodeError, UnicodeError) as e:
            last_err = e
            continue

    if df is None:
        raise RuntimeError(
            f"파일을 읽을 수 없습니다. 시도한 인코딩: {encodings_to_try}. "
            f"마지막 오류: {last_err}"
        )

    # 컬럼명 공백 제거
    df.columns = [c.strip() for c in df.columns]

    required_cols = ["자격", "서비스", "기준년월", "시도", "지급건수", "지급금액"]
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise KeyError(f"필수 컬럼이 누락되었습니다: {missing}")

    # 숫자형 변환 (콤마, 공백 등이 섞여있을 가능성 대비)
    for col in ["지급건수", "지급금액"]:
        if df[col].dtype == object:
            df[col] = (
                df[col]
                .astype(str)
                .str.replace(",", "", regex=False)
                .str.strip()
            )
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=["지급건수", "지급금액"])
    df = df[df["지급건수"] > 0]  # 0으로 나누기 방지

    # -----------------------------------------------------------------
    # 파생변수
    # -----------------------------------------------------------------
    # 지급금액 단위가 "백만원"이라고 가정 (요청사항의 * 1,000,000 계산 근거)
    # 건당_평균지급액 (원 단위)
    df["건당_평균지급액"] = (df["지급금액"] * 1_000_000) / df["지급건수"]

    # 10억원 단위 지급금액 (억원 단위, 요청 컬럼명 그대로 사용)
    df["10억원_단위_지급금액"] = df["지급금액"] / 1_000

    # 기준년월 문자열 표준화
    df["기준년월"] = df["기준년월"].astype(str)

    return df


try:
    raw_df = load_data(DATA_PATH)
except FileNotFoundError:
    st.error(
        f"❌ 데이터 파일을 찾을 수 없습니다: `{DATA_PATH}`\n\n"
        "해당 CSV 파일을 앱 실행 경로(또는 지정 경로)에 위치시켜주세요."
    )
    st.stop()
except Exception as e:
    st.error(f"❌ 데이터 로드 중 오류가 발생했습니다: {e}")
    st.stop()


# -----------------------------------------------------------------------
# 사이드바 필터
# -----------------------------------------------------------------------
st.sidebar.header("🔍 필터")

# 1) 복지 자격 선택 (전체/다중선택)
all_qualifications = sorted(raw_df["자격"].dropna().unique().tolist())
select_all_qual = st.sidebar.checkbox("복지 자격 전체 선택", value=True)

if select_all_qual:
    selected_qualifications = all_qualifications
else:
    selected_qualifications = st.sidebar.multiselect(
        "복지 자격 선택",
        options=all_qualifications,
        default=all_qualifications[:1] if all_qualifications else [],
    )

# 자격 선택에 따라 필터링된 데이터 (서비스 옵션 산출용)
df_by_qual = raw_df[raw_df["자격"].isin(selected_qualifications)]

# 2) 세부 서비스 선택 (자격 선택에 따라 가변 적용)
all_services = sorted(df_by_qual["서비스"].dropna().unique().tolist())
select_all_service = st.sidebar.checkbox("세부 서비스 전체 선택", value=True)

if select_all_service:
    selected_services = all_services
else:
    selected_services = st.sidebar.multiselect(
        "세부 서비스 선택",
        options=all_services,
        default=all_services[:1] if all_services else [],
    )

# 3) 시도 선택 (부가 필터, 요청엔 없지만 UX 개선용으로 추가)
all_sido = sorted(raw_df["시도"].dropna().unique().tolist())
selected_sido = st.sidebar.multiselect(
    "시도 선택 (선택 안 하면 전체)",
    options=all_sido,
    default=[],
)

st.sidebar.markdown("---")
st.sidebar.caption(f"원본 데이터 행 수: {len(raw_df):,}건")

# -----------------------------------------------------------------------
# 필터 적용
# -----------------------------------------------------------------------
filtered_df = raw_df[
    raw_df["자격"].isin(selected_qualifications)
    & raw_df["서비스"].isin(selected_services)
]

if selected_sido:
    filtered_df = filtered_df[filtered_df["시도"].isin(selected_sido)]

if filtered_df.empty:
    st.warning("⚠️ 선택하신 조건에 해당하는 데이터가 없습니다. 필터를 조정해주세요.")
    st.stop()


# -----------------------------------------------------------------------
# 상단 타이틀 & KPI 카드
# -----------------------------------------------------------------------
st.title("💰 시도별 복지급여 지급 현황")
st.caption("자료: 한국사회보장정보원 | 복지사업 시도별 급여지급 현황 (2025.12.31 기준)")

total_amount_billion = filtered_df["지급금액"].sum() / 1_000  # 억원
total_count = filtered_df["지급건수"].sum()
avg_amount_per_case = (
    (filtered_df["지급금액"].sum() * 1_000_000) / total_count if total_count > 0 else 0
)

kpi1, kpi2, kpi3 = st.columns(3)

kpi1.metric(
    label="💵 총 지급금액",
    value=f"{total_amount_billion:,.1f} 억원",
)
kpi2.metric(
    label="📄 총 지급건수",
    value=f"{total_count:,.0f} 건",
)
kpi3.metric(
    label="📊 건당 평균 지급액",
    value=f"{avg_amount_per_case:,.0f} 원",
)

st.markdown("---")

# -----------------------------------------------------------------------
# 탭 구성
# -----------------------------------------------------------------------
tab1, tab2, tab3, tab4 = st.tabs(
    [
        "① 시도별 총액·건수",
        "② 건당 평균 지급액",
        "③ 자격/서비스 비중",
        "④ 예산 소모 순위",
    ]
)

# 공통 색상 팔레트
COLOR_SEQ = px.colors.qualitative.Set2

# =========================================================================
# 탭 1: 시도별 복지 급여지급 총액 및 건수 비교 (Grouped/Horizontal Bar)
# =========================================================================
with tab1:
    st.subheader("시도별 복지 급여지급 총액 및 건수 비교")

    sido_summary = (
        filtered_df.groupby("시도", as_index=False)
        .agg(지급금액_억원=("10억원_단위_지급금액", "sum"), 지급건수=("지급건수", "sum"))
        .sort_values("지급금액_억원", ascending=True)
    )

    fig1 = go.Figure()

    fig1.add_trace(
        go.Bar(
            y=sido_summary["시도"],
            x=sido_summary["지급금액_억원"],
            name="지급금액 (억원)",
            orientation="h",
            marker_color=COLOR_SEQ[0],
            hovertemplate="시도: %{y}<br>지급금액: %{x:,.1f} 억원<extra></extra>",
        )
    )

    fig1.update_layout(
        title="시도별 총 지급금액 (억원)",
        xaxis_title="지급금액 (억원)",
        yaxis_title="시도",
        height=600,
        xaxis=dict(tickformat=",.0f"),
    )

    fig2 = go.Figure()
    sido_summary_count = sido_summary.sort_values("지급건수", ascending=True)
    fig2.add_trace(
        go.Bar(
            y=sido_summary_count["시도"],
            x=sido_summary_count["지급건수"],
            name="지급건수",
            orientation="h",
            marker_color=COLOR_SEQ[1],
            hovertemplate="시도: %{y}<br>지급건수: %{x:,.0f} 건<extra></extra>",
        )
    )
    fig2.update_layout(
        title="시도별 총 지급건수 (건)",
        xaxis_title="지급건수 (건)",
        yaxis_title="시도",
        height=600,
        xaxis=dict(tickformat=",.0f"),
    )

    col1, col2 = st.columns(2)
    with col1:
        st.plotly_chart(fig1, use_container_width=True)
    with col2:
        st.plotly_chart(fig2, use_container_width=True)

    with st.expander("📋 시도별 요약 데이터 보기"):
        st.dataframe(
            sido_summary.rename(
                columns={"지급금액_억원": "지급금액(억원)", "지급건수": "지급건수(건)"}
            ).style.format({"지급금액(억원)": "{:,.1f}", "지급건수(건)": "{:,.0f}"}),
            use_container_width=True,
        )

# =========================================================================
# 탭 2: 시도별 건당 평균 지급액 비교 (Bar + 평균선)
# =========================================================================
with tab2:
    st.subheader("시도별 건당 평균 지급액 비교")

    sido_avg = (
        filtered_df.groupby("시도", as_index=False)
        .agg(지급금액=("지급금액", "sum"), 지급건수=("지급건수", "sum"))
    )
    sido_avg["건당_평균지급액"] = (sido_avg["지급금액"] * 1_000_000) / sido_avg["지급건수"]
    sido_avg = sido_avg.sort_values("건당_평균지급액", ascending=False)

    overall_avg = sido_avg["건당_평균지급액"].mean()

    fig3 = go.Figure()
    fig3.add_trace(
        go.Bar(
            x=sido_avg["시도"],
            y=sido_avg["건당_평균지급액"],
            marker_color=COLOR_SEQ[2],
            name="건당 평균 지급액",
            hovertemplate="시도: %{x}<br>건당 평균 지급액: %{y:,.0f} 원<extra></extra>",
        )
    )

    fig3.add_hline(
        y=overall_avg,
        line_dash="dash",
        line_color="red",
        annotation_text=f"전체 평균: {overall_avg:,.0f}원",
        annotation_position="top left",
    )

    fig3.update_layout(
        title="시도별 건당 평균 지급액 (원) — 전체 평균선 포함",
        xaxis_title="시도",
        yaxis_title="건당 평균 지급액 (원)",
        height=550,
        yaxis=dict(tickformat=","),
    )

    st.plotly_chart(fig3, use_container_width=True)

    with st.expander("📋 시도별 건당 평균 지급액 데이터 보기"):
        st.dataframe(
            sido_avg[["시도", "건당_평균지급액", "지급건수", "지급금액"]]
            .rename(columns={"지급금액": "지급금액(백만원)"})
            .style.format(
                {
                    "건당_평균지급액": "{:,.0f}",
                    "지급건수": "{:,.0f}",
                    "지급금액(백만원)": "{:,.1f}",
                }
            ),
            use_container_width=True,
        )

# =========================================================================
# 탭 3: 복지 자격/서비스별 지급 금액 비중 (Sunburst / Donut)
# =========================================================================
with tab3:
    st.subheader("복지 자격/서비스별 지급 금액 비중")

    chart_type = st.radio(
        "차트 유형 선택",
        options=["선버스트 (자격 → 서비스)", "도넛 (자격별)"],
        horizontal=True,
    )

    qual_service_summary = (
        filtered_df.groupby(["자격", "서비스"], as_index=False)
        .agg(지급금액_억원=("10억원_단위_지급금액", "sum"))
    )
    qual_service_summary = qual_service_summary[qual_service_summary["지급금액_억원"] > 0]

    if chart_type.startswith("선버스트"):
        fig4 = px.sunburst(
            qual_service_summary,
            path=["자격", "서비스"],
            values="지급금액_억원",
            color="자격",
            color_discrete_sequence=COLOR_SEQ,
        )
        fig4.update_traces(
            hovertemplate="%{label}<br>지급금액: %{value:,.1f} 억원<br>비중: %{percentParent:.1%}<extra></extra>"
        )
        fig4.update_layout(title="복지 자격 → 서비스별 지급금액 비중 (선버스트)", height=650)
    else:
        qual_summary = (
            filtered_df.groupby("자격", as_index=False)
            .agg(지급금액_억원=("10억원_단위_지급금액", "sum"))
        )
        fig4 = px.pie(
            qual_summary,
            names="자격",
            values="지급금액_억원",
            hole=0.45,
            color_discrete_sequence=COLOR_SEQ,
        )
        fig4.update_traces(
            textinfo="label+percent",
            hovertemplate="자격: %{label}<br>지급금액: %{value:,.1f} 억원<br>비중: %{percent}<extra></extra>",
        )
        fig4.update_layout(title="복지 자격별 지급금액 비중 (도넛)", height=650)

    st.plotly_chart(fig4, use_container_width=True)

    with st.expander("📋 자격/서비스별 지급금액 데이터 보기"):
        st.dataframe(
            qual_service_summary.rename(columns={"지급금액_억원": "지급금액(억원)"}).style.format(
                {"지급금액(억원)": "{:,.1f}"}
            ),
            use_container_width=True,
        )

# =========================================================================
# 탭 4: 시도별 복지 예산 소모 순위 비교 (Treemap / Sorted Bar)
# =========================================================================
with tab4:
    st.subheader("시도별 복지 예산 소모 순위 비교")

    rank_type = st.radio(
        "차트 유형 선택",
        options=["트리맵 (Treemap)", "순위 막대 (Sorted Bar)"],
        horizontal=True,
        key="rank_chart_type",
    )

    sido_rank = (
        filtered_df.groupby("시도", as_index=False)
        .agg(지급금액_억원=("10억원_단위_지급금액", "sum"), 지급건수=("지급건수", "sum"))
        .sort_values("지급금액_억원", ascending=False)
        .reset_index(drop=True)
    )
    sido_rank["순위"] = sido_rank.index + 1

    if rank_type.startswith("트리맵"):
        fig5 = px.treemap(
            sido_rank,
            path=["시도"],
            values="지급금액_억원",
            color="지급금액_억원",
            color_continuous_scale="Blues",
        )
        fig5.update_traces(
            hovertemplate="시도: %{label}<br>지급금액: %{value:,.1f} 억원<extra></extra>",
            texttemplate="%{label}<br>%{value:,.0f}억원",
        )
        fig5.update_layout(title="시도별 복지 예산 소모 규모 (트리맵)", height=650)
    else:
        fig5 = px.bar(
            sido_rank,
            x="지급금액_억원",
            y="시도",
            orientation="h",
            color="지급금액_억원",
            color_continuous_scale="Blues",
            text="순위",
        )
        fig5.update_traces(
            hovertemplate="순위: %{text}위<br>시도: %{y}<br>지급금액: %{x:,.1f} 억원<extra></extra>",
        )
        fig5.update_layout(
            title="시도별 복지 예산 소모 순위 (막대)",
            xaxis_title="지급금액 (억원)",
            yaxis_title="시도",
            yaxis=dict(categoryorder="total ascending"),
            height=650,
        )

    st.plotly_chart(fig5, use_container_width=True)

    with st.expander("📋 시도별 순위 데이터 보기"):
        st.dataframe(
            sido_rank[["순위", "시도", "지급금액_억원", "지급건수"]]
            .rename(columns={"지급금액_억원": "지급금액(억원)", "지급건수": "지급건수(건)"})
            .style.format({"지급금액(억원)": "{:,.1f}", "지급건수(건)": "{:,.0f}"}),
            use_container_width=True,
        )

# -----------------------------------------------------------------------
# 하단 원본 데이터 미리보기
# -----------------------------------------------------------------------
st.markdown("---")
with st.expander("🗂️ 필터링된 원본 데이터 미리보기"):
    st.dataframe(filtered_df, use_container_width=True)
    st.caption(f"필터링된 데이터: {len(filtered_df):,}행")
