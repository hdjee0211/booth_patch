import streamlit as st
import pandas as pd
import requests
import base64
import json
from datetime import datetime
import time

# ───────────────────────────────────────────────
# 설정 (Streamlit Secrets에서 불러오기)
# ───────────────────────────────────────────────
GITHUB_TOKEN  = str(st.secrets["GITHUB_TOKEN"]).strip().encode("ascii", "ignore").decode("ascii")
GITHUB_REPO   = str(st.secrets["GITHUB_REPO"]).strip()
GITHUB_PATH   = str(st.secrets.get("GITHUB_PATH", "booth_data.csv")).strip()
BRANCH        = str(st.secrets.get("GITHUB_BRANCH", "main")).strip()

HEADERS = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3+json",
    "Content-Type": "application/json; charset=utf-8",
}
API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_PATH}"

COLUMNS = ["입장시간", "이름", "전화번호", "퇴장시간", "코인", "상태"]

# ───────────────────────────────────────────────
# GitHub CSV 읽기 / 쓰기
# ───────────────────────────────────────────────
def load_data():
    res = requests.get(API_URL, headers=HEADERS, params={"ref": BRANCH})
    if res.status_code == 404:
        return pd.DataFrame(columns=COLUMNS), None
    if res.status_code != 200:
        st.error(f"데이터 불러오기 실패: {res.status_code}")
        return pd.DataFrame(columns=COLUMNS), None
    content = res.json()
    sha = content["sha"]
    decoded = base64.b64decode(content["content"]).decode("utf-8")
    df = pd.read_csv(pd.io.common.StringIO(decoded), dtype=str).fillna("")
    # 컬럼 보정
    for col in COLUMNS:
        if col not in df.columns:
            df[col] = ""
    return df[COLUMNS], sha

def save_data(df: pd.DataFrame, sha=None, message="update booth data"):
    csv_bytes = df.to_csv(index=False).encode("utf-8")
    encoded   = base64.b64encode(csv_bytes).decode("utf-8")
    payload   = {"message": message, "content": encoded, "branch": BRANCH}
    if sha:
        payload["sha"] = sha
    res = requests.put(API_URL, headers=HEADERS, data=json.dumps(payload))
    return res.status_code in (200, 201)

# ───────────────────────────────────────────────
# UI
# ───────────────────────────────────────────────
st.set_page_config(page_title="부스 방문자 관리", page_icon="🎪", layout="centered")

st.markdown("""
<style>
    .stTabs [data-baseweb="tab"] { font-size: 1.1rem; font-weight: 600; padding: 10px 24px; }
    .big-metric { font-size: 2.8rem; font-weight: 800; color: #4F46E5; line-height: 1; }
    .metric-label { font-size: 0.85rem; color: #6B7280; margin-bottom: 4px; }
    .status-in  { background: #D1FAE5; color: #065F46; padding: 2px 10px; border-radius: 12px; font-size: 0.8rem; font-weight: 600; }
    .status-out { background: #F3F4F6; color: #6B7280; padding: 2px 10px; border-radius: 12px; font-size: 0.8rem; font-weight: 600; }
    div[data-testid="stForm"] { border: 1px solid #E5E7EB; border-radius: 12px; padding: 20px; }
</style>
""", unsafe_allow_html=True)

st.title("🎪 부스 방문자 관리")

tab_in, tab_out, tab_list = st.tabs(["✅ 입장", "🚪 퇴장", "📋 현황"])

# ───────────── 입장 탭 ─────────────
with tab_in:
    st.subheader("방문자 입장 등록")
    with st.form("form_in", clear_on_submit=True):
        name  = st.text_input("이름 *", placeholder="홍길동")
        phone = st.text_input("전화번호 *", placeholder="010-0000-0000")
        submitted = st.form_submit_button("✅ 입장 등록", use_container_width=True, type="primary")

    if submitted:
        if not name.strip() or not phone.strip():
            st.warning("이름과 전화번호를 모두 입력해 주세요.")
        else:
            df, sha = load_data()
            # 이미 입장 중인지 확인
            active = df[(df["이름"] == name.strip()) & (df["상태"] == "입장중")]
            if not active.empty:
                st.warning(f"⚠️ '{name}' 님은 이미 입장 중입니다.")
            else:
                now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                new_row = pd.DataFrame([{
                    "입장시간": now,
                    "이름":    name.strip(),
                    "전화번호": phone.strip(),
                    "퇴장시간": "",
                    "코인":    "",
                    "상태":    "입장중",
                }])
                df = pd.concat([df, new_row], ignore_index=True)
                if save_data(df, sha, f"입장: {name}"):
                    st.success(f"🎉 {name} 님, 환영합니다!")
                    st.balloons()
                else:
                    st.error("저장에 실패했습니다. 다시 시도해 주세요.")

