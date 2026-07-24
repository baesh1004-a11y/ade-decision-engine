import streamlit as st

from dashboard.ade_design_system import apply_premium_theme
from trading.name_resolution_patch import install_name_resolution_patch
from trading.order_service_patch import install_order_service_patch
from dashboard.trading_desk_chart_first_app import run
from dashboard.kis_realtime_panel import render_kis_realtime_panel

apply_premium_theme(st, page="kr-trading")
install_name_resolution_patch()
install_order_service_patch()
run()
render_kis_realtime_panel()
