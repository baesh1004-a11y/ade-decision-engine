from __future__ import annotations

from maintenance.network import dashboard_urls


def run(port: int = 8501) -> None:
    import streamlit as st

    st.set_page_config(page_title="ADE Mobile Access", page_icon="📱", layout="wide")
    urls = dashboard_urls(port)

    st.markdown(
        """
        <style>
        .stApp{background:linear-gradient(135deg,#eef7ff,#fbfdff 48%,#eaf3ff);color:#13253a}
        .block-container{max-width:1100px;padding-top:1.2rem}
        .hero{padding:26px 30px;border-radius:26px;background:rgba(255,255,255,.88);border:1px solid rgba(72,145,210,.22);box-shadow:0 18px 48px rgba(64,106,147,.12);margin-bottom:18px}
        .hero h1{margin:4px 0}.hero p{color:#687d92}.eyebrow{font-size:12px;letter-spacing:.15em;font-weight:800;color:#3479b9}
        .url-card{padding:22px;border-radius:22px;background:rgba(255,255,255,.88);border:1px solid rgba(72,145,210,.18);box-shadow:0 10px 28px rgba(63,105,145,.08)}
        .url{font-size:28px;font-weight:800;word-break:break-all;color:#1d5f9d}
        </style>
        <div class="hero">
          <div class="eyebrow">ADE MOBILE ACCESS</div>
          <h1>휴대폰 접속 안내</h1>
          <p>PC와 휴대폰이 같은 Wi-Fi에 연결된 상태에서 아래 주소를 휴대폰 브라우저에 입력합니다.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        f"""
        <div class="url-card">
          <div>모바일 접속 주소</div>
          <div class="url">{urls['mobile']}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.code(urls["mobile"], language=None)
    st.caption(f"PC 내부 주소: {urls['desktop']} · LAN IP: {urls['lan_ip']}")

    st.markdown("### 접속 조건")
    st.markdown(
        """
        1. PC에서 `python run_ade.py`가 실행 중이어야 합니다.  
        2. PC와 휴대폰이 같은 Wi-Fi 또는 같은 사내 LAN에 연결되어야 합니다.  
        3. Windows 네트워크 프로필은 **개인 네트워크**가 권장됩니다.  
        4. 접속이 막히면 관리자 권한 명령 프롬프트에서 `python setup_mobile_access.py`를 한 번 실행합니다.
        """
    )

    st.warning(
        "이 기능은 같은 로컬 네트워크용입니다. 공유기 포트포워딩으로 인터넷에 직접 공개하지 마세요."
    )


if __name__ == "__main__":
    run()
