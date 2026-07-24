import streamlit as st

from dashboard.ade_design_system import apply_premium_theme
from dashboard.us_trading_desk_app import run

apply_premium_theme(st, page="us-trading")
run()
