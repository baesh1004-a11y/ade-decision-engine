from __future__ import annotations

from dashboard.design_system import StatusBadge, apply_design_system, page_header, section
from maintenance.network import dashboard_urls


def run(port: int = 8501) -> None:
    import streamlit as st

    st.set_page_config(page_title="ADE 모바일 접속", page_icon="📱", layout="wide")
    apply_design_system()
    urls = dashboard_urls(port)

    page_header(
        "모바일 접속",
        "PC와 휴대폰이 같은 Wi-Fi 또는 사내 LAN에 연결된 상태에서 아래 주소로 접속합니다.",
        eyebrow="ADE · 모바일 접속 안내",
        badges=(
            StatusBadge("로컬 네트워크 전용", "warning"),
            StatusBadge(f"포트 {port}", "info"),
        ),
    )

    section("접속 주소", "휴대폰 브라우저의 주소창에 입력합니다.")
    st.code(urls["mobile"], language=None)
    st.caption(f"PC 내부 주소: {urls['desktop']} · LAN IP: {urls['lan_ip']}")

    section("접속 조건")
    st.markdown(
        """
        1. PC에서 `python run_ade.py`가 실행 중이어야 합니다.  
        2. PC와 휴대폰이 같은 Wi-Fi 또는 같은 사내 LAN에 연결되어야 합니다.  
        3. Windows 네트워크 프로필은 **개인 네트워크**가 권장됩니다.  
        4. 접속이 막히면 관리자 권한 명령 프롬프트에서 `python setup_mobile_access.py`를 한 번 실행합니다.
        """
    )

    st.warning("이 기능은 같은 로컬 네트워크에서만 사용하세요. 포트포워딩으로 인터넷에 직접 공개하지 마세요.")


if __name__ == "__main__":
    run()
