import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import json
import urllib.request

# ==========================================
# 1. 페이지 기본 설정 및 디자인
# ==========================================
st.set_page_config(
    page_title="전국 폭염일수 지도 시각화",
    page_icon="☀️",
    layout="wide"
)

st.title("☀️ 전국 연도별 폭염일수 현황 지도")
st.caption("기상청 폭염 관측 데이터와 행정구역 경계를 결합한 시각화 대시보드입니다.")


# ==========================================
# 2. CSV 파일 멀티 섹션 분리 파싱 함수
# ==========================================
@st.cache_data
def load_heatwave_data(file_path):
    """
    하나의 CSV 파일 안에 여러 제목 섹션으로 나뉜 데이터를
    UTF-8 / CP949 인코딩을 자동 감지하여 3개의 데이터프레임으로 분리합니다.
    """
    lines = []
    # 인코딩 호환성 처리 (utf-8 실패 시 cp949 시도)
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except UnicodeDecodeError:
        with open(file_path, 'r', encoding='cp949') as f:
            lines = f.readlines()

    section_1_lines = [] # 가장 긴 폭염
    section_2_lines = [] # 가장 빠른/가장 늦은 폭염
    section_3_lines = [] # 전국 폭염일수

    current_section = None

    for line in lines:
        line_str = line.strip()
        if not line_str:
            continue
            
        # 섹션 헤더 식별
        if "가장 긴 폭염" in line_str:
            current_section = 1
            continue
        elif "가장 빠른" in line_str or "가장 늦은" in line_str:
            current_section = 2
            continue
        elif "전국 폭염일수" in line_str:
            current_section = 3
            continue

        # 헤더별 데이터 분리
        if current_section == 1:
            section_1_lines.append(line)
        elif current_section == 2:
            section_2_lines.append(line)
        elif current_section == 3:
            section_3_lines.append(line)

    from io import StringIO
    
    # 각 섹션별 데이터프레임 생성
    df_longest = pd.read_csv(StringIO(''.join(section_1_lines))) if section_1_lines else pd.DataFrame()
    df_extreme_dates = pd.read_csv(StringIO(''.join(section_2_lines))) if section_2_lines else pd.DataFrame()
    df_raw_days = pd.read_csv(StringIO(''.join(section_3_lines))) if section_3_lines else pd.DataFrame()

    return df_longest, df_extreme_dates, df_raw_days


# ==========================================
# 3. GeoJSON 경계 데이터 로드 함수
# ==========================================
@st.cache_data
def load_geojson():
    url = "https://raw.githubusercontent.com/greatsong/modudata/main/data/boundaries/sigungu_kr.geojson"
    with urllib.request.urlopen(url) as response:
        geojson = json.loads(response.read().decode('utf-8'))
    return geojson


# ==========================================
# 4. 기상청 관측지점 → 실제 시군구명 매핑 딕셔너리
# ==========================================
STATION_TO_SIGUNGU = {
    "강릉": "강릉시",
    "대관령": "평창군",
    "추풍령": "영동군",
    "속초": "속초시",
    "춘천": "춘천시",
    "원주": "원주시",
    "전주": "전주시",
    "광주": "광주광역시",
    "대구": "대구광역시",
    "대전": "대전광역시",
    "부산": "부산광역시",
    "울산": "울산광역시",
    "서울": "서울특별시",
    "인천": "인천광역시",
    "수원": "수원시",
    "청주": "청주시",
    "목포": "목포시",
    "여수": "여수시",
    "안동": "안동시",
    "포항": "포항시",
    "창원": "창원시",
    "제주": "제주시",
    "서귀포": "서귀포시"
}


# ==========================================
# 5. 데이터 로드 및 전처리
# ==========================================
try:
    df_longest, df_extreme_dates, df_raw = load_heatwave_data("heatwave.csv")
    geojson_data = load_geojson()
except Exception as e:
    st.error(f"데이터를 읽어오는 중 오류가 발생했습니다: {e}")
    st.stop()

# '년도' 또는 '연도' 컬럼 정규화 및 수치형 변환
year_col = [col for col in df_raw.columns if '년' in col or 'year' in col.lower()]
if year_col:
    df_raw['연도'] = pd.to_numeric(df_raw[year_col[0]], errors='coerce')

# 지점명을 시군구 이름으로 매핑
station_col = [col for col in df_raw.columns if '지점' in col or 'station' in col.lower()][0]
df_raw['시군구'] = df_raw[station_col].map(lambda x: STATION_TO_SIGUNGU.get(str(x).strip(), str(x).strip()))