# ───────────── 퇴장 탭 ─────────────
with tab_out:
    st.subheader("방문자 퇴장 처리")

    search_name = st.text_input("이름으로 검색", placeholder="홍길동", key="search_out")

    if search_name.strip():
        df, sha = load_data()
        matches = df[(df["이름"].str.contains(search_name.strip())) & (df["상태"] == "입장중")]

        if matches.empty:
            st.info("현재 입장 중인 방문자 중 해당 이름을 찾을 수 없습니다.")
        else:
            st.write(f"**{len(matches)}명** 검색됨")
            for idx, row in matches.iterrows():
                with st.expander(f"👤 {row['이름']}  |  📞 {row['전화번호']}  |  🕐 {row['입장시간']}", expanded=True):
                    with st.form(f"form_out_{idx}", clear_on_submit=True):
                        coins = st.number_input("획득 코인 수", min_value=0, step=1, key=f"coin_{idx}")
                        out_btn = st.form_submit_button("🚪 퇴장 처리", use_container_width=True, type="primary")
                    if out_btn:
                        df2, sha2 = load_data()
                        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        # 같은 행 찾기 (입장시간+이름으로 특정)
                        mask = (df2["이름"] == row["이름"]) & (df2["입장시간"] == row["입장시간"]) & (df2["상태"] == "입장중")
                        df2.loc[mask, "퇴장시간"] = now
                        df2.loc[mask, "코인"]    = str(coins)
                        df2.loc[mask, "상태"]    = "퇴장완료"
                        if save_data(df2, sha2, f"퇴장: {row['이름']}"):
                            st.success(f"✅ {row['이름']} 님 퇴장 처리 완료! 코인 {coins}개")
                            time.sleep(1)
                            st.rerun()
                        else:
                            st.error("저장 실패. 다시 시도해 주세요.")

# ───────────── 현황 탭 ─────────────
with tab_list:
    st.subheader("전체 방문자 현황")

    col1, col2 = st.columns(2)
    if st.button("🔄 새로고침", use_container_width=False):
        st.rerun()

    df, _ = load_data()

    total   = len(df)
    active  = len(df[df["상태"] == "입장중"])
    exited  = len(df[df["상태"] == "퇴장완료"])
    coin_total = pd.to_numeric(df["코인"], errors="coerce").sum()

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown('<div class="metric-label">총 방문자</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="big-metric">{total}</div>', unsafe_allow_html=True)
    with c2:
        st.markdown('<div class="metric-label">현재 입장 중</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="big-metric" style="color:#059669">{active}</div>', unsafe_allow_html=True)
    with c3:
        st.markdown('<div class="metric-label">퇴장 완료</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="big-metric" style="color:#6B7280">{exited}</div>', unsafe_allow_html=True)
    with c4:
        st.markdown('<div class="metric-label">총 코인</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="big-metric" style="color:#D97706">{int(coin_total)}</div>', unsafe_allow_html=True)

    st.divider()

    if df.empty:
        st.info("아직 등록된 방문자가 없습니다.")
    else:
        # 상태 표시용 컬럼 추가
        display_df = df.copy()
        display_df = display_df.sort_values("입장시간", ascending=False)
        display_df["상태표시"] = display_df["상태"].apply(
            lambda x: "🟢 입장중" if x == "입장중" else "⚪ 퇴장완료"
        )
        st.dataframe(
            display_df[["상태표시", "이름", "전화번호", "입장시간", "퇴장시간", "코인"]].rename(columns={"상태표시": "상태"}),
            use_container_width=True,
            hide_index=True,
        )

        # CSV 다운로드
        csv = df.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="⬇️ CSV 다운로드",
            data=csv,
            file_name=f"booth_visitors_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv",
        )