# ==========================================
# 6. 사이드바 - 연도 선택 슬라이더
# ==========================================
st.sidebar.header("⚙️ 검색 옵션")
available_years = sorted(df_raw['연도'].dropna().unique().astype(int))

if available_years:
    selected_year = st.sidebar.slider(
        "조회할 연도를 선택하세요",
        min_value=int(min(available_years)),
        max_value=int(max(available_years)),
        value=int(max(available_years)),
        step=1
    )
else:
    selected_year = 2023


# 선택된 연도 데이터 필터링
df_year = df_raw[df_raw['연도'] == selected_year]

# 지점별 폭염일수 집계 (관측 원자료의 행 수가 각 발생일수)
if '날짜' in df_year.columns:
    df_summary = df_year.groupby(['시군구', station_col]).size().reset_index(name='폭염일수')
else:
    # 이미 일수가 계산되어 있는 데이터 형태일 경우 대응
    val_col = [c for c in df_year.columns if '일수' in c or 'count' in c.lower()]
    if val_col:
        df_summary = df_year.groupby(['시군구', station_col])[val_col[0]].sum().reset_index(name='폭염일수')
    else:
        df_summary = df_year.groupby(['시군구', station_col]).size().reset_index(name='폭염일수')


# ==========================================
# 7. 상단 지표 카드 (Metrics)
# ==========================================
col1, col2, col3 = st.columns(3)

avg_days = round(df_summary['폭염일수'].mean(), 1) if not df_summary.empty else 0
max_row = df_summary.loc[df_summary['폭염일수'].idxmax()] if not df_summary.empty else None
max_location = f"{max_row[station_col]} ({max_row['폭염일수']}일)" if max_row is not None else "-"
station_count = len(df_summary)

col1.metric("전국 평균 폭염일수", f"{avg_days} 일")
col2.metric("최다 폭염 발생지", max_location)
col3.metric("관측지점 수", f"{station_count} 곳")

st.divider()


# ==========================================
# 8. Folium 단계구분도(Choropleth) 지도 생성
# ==========================================
st.subheader(f"🗺️ {selected_year}년 시군구별 폭염일수 지도")

# 대한민국 중심좌표 설정
m = folium.Map(location=[36.5, 127.5], zoom_start=7, tiles="cartodbpositron")

# 지도 단계구분도 추가
folium.Choropleth(
    geo_data=geojson_data,
    name="choropleth",
    data=df_summary,
    columns=["시군구", "폭염일수"],
    key_on="feature.properties.시군구",
    fill_color="YlOrRd",
    fill_opacity=0.7,
    line_opacity=0.3,
    legend_name=f"{selected_year}년 폭염일수 (일)",
    nan_fill_color="#f8f9fa"
).add_to(m)

# Streamlit에 지도 출력
st_folium(m, width="100%", height=500)


# ==========================================
# 9. 지도 하단 - 상위 / 하위 10곳 표
# ==========================================
st.divider()
st.subheader(f"📊 {selected_year}년 폭염일수 순위")

col_top, col_bottom = st.columns(2)

with col_top:
    st.markdown("##### 🔥 폭염일수 상위 10곳")
    df_top10 = df_summary.sort_values(by="폭염일수", ascending=False).head(10).reset_index(drop=True)
    st.dataframe(df_top10[[station_col, "시군구", "폭염일수"]], use_container_width=True)

with col_bottom:
    st.markdown("##### 🧊 폭염일수 하위 10곳")
    df_bottom10 = df_summary.sort_values(by="폭염일수", ascending=True).head(10).reset_index(drop=True)
    st.dataframe(df_bottom10[[station_col, "시군구", "폭염일수"]], use_container_width=True)


# ==========================================
# 10. 추가 정보 - 통계 표 섹션
# ==========================================
st.divider()
st.subheader("📜 역대 폭염 기록 상세 정보")

tab1, tab2 = st.tabs(["⏳ 가장 긴 폭염 기록", "🗓️ 가장 빠른 / 늦은 폭염 기록"])

with tab1:
    st.markdown("##### 연도별 가장 오래 지속된 폭염")
    st.dataframe(df_longest, use_container_width=True)

with tab2:
    st.markdown("##### 연도별 가장 이른/늦은 폭염 관측일")
    st.dataframe(df_extreme_dates, use_container_width=True)
