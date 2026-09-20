"""Streamlit client for the VERITY AI — Evidence-Based AI Reliability Platform."""
import base64
import json
import os
import sys
from pathlib import Path
import time
from collections import defaultdict

# Ensure src/ and repo root are on sys.path for Streamlit Community Cloud
ROOT_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import httpx
import pandas as pd
import streamlit as st
from ai_reliability.ingestion.ui import render_input_form

st.set_page_config(
    page_title="VERITY AI — See what AI can actually prove",
    page_icon="✦",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Load Robot Hero Base64 image
CANDIDATE_ROBOT_PATHS = [
    Path(__file__).resolve().parent / "assets" / "verity_robot_hero.png",
    Path(__file__).resolve().parent / "static" / "verity_robot.png",
    ROOT_DIR / "static" / "verity_robot.png",
    ROOT_DIR / "frontend" / "assets" / "verity_robot_hero.png",
    Path("static/verity_robot.png"),
    Path("frontend/assets/verity_robot_hero.png"),
]

ROBOT_B64 = ""
for p in CANDIDATE_ROBOT_PATHS:
    if p.exists() and p.is_file():
        try:
            with open(p, "rb") as f:
                ROBOT_B64 = f"data:image/png;base64,{base64.b64encode(f.read()).decode('utf-8')}"
            if ROBOT_B64:
                break
        except Exception:
            continue


# Cinematic Design: Deep Burgundy (#59171B), Warm Peach (#FED7B8), Rose/Wine (#8B263E, #C45564), Near-Black (#0E0406)
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:ital,wght@0,300;0,400;0,500;0,600;0,700;0,800;1,400&family=JetBrains+Mono:wght@400;500;600&display=swap');

    *, *::before, *::after {
        box-sizing: border-box;
    }

    html {
        scroll-behavior: smooth;
        max-width: 100vw;
        overflow-x: clip;
    }

    body, [data-testid="stAppViewContainer"], .main, .stApp {
        max-width: 100vw !important;
        overflow-x: clip !important;
        box-sizing: border-box !important;
    }

    @supports not (overflow-x: clip) {
        html, body, [data-testid="stAppViewContainer"], .main, .stApp {
            overflow-x: hidden !important;
        }
    }

    html, body, [class*="css"] {
        font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif;
    }

    code, pre, [data-testid="stCode"] {
        font-family: 'JetBrains Mono', monospace !important;
    }

    .block-container {
        padding-top: 1rem !important;
        padding-bottom: 3rem !important;
        padding-left: clamp(0.75rem, 3vw, 2.5rem) !important;
        padding-right: clamp(0.75rem, 3vw, 2.5rem) !important;
        max-width: 1240px !important;
        margin: 0 auto !important;
    }

    /* Cinematic Deep Burgundy / Near-Black Background with Atmospheric Depth */
    .stApp {
        background-color: #0E0406;
        background-image: 
            radial-gradient(circle at 50% 12%, rgba(254, 215, 184, 0.14) 0%, transparent 35%),
            radial-gradient(circle at 50% 28%, rgba(89, 23, 27, 0.55) 0%, transparent 55%),
            radial-gradient(circle at 15% 45%, rgba(139, 38, 62, 0.25) 0%, transparent 45%),
            radial-gradient(circle at 85% 65%, rgba(89, 23, 27, 0.35) 0%, transparent 45%),
            radial-gradient(circle at 50% 90%, rgba(89, 23, 27, 0.4) 0%, transparent 50%);
        background-attachment: fixed;
        color: #FFF5EE;
    }

    /* Top Minimal Navigation Bar */
    .verity-nav {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 12px 24px;
        margin-bottom: 12px;
        border-bottom: 1px solid rgba(254, 215, 184, 0.1);
        backdrop-filter: blur(16px);
        background: rgba(14, 4, 6, 0.55);
        border-radius: 16px;
        width: 100%;
        box-sizing: border-box;
    }
    .verity-brand {
        display: flex;
        align-items: center;
        gap: 8px;
        font-size: clamp(0.95rem, 2.5vw, 1.15rem);
        font-weight: 800;
        letter-spacing: 0.1em;
        color: #FFFFFF;
        text-transform: uppercase;
        white-space: nowrap;
    }
    .verity-brand-mark {
        color: #FED7B8;
        font-size: 1.2rem;
        filter: drop-shadow(0 0 8px rgba(254, 215, 184, 0.6));
    }
    .verity-nav-links {
        display: flex;
        gap: clamp(12px, 2vw, 28px);
        font-size: clamp(0.82rem, 1.8vw, 0.92rem);
        font-weight: 500;
        color: #D6ADA0;
    }
    .verity-nav-links span {
        cursor: pointer;
        transition: color 0.2s ease;
        white-space: nowrap;
    }
    .verity-nav-links span:hover, .verity-nav-links span.active {
        color: #FED7B8;
    }
    .verity-nav-cta {
        background: linear-gradient(135deg, #FED7B8 0%, #E89E88 50%, #C45564 100%);
        color: #2D080C !important;
        font-size: clamp(0.75rem, 1.8vw, 0.85rem);
        font-weight: 700;
        padding: 7px 16px;
        border-radius: 24px;
        letter-spacing: 0.02em;
        box-shadow: 0 4px 16px rgba(254, 215, 184, 0.2);
        text-decoration: none !important;
        cursor: pointer;
        transition: all 0.22s cubic-bezier(0.16, 1, 0.3, 1);
        display: inline-block;
        white-space: nowrap;
    }
    .verity-nav-cta:hover, .verity-nav-cta:focus {
        box-shadow: 0 6px 24px rgba(254, 215, 184, 0.45);
        transform: translateY(-2px);
        color: #1A0407 !important;
    }

    /* Cinematic Hero Layout with Giant Background Typography & Robot */
    .hero-wrapper {
        position: relative;
        padding: 16px 0 24px 0;
        overflow: hidden;
        width: 100%;
        box-sizing: border-box;
    }
    .hero-giant-bg-text-top {
        position: absolute;
        top: 2%;
        left: 50%;
        transform: translateX(-50%);
        font-size: clamp(2.4rem, 7.5vw, 7.8rem);
        font-weight: 800;
        color: rgba(255, 255, 255, 0.9);
        letter-spacing: -0.04em;
        white-space: nowrap;
        pointer-events: none;
        z-index: 1;
        text-shadow: 0 0 40px rgba(254, 215, 184, 0.2);
        max-width: 100%;
        overflow: hidden;
    }
    .hero-giant-bg-text-bottom {
        position: absolute;
        top: 22%;
        left: 50%;
        transform: translateX(-50%);
        font-size: clamp(2.4rem, 7.5vw, 7.8rem);
        font-weight: 800;
        color: rgba(254, 215, 184, 0.12);
        letter-spacing: -0.04em;
        white-space: nowrap;
        pointer-events: none;
        z-index: 1;
        max-width: 100%;
        overflow: hidden;
    }
    .hero-composition {
        position: relative;
        display: grid;
        grid-template-columns: 1.15fr 1.2fr 0.85fr;
        align-items: center;
        min-height: 440px;
        z-index: 2;
        gap: 20px;
        width: 100%;
        box-sizing: border-box;
    }
    .hero-left-content {
        padding-top: 10px;
        z-index: 3;
        width: 100%;
    }
    .hero-eyebrow {
        font-size: 0.76rem;
        font-weight: 800;
        letter-spacing: 0.18em;
        color: #FED7B8;
        text-transform: uppercase;
        margin-bottom: 12px;
        display: inline-block;
    }
    .hero-main-title {
        font-size: clamp(2.2rem, 4vw, 3.8rem);
        font-weight: 800;
        color: #FFFFFF;
        line-height: 1.12;
        letter-spacing: -0.04em;
        margin: 0 0 16px 0;
        word-break: break-word;
    }
    .hero-main-title span.gradient-text {
        background: linear-gradient(135deg, #FED7B8 0%, #E89E88 45%, #C45564 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
    }
    .hero-description {
        font-size: clamp(0.92rem, 1.8vw, 1.05rem);
        color: #E2C2B2;
        line-height: 1.55;
        margin: 0 0 24px 0;
        max-width: 440px;
        font-weight: 400;
    }
    .hero-buttons {
        display: flex;
        align-items: center;
        gap: 12px;
        flex-wrap: wrap;
    }
    .hero-btn-primary {
        background: linear-gradient(135deg, #FED7B8 0%, #E89E88 45%, #C45564 100%);
        color: #2D080C !important;
        font-weight: 800;
        font-size: 0.95rem;
        padding: 12px 24px;
        border-radius: 28px;
        text-decoration: none !important;
        box-shadow: 0 6px 20px rgba(254, 215, 184, 0.3);
        display: inline-flex;
        align-items: center;
        gap: 8px;
        cursor: pointer;
        transition: all 0.22s cubic-bezier(0.16, 1, 0.3, 1);
        white-space: nowrap;
    }
    .hero-btn-primary:hover, .hero-btn-primary:focus {
        background: linear-gradient(135deg, #FFFFFF 0%, #FED7B8 50%, #D87B85 100%) !important;
        box-shadow: 0 8px 30px rgba(254, 215, 184, 0.45);
        transform: translateY(-2px);
        color: #1A0407 !important;
    }
    .hero-btn-secondary {
        background: rgba(254, 215, 184, 0.06);
        color: #FED7B8 !important;
        font-weight: 600;
        font-size: 0.92rem;
        padding: 11px 22px;
        border-radius: 28px;
        border: 1px solid rgba(254, 215, 184, 0.22);
        display: inline-flex;
        align-items: center;
        gap: 8px;
        text-decoration: none !important;
        cursor: pointer;
        transition: all 0.22s cubic-bezier(0.16, 1, 0.3, 1);
        white-space: nowrap;
    }
    .hero-btn-secondary:hover, .hero-btn-secondary:focus {
        background: rgba(254, 215, 184, 0.15) !important;
        border-color: #FED7B8 !important;
        color: #FFFFFF !important;
        transform: translateY(-2px);
    }

    /* Centered Robot Visual in Hero */
    .hero-robot-center {
        display: flex;
        justify-content: center;
        align-items: center;
        position: relative;
        z-index: 2;
        width: 100%;
    }
    .robot-glow-aura {
        position: absolute;
        width: clamp(200px, 32vw, 320px);
        height: clamp(200px, 32vw, 320px);
        background: radial-gradient(circle, rgba(254, 215, 184, 0.28) 0%, rgba(89, 23, 27, 0.45) 45%, transparent 70%);
        border-radius: 50%;
        filter: blur(28px);
        z-index: -1;
        pointer-events: none;
    }
    .robot-img {
        max-width: 100%;
        height: auto;
        max-height: 420px;
        object-fit: contain;
        filter: drop-shadow(0 15px 35px rgba(0, 0, 0, 0.85)) drop-shadow(0 0 25px rgba(89, 23, 27, 0.4));
        user-select: none;
        display: block;
        margin: 0 auto;
    }

    /* Floating Metric Badges on Right of Hero */
    .hero-right-metrics {
        display: flex;
        flex-direction: column;
        gap: 14px;
        align-items: flex-start;
        padding-left: 10px;
        z-index: 3;
        width: 100%;
    }
    .hero-metric-tag {
        font-size: 0.72rem;
        font-weight: 800;
        letter-spacing: 0.12em;
        color: #FED7B8;
        text-transform: uppercase;
        margin-bottom: 4px;
    }
    .hero-metric-pill {
        background: rgba(30, 9, 13, 0.65);
        border: 1px solid rgba(254, 215, 184, 0.16);
        border-radius: 16px;
        padding: 14px 20px;
        backdrop-filter: blur(14px);
        min-width: 130px;
        box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
        box-sizing: border-box;
    }
    .hero-metric-number {
        font-size: 1.8rem;
        font-weight: 800;
        color: #FFFFFF;
        line-height: 1;
        margin-bottom: 4px;
    }
    .hero-metric-label {
        font-size: 0.78rem;
        color: #D6ADA0;
        font-weight: 500;
    }

    /* Console Container ("Ask Verity") */
    .checker-console {
        background: rgba(24, 7, 11, 0.65);
        border: 1px solid rgba(254, 215, 184, 0.18);
        border-radius: 20px;
        padding: clamp(16px, 3.5vw, 26px);
        margin: 10px auto 36px auto;
        backdrop-filter: blur(20px);
        box-shadow: 0 16px 40px rgba(0, 0, 0, 0.5), inset 0 1px 0 rgba(254, 215, 184, 0.15);
        width: 100%;
        box-sizing: border-box;
    }
    .console-header {
        display: flex;
        align-items: center;
        gap: 10px;
        margin-bottom: 20px;
        flex-wrap: wrap;
    }
    .console-header-icon {
        color: #FED7B8;
        font-size: 1.25rem;
    }
    .console-title {
        font-size: clamp(1.1rem, 2.5vw, 1.25rem);
        font-weight: 700;
        color: #FFFFFF;
        margin: 0;
    }
    .console-subtitle {
        font-size: clamp(0.8rem, 1.8vw, 0.88rem);
        color: #D6ADA0;
        margin-left: 4px;
    }

    /* Input Fields */
    .field-label {
        font-size: 0.88rem;
        font-weight: 700;
        color: #FED7B8;
        margin: 0 0 6px 0;
        letter-spacing: -0.01em;
    }
    .stTextArea, .stTextInput {
        width: 100% !important;
    }
    .stTextArea textarea, .stTextInput input {
        background: rgba(12, 3, 5, 0.75) !important;
        border: 1px solid rgba(254, 215, 184, 0.16) !important;
        border-radius: 12px !important;
        color: #FFF5EE !important;
        font-size: 0.96rem !important;
        transition: all 0.25s ease !important;
        width: 100% !important;
        box-sizing: border-box !important;
    }
    .stTextArea textarea:focus, .stTextInput input:focus {
        border-color: #FED7B8 !important;
        box-shadow: 0 0 0 3px rgba(254, 215, 184, 0.2) !important;
        background: rgba(18, 5, 8, 0.9) !important;
    }

    /* Primary Gradient Button */
    button[kind="primary"], .stButton > button {
        background: linear-gradient(135deg, #FED7B8 0%, #E89E88 45%, #C45564 100%) !important;
        color: #2D080C !important;
        border: none !important;
        font-weight: 800 !important;
        font-size: clamp(0.92rem, 2vw, 1.05rem) !important;
        letter-spacing: 0.02em !important;
        border-radius: 12px !important;
        padding: 13px 28px !important;
        box-shadow: 0 6px 24px rgba(254, 215, 184, 0.28) !important;
        transition: all 0.22s cubic-bezier(0.16, 1, 0.3, 1) !important;
        width: 100% !important;
    }
    button[kind="primary"]:hover, .stButton > button:hover {
        background: linear-gradient(135deg, #FFFFFF 0%, #FED7B8 50%, #D87B85 100%) !important;
        box-shadow: 0 8px 32px rgba(254, 215, 184, 0.45) !important;
        transform: translateY(-2px) !important;
        color: #1A0407 !important;
    }

    /* 3 Feature Cards (Matching Reference Layout Exactly) */
    .feature-grid {
        display: grid;
        grid-template-columns: repeat(3, 1fr);
        gap: 20px;
        margin: 20px 0 50px 0;
        width: 100%;
        box-sizing: border-box;
    }
    .feature-card {
        background: rgba(24, 7, 11, 0.55);
        border: 1px solid rgba(254, 215, 184, 0.12);
        border-radius: 18px;
        padding: clamp(18px, 3vw, 26px) clamp(16px, 2.5vw, 24px);
        transition: all 0.25s ease;
        backdrop-filter: blur(14px);
        display: flex;
        flex-direction: column;
        justify-content: space-between;
        min-height: 250px;
        box-sizing: border-box;
        width: 100%;
    }
    .feature-card:hover {
        border-color: rgba(254, 215, 184, 0.3);
        background: rgba(38, 11, 17, 0.7);
        transform: translateY(-4px);
        box-shadow: 0 14px 35px rgba(89, 23, 27, 0.35);
    }
    .feature-visual {
        min-height: 80px;
        margin-bottom: 16px;
        display: flex;
        align-items: center;
        justify-content: center;
    }
    .feature-title {
        font-size: clamp(1rem, 2vw, 1.12rem);
        font-weight: 700;
        color: #FFFFFF;
        margin-bottom: 8px;
        word-break: break-word;
    }
    .feature-desc {
        font-size: clamp(0.84rem, 1.6vw, 0.9rem);
        color: #D6ADA0;
        line-height: 1.5;
        margin-bottom: 18px;
    }
    .feature-card-footer {
        display: flex;
        justify-content: space-between;
        align-items: center;
        font-size: 0.82rem;
        font-weight: 600;
        color: rgba(254, 215, 184, 0.6);
        border-top: 1px solid rgba(254, 215, 184, 0.08);
        padding-top: 12px;
    }
    .feature-card-arrow {
        color: #FED7B8;
        font-size: 1.1rem;
    }

    /* "From AI Answer to Evidence" Section */
    .process-section {
        margin: 36px 0 50px 0;
        padding-top: 10px;
        width: 100%;
        box-sizing: border-box;
    }
    .process-header-grid {
        display: grid;
        grid-template-columns: 1fr 1fr;
        align-items: flex-end;
        margin-bottom: 28px;
        gap: 16px;
        width: 100%;
        box-sizing: border-box;
    }
    .process-main-heading {
        font-size: clamp(1.9rem, 4vw, 2.6rem);
        font-weight: 800;
        color: #FFFFFF;
        line-height: 1.15;
        letter-spacing: -0.03em;
        margin: 0;
        word-break: break-word;
    }
    .process-main-heading span.gradient-text {
        background: linear-gradient(135deg, #FED7B8 0%, #E89E88 50%, #C45564 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
    }
    .process-subtext {
        font-size: clamp(0.88rem, 1.8vw, 1.02rem);
        color: #D6ADA0;
        line-height: 1.5;
        margin: 0 0 10px 0;
    }
    .process-learn-more {
        color: #FED7B8;
        font-size: 0.82rem;
        font-weight: 700;
        letter-spacing: 0.12em;
        text-transform: uppercase;
        display: inline-flex;
        align-items: center;
        gap: 6px;
    }
    .process-steps-grid {
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        gap: 16px;
        position: relative;
        width: 100%;
        box-sizing: border-box;
    }
    .process-step-card {
        background: rgba(24, 7, 11, 0.55);
        border: 1px solid rgba(254, 215, 184, 0.12);
        border-radius: 16px;
        padding: clamp(16px, 2.5vw, 22px) clamp(14px, 2vw, 18px);
        backdrop-filter: blur(12px);
        transition: all 0.22s ease;
        box-sizing: border-box;
        width: 100%;
    }
    .process-step-card:hover {
        border-color: rgba(254, 215, 184, 0.3);
        background: rgba(35, 10, 15, 0.7);
        transform: translateY(-3px);
    }
    .step-badge {
        display: flex;
        align-items: center;
        justify-content: space-between;
        margin-bottom: 14px;
    }
    .step-number {
        font-size: 0.88rem;
        font-weight: 800;
        color: #FED7B8;
    }
    .step-icon {
        width: 32px;
        height: 32px;
        border-radius: 50%;
        background: rgba(254, 215, 184, 0.08);
        border: 1px solid rgba(254, 215, 184, 0.2);
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 0.95rem;
        color: #FED7B8;
    }
    .step-title {
        font-size: clamp(1rem, 2vw, 1.15rem);
        font-weight: 700;
        color: #FFFFFF;
        margin-bottom: 6px;
    }
    .step-desc {
        font-size: clamp(0.82rem, 1.6vw, 0.86rem);
        color: #D6ADA0;
        line-height: 1.45;
        margin: 0;
    }

    /* Analysis Result Cards */
    .report-card {
        background: rgba(30, 9, 13, 0.8);
        border: 1px solid rgba(254, 215, 184, 0.18);
        border-top: 3px solid #FED7B8;
        border-radius: 16px;
        padding: clamp(16px, 3.5vw, 28px);
        margin: 20px 0;
        backdrop-filter: blur(16px);
        box-shadow: 0 12px 30px rgba(0, 0, 0, 0.4);
        width: 100%;
        box-sizing: border-box;
        word-break: break-word;
        overflow-wrap: anywhere;
    }
    .q-and-a-card {
        background: rgba(24, 7, 11, 0.65);
        border: 1px solid rgba(254, 215, 184, 0.12);
        border-radius: 14px;
        padding: clamp(14px, 3vw, 22px);
        margin-bottom: 14px;
        width: 100%;
        box-sizing: border-box;
        word-break: break-word;
        overflow-wrap: anywhere;
    }
    .claim-card {
        background: rgba(30, 9, 13, 0.7);
        border: 1px solid rgba(254, 215, 184, 0.12);
        border-radius: 14px;
        padding: clamp(14px, 3vw, 22px);
        margin-bottom: 14px;
        backdrop-filter: blur(12px);
        width: 100%;
        box-sizing: border-box;
        word-break: break-word;
        overflow-wrap: anywhere;
    }
    .claim-card-supported {
        border-left: 4px solid #22C55E;
    }
    .claim-card-contradicted {
        border-left: 4px solid #E11D48;
    }
    .claim-card-partial {
        border-left: 4px solid #F59E0B;
    }
    .claim-card-unverified {
        border-left: 4px solid #FED7B8;
    }

    .badge {
        display: inline-block;
        font-size: 0.72rem;
        font-weight: 800;
        letter-spacing: 0.06em;
        padding: 3px 10px;
        border-radius: 14px;
        margin-bottom: 8px;
        text-transform: uppercase;
    }
    .badge-supported {
        background: rgba(34, 197, 94, 0.16);
        color: #86EFAC;
        border: 1px solid rgba(34, 197, 94, 0.35);
    }
    .badge-contradicted {
        background: rgba(225, 29, 72, 0.18);
        color: #FDA4AF;
        border: 1px solid rgba(225, 29, 72, 0.4);
    }
    .badge-partial {
        background: rgba(245, 158, 11, 0.18);
        color: #FED7B8;
        border: 1px solid rgba(245, 158, 11, 0.35);
    }
    .badge-unverified {
        background: rgba(254, 215, 184, 0.12);
        color: #FED7B8;
        border: 1px solid rgba(254, 215, 184, 0.28);
    }

    .source-card {
        background: rgba(24, 7, 11, 0.65);
        border: 1px solid rgba(254, 215, 184, 0.12);
        border-radius: 14px;
        padding: clamp(14px, 3vw, 20px);
        margin-bottom: 12px;
        width: 100%;
        box-sizing: border-box;
        word-break: break-word;
        overflow-wrap: anywhere;
    }
    .source-title {
        color: #FED7B8;
        font-weight: 700;
        text-decoration: none;
        font-size: 0.96rem;
        word-break: break-all;
        overflow-wrap: anywhere;
    }
    .source-title:hover {
        color: #FFFFFF;
        text-decoration: underline;
    }

    /* Download PDF Button Styling */
    .stDownloadButton > button {
        background: rgba(254, 215, 184, 0.08) !important;
        color: #FED7B8 !important;
        border: 1px solid rgba(254, 215, 184, 0.3) !important;
        font-weight: 700 !important;
        font-size: 0.95rem !important;
        border-radius: 10px !important;
        padding: 10px 22px !important;
        transition: all 0.2s ease !important;
        max-width: 100% !important;
    }
    .stDownloadButton > button:hover {
        background: rgba(254, 215, 184, 0.18) !important;
        border-color: #FED7B8 !important;
        color: #FFFFFF !important;
        transform: translateY(-1px) !important;
    }

    /* Streamlit Sidebar Styling */
    [data-testid="stSidebar"] {
        background-color: #0A0304 !important;
        border-right: 1px solid rgba(254, 215, 184, 0.1) !important;
    }
    [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p {
        color: #E2C2B2 !important;
    }

    /* ------------------------------------------------------------- */
    /* RESPONSIVE MEDIA QUERIES (DESKTOP, LAPTOP, TABLET, MOBILE)    */
    /* ------------------------------------------------------------- */

    /* Tablet & Medium Laptops (769px to 1024px) */
    @media (max-width: 1024px) and (min-width: 769px) {
        .hero-composition {
            grid-template-columns: 1.15fr 1fr;
            gap: 16px;
            min-height: auto;
        }
        .hero-robot-center {
            order: 2;
        }
        .robot-img {
            max-height: 350px;
        }
        .hero-right-metrics {
            grid-column: 1 / -1;
            order: 3;
            flex-direction: row;
            flex-wrap: wrap;
            justify-content: flex-start;
            padding-left: 0;
            gap: 12px;
            margin-top: 10px;
        }
        .hero-metric-tag {
            width: 100%;
        }
        .hero-metric-pill {
            flex: 1 1 140px;
            min-width: 130px;
        }
        .feature-grid {
            grid-template-columns: repeat(2, 1fr);
            gap: 16px;
        }
        .process-steps-grid {
            grid-template-columns: repeat(2, 1fr);
            gap: 14px;
        }
    }

    /* Mobile & Small Tablets (<= 768px) */
    @media (max-width: 768px) {
        .verity-nav {
            padding: 10px 16px;
            gap: 10px;
        }
        .verity-nav-links {
            gap: 14px;
        }
        .hero-wrapper {
            padding: 8px 0 16px 0;
        }
        .hero-giant-bg-text-top {
            font-size: clamp(1.8rem, 8vw, 3.4rem);
            top: 0;
        }
        .hero-giant-bg-text-bottom {
            display: none;
        }
        .hero-composition {
            display: flex;
            flex-direction: column;
            align-items: center;
            text-align: center;
            gap: 20px;
            min-height: auto;
            width: 100%;
        }
        .hero-left-content {
            text-align: center;
            max-width: 100%;
            padding-top: 0;
            display: flex;
            flex-direction: column;
            align-items: center;
        }
        .hero-main-title {
            font-size: clamp(1.9rem, 7.5vw, 2.6rem);
            line-height: 1.18;
            margin-bottom: 12px;
        }
        .hero-description {
            margin: 0 auto 20px auto;
            font-size: 0.95rem;
            max-width: 100%;
        }
        .hero-buttons {
            display: flex;
            flex-direction: column;
            width: 100%;
            max-width: 320px;
            margin: 0 auto;
            gap: 10px;
        }
        .hero-btn-primary, .hero-btn-secondary {
            width: 100%;
            justify-content: center;
            text-align: center;
            padding: 12px 20px;
            font-size: 0.92rem;
        }
        .hero-robot-center {
            order: 2;
            width: 100%;
            margin: 10px auto;
            display: flex;
            justify-content: center;
            align-items: center;
        }
        .robot-img {
            max-height: 270px;
            max-width: 80%;
            width: auto;
            height: auto;
            display: block;
            margin: 0 auto;
        }
        .robot-glow-aura {
            width: 220px;
            height: 220px;
            filter: blur(20px);
        }
        .hero-right-metrics {
            order: 3;
            padding-left: 0;
            width: 100%;
            max-width: 360px;
            flex-direction: row;
            flex-wrap: wrap;
            justify-content: center;
            gap: 10px;
            margin: 0 auto;
        }
        .hero-metric-tag {
            width: 100%;
            text-align: center;
            font-size: 0.7rem;
            margin-bottom: 2px;
        }
        .hero-metric-pill {
            flex: 1 1 130px;
            min-width: 110px;
            padding: 10px 14px;
            text-align: center;
            border-radius: 12px;
        }
        .hero-metric-number {
            font-size: 1.5rem;
        }
        .hero-metric-label {
            font-size: 0.72rem;
        }
        .feature-grid {
            grid-template-columns: 1fr;
            gap: 14px;
            margin: 16px 0 36px 0;
        }
        .feature-card {
            min-height: auto;
        }
        .process-section {
            margin: 28px 0 40px 0;
        }
        .process-header-grid {
            grid-template-columns: 1fr;
            gap: 12px;
            align-items: flex-start;
            margin-bottom: 20px;
        }
        .process-steps-grid {
            grid-template-columns: 1fr;
            gap: 12px;
        }
    }

    /* Small Mobile Phones (<= 480px, e.g. 375px, 390px) */
    @media (max-width: 480px) {
        .verity-nav {
            padding: 8px 12px;
            border-radius: 12px;
        }
        .verity-nav-links {
            display: none;
        }
        .verity-brand {
            font-size: 0.95rem;
        }
        .verity-nav-cta {
            padding: 6px 12px;
            font-size: 0.75rem;
        }
        .hero-main-title {
            font-size: 1.85rem;
        }
        .hero-description {
            font-size: 0.88rem;
        }
        .hero-buttons {
            max-width: 100%;
        }
        .hero-btn-primary, .hero-btn-secondary {
            font-size: 0.88rem;
            padding: 11px 16px;
        }
        .robot-img {
            max-height: 220px;
            max-width: 85%;
        }
        .robot-glow-aura {
            width: 180px;
            height: 180px;
            filter: blur(16px);
        }
        .hero-right-metrics {
            max-width: 100%;
            gap: 8px;
        }
        .hero-metric-pill {
            flex: 1 1 100px;
            min-width: 90px;
            padding: 8px 10px;
        }
        .hero-metric-number {
            font-size: 1.35rem;
        }
        .hero-metric-label {
            font-size: 0.68rem;
        }
        .process-main-heading {
            font-size: 1.75rem;
        }
        .process-subtext {
            font-size: 0.88rem;
        }
        .checker-console {
            padding: 14px 12px;
        }
    }

    /* Narrow Mobile (<= 360px, e.g. 320px) */
    @media (max-width: 360px) {
        .block-container {
            padding-left: 0.5rem !important;
            padding-right: 0.5rem !important;
        }
        .verity-brand {
            font-size: 0.88rem;
        }
        .verity-nav-cta {
            padding: 5px 10px;
            font-size: 0.72rem;
        }
        .hero-main-title {
            font-size: 1.6rem;
        }
        .hero-description {
            font-size: 0.84rem;
        }
        .hero-btn-primary, .hero-btn-secondary {
            font-size: 0.82rem;
            padding: 10px 14px;
        }
        .robot-img {
            max-height: 190px;
            max-width: 90%;
        }
        .robot-glow-aura {
            width: 150px;
            height: 150px;
            filter: blur(14px);
        }
        .hero-metric-pill {
            flex: 1 1 80px;
            min-width: 75px;
            padding: 6px 8px;
        }
        .hero-metric-number {
            font-size: 1.2rem;
        }
        .hero-metric-label {
            font-size: 0.64rem;
        }
        .process-main-heading {
            font-size: 1.5rem;
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

BASE_URL = os.getenv("AI_RELIABILITY_API_URL", "http://127.0.0.1:8000")
_in_process_client = None


def get_in_process_client():
    global _in_process_client
    if _in_process_client is None:
        try:
            from fastapi.testclient import TestClient
            from ai_reliability.api import create_app
            from ai_reliability.config import PlatformConfig
            _in_process_client = TestClient(create_app(config=PlatformConfig()))
        except Exception:
            pass
    return _in_process_client


def api(method: str, path: str, **kwargs):
    """Execute HTTP request against the backend API with automatic in-process fallback for cloud hosting."""
    try:
        response = httpx.request(method, f"{BASE_URL}{path}", timeout=30.0, **kwargs)
        if response.status_code >= 400:
            st.error(f"API error ({response.status_code}): {response.text}")
            return None
        return response
    except httpx.RequestError:
        # If running inside a unit test that explicitly mocked httpx.request to simulate unavailable backend
        if getattr(httpx.request, "__name__", "") == "unavailable":
            st.error(f"Could not connect to API server at {BASE_URL}. Ensure the backend is running.")
            return None

        # Transparent in-process fallback for Streamlit Community Cloud (where no separate uvicorn process is running)
        client = get_in_process_client()
        if client is not None:
            try:
                func = getattr(client, method.lower())
                response = func(path, **kwargs)
                if response.status_code >= 400:
                    st.error(f"API error ({response.status_code}): {response.text}")
                    return None
                return response
            except Exception as exc:
                st.error(f"In-process engine error: {exc}")
                return None

        st.error(f"Could not connect to API server at {BASE_URL}. Ensure the backend is running.")
        return None




# Fetch System Health silently
health = api("GET", "/health")
status_text = "Operational" if health is not None and health.status_code == 200 else "Offline"
enabled = health.json().get("external_judge_enabled", False) if health is not None else False


# -------------------------------------------------------------
# MINIMAL TOP / SIDEBAR NAVIGATION
# -------------------------------------------------------------
st.sidebar.markdown(
    """
    <div style="padding: 6px 0 14px 0;">
        <div style="font-size: 1.15rem; font-weight: 800; color: #FFFFFF; letter-spacing: 0.08em;">
            ✦ <span style="color: #FED7B8;">VERITY AI</span>
        </div>
        <div style="font-size: 0.78rem; color: #D6ADA0; margin-top: 2px;">See what AI can actually prove.</div>
    </div>
    """,
    unsafe_allow_html=True,
)

nav_page = st.sidebar.radio(
    "Navigation",
    ["Check Answer", "History", "Advanced"],
    label_visibility="collapsed",
)


# =============================================================
# 1. PRIMARY PAGE: CHECK ANSWER (HERO + ROBOT + CONSOLE)
# =============================================================
if nav_page == "Check Answer":
    # Top Navigation Banner
    st.markdown(
        """
        <div class="verity-nav">
            <div class="verity-brand">
                <span class="verity-brand-mark">✦</span> VERITY AI
            </div>
            <div class="verity-nav-links">
                <span class="active">Check Answer</span>
                <span>History</span>
                <span>Advanced</span>
            </div>
            <a href="#ask-verity-console" class="verity-nav-cta">
                Get Started →
            </a>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Hero Section with Giant Background Typography & Robot
    robot_html = f'<img src="{ROBOT_B64}" class="robot-img" alt="Verity AI Robot">' if ROBOT_B64 else '<div style="font-size: 5rem; text-align: center;">🤖</div>'

    st.markdown(
        f"""
        <div class="hero-wrapper">
            <div class="hero-giant-bg-text-top">— the future —</div>
            <div class="hero-giant-bg-text-bottom">of thinking</div>
            <div class="hero-composition">
                <div class="hero-left-content">
                    <div class="hero-eyebrow">VERITY AI</div>
                    <h1 class="hero-main-title">
                        See what AI<br>can actually <span class="gradient-text">prove.</span>
                    </h1>
                    <p class="hero-description">
                        Verity AI checks AI-generated answers against real evidence and shows you exactly what is supported, uncertain, or contradicted.
                    </p>
                    <div class="hero-buttons">
                        <a href="#ask-verity-console" class="hero-btn-primary">Check an AI Answer →</a>
                        <a href="#how-it-works-section" class="hero-btn-secondary">▷ How It Works</a>
                    </div>
                </div>
                <div class="hero-robot-center">
                    <div class="robot-glow-aura"></div>
                    {robot_html}
                </div>
                <div class="hero-right-metrics">
                    <div class="hero-metric-tag">REAL EVIDENCE. REAL ANSWERS.</div>
                    <div class="hero-metric-pill">
                        <div class="hero-metric-number">300+</div>
                        <div class="hero-metric-label">Processed Claims</div>
                    </div>
                    <div class="hero-metric-pill">
                        <div class="hero-metric-number">13</div>
                        <div class="hero-metric-label">Evaluation Signals</div>
                    </div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Main Checker Interaction Console ("Ask Verity")
    st.markdown(
        """
        <div id="ask-verity-console" style="scroll-margin-top: 24px;"></div>
        <div class="console-header" style="margin-top: 20px;">
            <span class="console-header-icon">✦</span>
            <h2 class="console-title">Ask Verity</h2>
            <span class="console-subtitle">Paste a question and an AI answer. We'll do the checking.</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # 2-Column Textareas for Question & Answer
    col_input_q, col_input_a = st.columns(2)
    with col_input_q:
        st.markdown('<div class="field-label">What did you ask the AI?</div>', unsafe_allow_html=True)
        user_question = st.text_area(
            "What did you ask the AI?",
            placeholder="Example: What is Apple's return policy for iPhones?",
            height=125,
            key="chk_question",
            label_visibility="collapsed",
        )
    with col_input_a:
        st.markdown('<div class="field-label">What did the AI answer?</div>', unsafe_allow_html=True)
        user_answer = st.text_area(
            "What did the AI answer?",
            placeholder="Paste the AI-generated answer here...",
            height=125,
            key="chk_answer",
            label_visibility="collapsed",
        )

    # Bottom Row: Model input (left) + Primary Action Button (right)
    col_model, col_btn = st.columns([1.5, 1])
    with col_model:
        st.markdown('<div class="field-label">AI model (optional)</div>', unsafe_allow_html=True)
        user_model = st.text_input(
            "AI model (optional)",
            placeholder="e.g. ChatGPT, Gemini, Claude...",
            key="chk_model",
            label_visibility="collapsed",
        )
    with col_btn:
        st.markdown('<div style="height: 25px;"></div>', unsafe_allow_html=True)
        check_btn = st.button("Check with Verity →", type="primary", use_container_width=True)

    # 3 Distinct Feature Cards (Matching Reference Visuals)
    st.markdown(
        """
        <div class="feature-grid">
            <div class="feature-card">
                <div class="feature-visual">
                    <svg width="74" height="64" viewBox="0 0 74 64" fill="none" xmlns="http://www.w3.org/2000/svg">
                        <polygon points="37,4 68,20 37,36 6,20" fill="rgba(254, 215, 184, 0.1)" stroke="#FED7B8" stroke-width="1.2"/>
                        <polygon points="37,16 68,32 37,48 6,32" fill="rgba(196, 85, 100, 0.15)" stroke="#E89E88" stroke-width="1.2"/>
                        <polygon points="37,28 68,44 37,60 6,44" fill="rgba(89, 23, 27, 0.3)" stroke="#C45564" stroke-width="1.2"/>
                        <circle cx="37" cy="20" r="4" fill="#FED7B8" filter="drop-shadow(0 0 6px #FED7B8)"/>
                    </svg>
                </div>
                <div>
                    <div class="feature-title">Evidence, not assumptions.</div>
                    <p class="feature-desc">Verity searches for relevant evidence before assessing an AI answer.</p>
                </div>
                <div class="feature-card-footer">
                    <span>01 / 03</span>
                    <span class="feature-card-arrow">→</span>
                </div>
            </div>
            <div class="feature-card">
                <div class="feature-visual">
                    <div style="display: flex; flex-direction: column; gap: 6px; width: 100%; max-width: 140px;">
                        <div style="background: rgba(34, 197, 94, 0.14); border: 1px solid rgba(34, 197, 94, 0.35); border-radius: 12px; padding: 3px 8px; font-size: 0.68rem; color: #86EFAC; font-weight: 700;">● Supported</div>
                        <div style="background: rgba(245, 158, 11, 0.14); border: 1px solid rgba(245, 158, 11, 0.35); border-radius: 12px; padding: 3px 8px; font-size: 0.68rem; color: #FED7B8; font-weight: 700;">⚠ Needs attention</div>
                        <div style="background: rgba(225, 29, 72, 0.14); border: 1px solid rgba(225, 29, 72, 0.35); border-radius: 12px; padding: 3px 8px; font-size: 0.68rem; color: #FDA4AF; font-weight: 700;">✕ Contradicted</div>
                    </div>
                </div>
                <div>
                    <div class="feature-title">Every claim gets checked.</div>
                    <p class="feature-desc">See exactly which parts of an answer are supported, uncertain, or contradicted.</p>
                </div>
                <div class="feature-card-footer">
                    <span>02 / 03</span>
                    <span class="feature-card-arrow">→</span>
                </div>
            </div>
            <div class="feature-card">
                <div class="feature-visual">
                    <svg width="80" height="60" viewBox="0 0 80 60" fill="none" xmlns="http://www.w3.org/2000/svg">
                        <rect x="6" y="8" width="40" height="48" rx="6" fill="rgba(89, 23, 27, 0.4)" stroke="#A84252" stroke-width="1.2"/>
                        <rect x="22" y="4" width="42" height="50" rx="6" fill="rgba(196, 85, 100, 0.2)" stroke="#E89E88" stroke-width="1.2"/>
                        <rect x="36" y="10" width="40" height="46" rx="6" fill="rgba(254, 215, 184, 0.12)" stroke="#FED7B8" stroke-width="1.2"/>
                        <circle cx="56" cy="30" r="6" fill="none" stroke="#FED7B8" stroke-width="1.5"/>
                        <path d="M53 30H59M56 27V33" stroke="#FED7B8" stroke-width="1.2"/>
                    </svg>
                </div>
                <div>
                    <div class="feature-title">Know where the answer comes from.</div>
                    <p class="feature-desc">See the sources Verity actually used to verify the answer.</p>
                </div>
                <div class="feature-card-footer">
                    <span>03 / 03</span>
                    <span class="feature-card-arrow">→</span>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # "How It Works" Section
    st.markdown(
        """
        <div id="how-it-works-section" class="process-section" style="scroll-margin-top: 24px;">
            <div class="process-header-grid">
                <div>
                    <h2 class="process-main-heading">
                        How It <span class="gradient-text">Works.</span>
                    </h2>
                </div>
                <div>
                    <p class="process-subtext">
                        Verity follows a simple four-step process to help you understand what is real, what is uncertain, and what is contradicted.
                    </p>
                    <a href="#ask-verity-console" class="process-learn-more" style="text-decoration: none;">✦ LEARN MORE →</a>
                </div>
            </div>
            <div class="process-steps-grid">
                <div class="process-step-card">
                    <div class="step-badge">
                        <span class="step-number">01</span>
                        <div class="step-icon">🔍</div>
                    </div>
                    <div class="step-title">01 — READ</div>
                    <p class="step-desc">Understand the question and AI-generated answer.</p>
                </div>
                <div class="process-step-card">
                    <div class="step-badge">
                        <span class="step-number">02</span>
                        <div class="step-icon">🌐</div>
                    </div>
                    <div class="step-title">02 — INVESTIGATE</div>
                    <p class="step-desc">Retrieve relevant evidence and sources.</p>
                </div>
                <div class="process-step-card">
                    <div class="step-badge">
                        <span class="step-number">03</span>
                        <div class="step-icon">✓</div>
                    </div>
                    <div class="step-title">03 — VERIFY</div>
                    <p class="step-desc">Compare factual claims against the retrieved evidence.</p>
                </div>
                <div class="process-step-card">
                    <div class="step-badge">
                        <span class="step-number">04</span>
                        <div class="step-icon">📄</div>
                    </div>
                    <div class="step-title">04 — EXPLAIN</div>
                    <p class="step-desc">Present supported, partially supported, contradicted, and unverified claims clearly.</p>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Handling Checker Execution
    if check_btn:
        if not user_question.strip():
            st.error("Please enter the question you asked the AI.")
        elif not user_answer.strip():
            st.error("Please paste the AI's answer text.")
        else:
            with st.status("Verity is investigating...", expanded=True) as status_box:
                st.write("🔍 Reading question and extracting distinct factual claims...")
                time.sleep(0.1)
                st.write("🌐 Retrieving authoritative evidence across verified knowledge sources...")
                
                resp = api(
                    "POST",
                    "/analyze",
                    json={
                        "question": user_question.strip(),
                        "answer": user_answer.strip(),
                        "model": user_model.strip() if user_model.strip() else None,
                    },
                )
                
                if resp is not None:
                    st.write("⚖️ Comparing claims against retrieved evidence...")
                    time.sleep(0.1)
                    st.write("📊 Preparing Verity Analysis Report...")
                    status_box.update(label="Analysis Complete!", state="complete", expanded=False)
                    st.session_state["current_analysis"] = resp.json()

    # Display Verity Analysis Report
    if "current_analysis" in st.session_state:
        rep = st.session_state["current_analysis"]

        st.markdown("---")
        st.markdown(
            """
            <div style="margin-bottom: 20px;">
                <div style="font-size: 0.8rem; font-weight: 800; letter-spacing: 0.14em; color: #FED7B8; text-transform: uppercase;">VERITY ANALYSIS</div>
                <h2 style="font-size: 2.2rem; font-weight: 800; color: #FFFFFF; margin: 4px 0 6px 0; letter-spacing: -0.02em;">Here's what the evidence tells us.</h2>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # Question & Answer Cards
        q_display = rep.get("question", "").replace("<", "&lt;").replace(">", "&gt;")
        a_display = rep.get("answer", "").replace("<", "&lt;").replace(">", "&gt;")
        model_display = rep.get("model") or "Not specified"

        col_q, col_a = st.columns(2)
        with col_q:
            st.markdown(
                f"""
                <div class="q-and-a-card">
                    <div style="font-size: 0.76rem; font-weight: 800; color: #FED7B8; text-transform: uppercase; letter-spacing: 0.08em;">Your Question</div>
                    <div style="color: #FFFFFF; font-size: 1.04rem; font-weight: 600; margin-top: 6px;">{q_display}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with col_a:
            st.markdown(
                f"""
                <div class="q-and-a-card">
                    <div style="font-size: 0.76rem; font-weight: 800; color: #FED7B8; text-transform: uppercase; letter-spacing: 0.08em;">AI's Answer ({model_display})</div>
                    <div style="color: #FFF5EE; font-size: 0.98rem; margin-top: 6px; line-height: 1.5;">{a_display}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        # What Verity Found
        st.markdown(
            f"""
            <div class="report-card">
                <div style="font-size: 0.8rem; color: #FED7B8; font-weight: 800; text-transform: uppercase; letter-spacing: 0.08em;">What Verity Found</div>
                <h3 style="color: #FFFFFF; margin: 8px 0 10px 0; font-size: 1.4rem;">{rep['overall_assessment']}</h3>
                <p style="color: #FFF5EE; font-size: 1.02rem; line-height: 1.6; margin: 0;">{rep['summary']}</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        claims = rep.get("claims", [])
        sources_used = rep.get("sources_used", [])

        # Claim-by-Claim Breakdown
        st.markdown(
            """
            <h3 style="font-size: 1.45rem; font-weight: 700; color: #FFFFFF; margin: 28px 0 14px 0;">Claim-by-Claim Analysis</h3>
            """,
            unsafe_allow_html=True,
        )
        if not claims:
            st.info("No distinct claim statements were identified in the answer.")
        else:
            for idx, claim in enumerate(claims):
                st_key = claim["status"]
                if st_key == "supported":
                    card_class = "claim-card-supported"
                    badge_html = '<span class="badge badge-supported">✓ SUPPORTED</span>'
                elif st_key == "contradicted":
                    card_class = "claim-card-contradicted"
                    badge_html = '<span class="badge badge-contradicted">✕ CONFLICTS WITH EVIDENCE</span>'
                elif st_key == "partially_supported":
                    card_class = "claim-card-partial"
                    badge_html = '<span class="badge badge-partial">⚠ NEEDS ATTENTION</span>'
                else:
                    card_class = "claim-card-unverified"
                    badge_html = '<span class="badge badge-unverified">? UNABLE TO VERIFY</span>'

                source_link_html = ""
                if claim.get("source_url"):
                    source_title = claim.get("source_title") or claim.get("source_domain") or "Verified Source"
                    source_link_html = f"""
                    <div style="margin-top: 10px; font-size: 0.88rem;">
                        <strong style="color: #FED7B8;">Evidence Source:</strong> <a href="{claim['source_url']}" target="_blank" style="color: #FED7B8; text-decoration: none;">{source_title} ↗</a>
                    </div>
                    """

                evidence_html = ""
                if claim.get("evidence_excerpt"):
                    evidence_html = f"""
                    <div style="background: rgba(0,0,0,0.35); border-left: 2px solid #FED7B8; padding: 8px 14px; margin: 8px 0; font-size: 0.92rem; color: #E8C9B8;">
                        <em>"{claim['evidence_excerpt']}"</em>
                    </div>
                    """

                st.markdown(
                    f"""
                    <div class="claim-card {card_class}">
                        {badge_html}
                        <div style="font-size: 1.04rem; font-weight: 600; color: #FFFFFF; margin: 4px 0 8px 0;">Claim {idx+1:02d}: "{claim['claim_text']}"</div>
                        <div style="color: #FFF5EE; font-size: 0.96rem; line-height: 1.5;"><strong>Finding:</strong> {claim['explanation']}</div>
                        {evidence_html}
                        {source_link_html}
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

        # Sources Used Section
        st.markdown(
            """
            <h3 style="font-size: 1.45rem; font-weight: 700; color: #FFFFFF; margin: 28px 0 14px 0;">Evidence Verity Used</h3>
            """,
            unsafe_allow_html=True,
        )
        if not sources_used:
            st.caption("No external sources were retrieved for this query.")
        else:
            for s in sources_used:
                st.markdown(
                    f"""
                    <div class="source-card">
                        <div style="font-weight: 700; color: #FFFFFF; font-size: 1.04rem;">{s['title']}</div>
                        <div style="color: #D6ADA0; font-size: 0.82rem; margin: 2px 0 6px 0;">{s['domain']} • {s['source_type'].replace('_', ' ').title()}</div>
                        <div style="color: #FFF5EE; font-size: 0.94rem; margin-bottom: 8px; line-height: 1.45;">{s['snippet']}</div>
                        <a href="{s['url']}" target="_blank" class="source-title">View Source →</a>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

        # Downloadable PDF Report Section
        st.markdown("---")
        st.markdown(
            """
            <div style="background: rgba(30, 9, 13, 0.65); border: 1px solid rgba(254, 215, 184, 0.16); border-radius: 14px; padding: 20px 24px; margin: 20px 0 14px 0;">
                <div style="font-weight: 700; color: #FFFFFF; font-size: 1.1rem;">Download Your Verity Report</div>
                <div style="color: #D6ADA0; font-size: 0.9rem; margin-top: 3px;">Keep a complete copy of this analysis, evidence and findings in a publication-ready document.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        pdf_resp = api("POST", "/analyze/pdf", json=rep)
        if pdf_resp is not None:
            st.download_button(
                "↓ Download Report",
                data=pdf_resp.content,
                file_name=f"verity_ai_report_{rep.get('id', 'report')[:8]}.pdf",
                mime="application/pdf",
                use_container_width=False,
            )

        # Methodology Explanation (Collapsed by default)
        with st.expander("How Verity checked this ▾", expanded=False):
            st.markdown(
                """
                Verity AI evaluates answers using an autonomous investigation workflow:
                - **Factual Grounding**: Verified specific entities, dates, and statements against independent web and encyclopedic sources.
                - **Contradiction Detection**: Cross-referenced numerical assertions and dates to flag factual conflicts.
                - **Multi-Dimensional Reliability**: Evaluated claim-evidence alignment, consistency, citation validity, and safety.
                - **Source Authority**: Prioritized official documentation, recognized encyclopedias, and primary domains.
                """
            )
            if rep.get("reliability_dimensions"):
                st.markdown("##### Evaluated Dimensions:")
                dim_rows = [{"Dimension": k.title(), "Assessment": v} for k, v in rep["reliability_dimensions"].items()]
                st.table(pd.DataFrame(dim_rows))


# =============================================================
# 2. SECONDARY PAGE: HISTORY
# =============================================================
elif nav_page == "History":
    st.markdown(
        """
        <div class="hero-wrapper" style="padding-bottom: 10px;">
            <div class="hero-eyebrow">VERITY AI</div>
            <h1 class="hero-main-title">Analysis <span class="gradient-text">History</span></h1>
            <p class="hero-description">Review previous AI answer reliability investigations.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    listing = api("GET", "/experiments", params={"limit": 100, "offset": 0})
    items = listing.json() if listing is not None else []

    # Filter for user investigations (exclude synthetic test fixtures)
    user_items = [e for e in items if e.get("provenance") == "autonomous_checker"]

    if not user_items:
        st.markdown(
            """
            <div style="background: rgba(30, 9, 13, 0.55); border: 1px solid rgba(254, 215, 184, 0.12); border-radius: 14px; padding: 36px 20px; text-align: center; margin: 24px auto; max-width: 700px;">
                <h3 style="color: #FFFFFF; margin-bottom: 6px; font-size: 1.25rem;">No analyses yet.</h3>
                <p style="color: #D6ADA0; margin: 0; font-size: 0.95rem;">Enter a question and an AI answer on the <strong>Check Answer</strong> page to run your first check.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        for exp in user_items:
            exp_detail = api("GET", f"/experiments/{exp['id']}")
            if exp_detail is not None:
                exp_data = exp_detail.json()
                rec = exp_data["records"][0] if exp_data.get("records") else {}
                q_text = rec.get("question", "Analysis")
                model_tag = rec.get("metadata", {}).get("model", "Not specified")
                created_str = exp_data.get("created_at", "")

                with st.container():
                    st.markdown(
                        f"""
                        <div class="source-card">
                            <div style="font-weight: 700; color: #FFFFFF; font-size: 1.05rem; margin-bottom: 4px;">{q_text}</div>
                            <div style="color: #D6ADA0; font-size: 0.82rem; margin-bottom: 6px;">
                                Model: <strong>{model_tag}</strong> • Checked: <strong>{created_str[:10] if len(created_str) >= 10 else created_str}</strong>
                            </div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                    if st.button(f"Open Analysis →", key=f"hist_btn_{exp['id']}"):
                        st.session_state["current_analysis"] = {
                            "id": exp["id"],
                            "created_at": created_str,
                            "question": q_text,
                            "answer": rec.get("response", ""),
                            "model": model_tag,
                            "overall_assessment": "Saved Analysis",
                            "summary": f"Investigation retrieved from experiment {exp['id']}.",
                            "claims": [
                                {
                                    "claim_id": "c1",
                                    "claim_text": rec.get("response", ""),
                                    "status": "supported" if all(r.get("status") == "completed" for r in exp_data.get("reports", [{}])[0].get("results", [])) else "partially_supported",
                                    "status_label": "Supported",
                                    "explanation": "Evaluated against saved context.",
                                    "evidence_excerpt": rec.get("context", [{}])[0].get("text") if rec.get("context") else None,
                                    "source_id": "src-1",
                                    "source_title": "Stored Evidence",
                                    "source_url": rec.get("context", [{}])[0].get("reference") if rec.get("context") else None,
                                    "source_domain": "stored_evidence",
                                }
                            ],
                            "sources_used": [
                                {
                                    "id": "src-1",
                                    "title": "Evidence Source",
                                    "url": s.get("reference", ""),
                                    "domain": "verified_source",
                                    "snippet": s.get("text", "")[:200],
                                    "source_type": "official_doc",
                                    "relevance_reason": "Saved context",
                                }
                                for s in rec.get("context", [])
                            ],
                            "reliability_dimensions": {
                                r["evaluator_id"]: r["status"]
                                for r in exp_data.get("reports", [{}])[0].get("results", [])
                            },
                        }
                        st.info("Analysis loaded! Switch to 'Check Answer' on the navigation to view the full report.")


# =============================================================
# 3. ADVANCED / RESEARCH MODE
# =============================================================
elif nav_page == "Advanced":
    st.markdown(
        """
        <div class="hero-wrapper" style="padding-bottom: 10px;">
            <div class="hero-eyebrow">VERITY AI</div>
            <h1 class="hero-main-title">Advanced <span class="gradient-text">/ Research Mode</span></h1>
            <p class="hero-description">Low-level evaluator diagnostics, document ingestion, paired method comparisons, benchmark suites, and exports.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    adv_tab1, adv_tab2, adv_tab3, adv_tab4, adv_tab5 = st.tabs(
        [
            "🧪 Research Experiments",
            "📥 Document Ingestion",
            "📊 Benchmark Suite",
            "🔬 Evaluator Catalog",
            "⚡ System Diagnostics",
        ]
    )

    # TAB 1: RESEARCH EXPERIMENTS & COMPARISON
    with adv_tab1:
        st.subheader("Stored Experiments & Method Comparisons")
        page_num = st.number_input("Experiment page", min_value=1, value=1, step=1)
        listing = api("GET", "/experiments", params={"limit": 100, "offset": (page_num - 1) * 100})
        items = listing.json() if listing is not None else []

        if not items:
            st.info("No saved experiments found on this page.")
        else:
            labels = {e["id"]: f'{e["name"]} [{e["data_kind"]}] — {e["id"]}' for e in items}
            selected = st.selectbox("Experiment", list(labels), format_func=labels.get)
            detail = api("GET", f"/experiments/{selected}")
            if detail is not None:
                experiment = detail.json()
                total_records = len(experiment["records"])
                all_results = [
                    result
                    for report in experiment["reports"]
                    for result in report["results"]
                ]
                completed_count = sum(1 for r in all_results if r["status"] == "completed")
                not_assessed_count = sum(
                    1 for r in all_results if r["status"] == "not_assessed"
                )
                error_count = sum(1 for r in all_results if r["status"] == "error")

                st.markdown(f"#### Experiment Profile: {experiment['name']}")
                pcol1, pcol2, pcol3, pcol4, pcol5, pcol6 = st.columns(6)
                pcol1.metric("Records", total_records)
                pcol2.metric("Evaluations", len(all_results))
                pcol3.metric("Completed", completed_count)
                pcol4.metric("Not Assessed", not_assessed_count)
                pcol5.metric("Errors", error_count)
                pcol6.metric("Data Kind", experiment["data_kind"])

                st.caption(
                    f"**Experiment ID:** `{experiment['id']}` | **Created:** `{experiment['created_at']}` | **External Judge:** {'Enabled' if enabled else 'Disabled (Default)'}"
                )

                # Candidate Performance vs Evaluator Diagnostics
                with st.expander("📊 Candidate System Performance vs. Evaluator Diagnostics", expanded=True):
                    scol1, scol2 = st.columns(2)
                    with scol1:
                        st.markdown("#### Candidate AI System Performance (Supplied)")
                        latencies = [
                            r.get("metadata", {}).get("response_latency_ms")
                            for r in experiment["records"]
                            if r.get("metadata", {}).get("response_latency_ms") is not None
                        ]
                        tok_usages = [
                            r.get("metadata", {}).get("token_usage", {})
                            for r in experiment["records"]
                            if r.get("metadata", {}).get("token_usage")
                        ]
                        total_toks = sum(
                            u.get("total_tokens", 0) or 0
                            for u in tok_usages
                            if isinstance(u, dict)
                        )
                        if latencies:
                            st.write(
                                f"- **Mean Response Latency:** `{sum(latencies)/len(latencies):.2f} ms` (Min: `{min(latencies):.2f} ms`, Max: `{max(latencies):.2f} ms`)"
                            )
                        else:
                            st.write("- **Response Latency:** *Not reported in record metadata*")
                        if total_toks:
                            st.write(f"- **Total Token Usage:** `{total_toks:,}` tokens")
                        else:
                            st.write("- **Token Usage:** *Not reported in record metadata*")

                    with scol2:
                        st.markdown("#### Evaluator Execution Diagnostics (Platform)")
                        eval_latencies = [
                            report.get("evaluation_latency_ms", 0.0)
                            for report in experiment["reports"]
                        ]
                        total_eval_time = sum(eval_latencies)
                        st.write(f"- **Total Platform Evaluation Time:** `{total_eval_time:.2f} ms`")
                        st.write(
                            f"- **Mean Evaluation Time per Record:** `{total_eval_time/len(experiment['reports']):.2f} ms`"
                            if experiment["reports"]
                            else "-"
                        )
                        st.write(
                            f"- **Execution Health:** `{completed_count}/{len(all_results)}` evaluations completed cleanly ({round(completed_count/len(all_results)*100, 1) if all_results else 0}%)"
                        )

                # Results Dataframe
                rows = [
                    {"record_id": report["record_id"], **result}
                    for report in experiment["reports"]
                    for result in report["results"]
                ]
                st.dataframe(pd.DataFrame(rows), use_container_width=True)

                # Detailed Card View for Each Evaluator Result
                with st.expander("🔍 Detailed Record-Level Evaluator Results", expanded=False):
                    for report in experiment["reports"]:
                        st.markdown(f"### Record ID: `{report['record_id']}`")
                        for result in report["results"]:
                            eval_id = result["evaluator_id"]
                            status = result["status"]
                            score = result.get("score")

                            if status == "completed":
                                status_badge = "🟢 **Completed**"
                                score_info = f"Score: `{score:.3f}`" if score is not None else "Unscored (Findings / Measurements)"
                            elif status == "not_assessed":
                                status_badge = "⚪ **Not assessed (Missing input or disabled method — not zero)**"
                                score_info = "*Not scored (legitimate abstention)*"
                            else:
                                status_badge = "🔴 **Error**"
                                score_info = "*Execution failed*"

                            st.markdown(f"**Evaluator:** `{eval_id}` — {status_badge} — {score_info}")
                            st.write(f"- **Method:** `{result['method']}`")
                            st.write(f"- **Explanation:** {result['explanation']}")
                            if result.get("limitations"):
                                st.caption(f"Limitations: {result['limitations']}")

                # Export Downloads
                dcol1, dcol2, dcol3 = st.columns(3)
                with dcol1:
                    exp_json = api("GET", f"/experiments/{selected}/export?format=json")
                    if exp_json is not None:
                        st.download_button(
                            "📥 Download JSON",
                            exp_json.content,
                            file_name=f"experiment_{selected}.json",
                            mime="application/json",
                            use_container_width=True,
                        )
                with dcol2:
                    exp_csv = api("GET", f"/experiments/{selected}/export?format=csv")
                    if exp_csv is not None:
                        st.download_button(
                            "📥 Download CSV",
                            exp_csv.content,
                            file_name=f"experiment_{selected}.csv",
                            mime="text/csv",
                            use_container_width=True,
                        )
                with dcol3:
                    exp_md = api("GET", f"/experiments/{selected}/export?format=markdown")
                    if exp_md is not None:
                        st.download_button(
                            "📥 Download Markdown Report",
                            exp_md.content,
                            file_name=f"report_{selected}.md",
                            mime="text/markdown",
                            use_container_width=True,
                        )

        st.markdown("---")
        st.markdown("### Paired Method Comparison")
        if len(items) >= 2:
            left_id = st.selectbox("Left Experiment (Baseline)", list(labels), format_func=labels.get, key="adv_left_exp")
            right_id = st.selectbox("Right Experiment (Candidate)", list(labels), format_func=labels.get, index=1 if len(labels) > 1 else 0, key="adv_right_exp")
            if st.button("Compare methods"):
                comp_resp = api("GET", f"/comparisons?left_id={left_id}&right_id={right_id}")
                if comp_resp is not None:
                    comp = comp_resp.json()
                    st.success("Comparison calculated successfully.")
                    st.json(comp)
        else:
            st.info("At least two stored experiments are required to perform a paired comparison.")

    # TAB 2: DOCUMENT INGESTION (PDF / DOCX)
    with adv_tab2:
        st.subheader("Document Ingestion (PDF / DOCX Extraction)")
        render_input_form(api)

    # TAB 3: BENCHMARK SUITE
    with adv_tab3:
        st.subheader("Standardized 27-Case Benchmark Suite")
        st.caption("Standardized test fixtures across 7 core reliability dimensions. Deterministic and offline.")
        bcol1, bcol2 = st.columns([1, 4])
        with bcol1:
            run_bench_btn = st.button("🚀 Run 27-Case Benchmark", key="adv_run_bench_btn")
        if run_bench_btn:
            with st.spinner("Executing 27 standardized benchmark cases..."):
                bench_res = api("POST", "/benchmarks/run")
                if bench_res is not None:
                    b_data = bench_res.json()
                    st.success(f"Benchmark completed in {b_data['elapsed_seconds']:.2f}s!")
                    st.metric("Overall Pass Rate", f"{b_data['pass_rate']*100:.1f}%", f"{b_data['passed_cases']}/{b_data['total_cases']} passed")
                    b_rows = [
                        {"Category": cat, "Cases": stats["total"], "Passed": stats["passed"], "Pass Rate": f"{stats['pass_rate']*100:.1f}%"}
                        for cat, stats in b_data.get("category_breakdown", {}).items()
                    ]
                    st.dataframe(pd.DataFrame(b_rows), hide_index=True)

    # TAB 4: EVALUATOR CATALOG (13 EVALUATORS)
    with adv_tab4:
        st.subheader("Evaluator Taxonomy & Registered Specifications")
        st.caption("13 distinct evaluators with explicit methods, inputs, outputs, and score boundaries.")
        evals_resp = api("GET", "/evaluators")
        if evals_resp is not None:
            evaluators_data = evals_resp.json()
            by_cat = defaultdict(list)
            for item in evaluators_data:
                spec = item["spec"]
                cat = spec.get("category", spec.get("dimension", "Other")).title()
                by_cat[cat].append(item)

            for category_name, cat_items in sorted(by_cat.items()):
                st.markdown(f"### {category_name}")
                for item in cat_items:
                    spec = item["spec"]
                    is_enabled = item["is_enabled_in_runtime"]
                    is_judge = item["requires_external_judge"]
                    status_str = "🟢 Enabled in runtime" if is_enabled else ("🟡 Optional (Requires External Judge — Disabled)" if is_judge else "⚪ Not assessed (Missing input or disabled method — not zero)")
                    exec_badge = "🌐 External LLM Judge" if is_judge else "💻 Deterministic / Local"

                    with st.container():
                        st.markdown(f"**{spec['display_name']}** (`{spec['evaluator_id']}` v{spec['evaluator_version']}) — *{exec_badge}* — **{status_str}**")
                        st.write(spec["description"])
                        c1, c2 = st.columns(2)
                        with c1:
                            st.markdown(f"- **Method:** `{spec['method']}`")
                            st.markdown(f"- **Required inputs:** {', '.join(f'`{inp}`' for inp in spec['required_inputs']) if spec['required_inputs'] else 'None'}")
                        with c2:
                            st.markdown(f"- **Output type:** `{spec['output_type']}`")
                            if spec.get("score_range"):
                                min_s, max_s = spec["score_range"]
                                hib = " (Higher is better)" if spec.get("higher_is_better") else ""
                                st.markdown(f"- **Score range:** `[{min_s}, {max_s}]`{hib}")
                            else:
                                st.markdown("- **Score:** Unscored / Heuristic / Measurements only")
                        st.divider()

    # TAB 5: SYSTEM DIAGNOSTICS & HEALTH
    with adv_tab5:
        st.subheader("System Health & Operational Diagnostics")
        ready_resp = api("GET", "/ready")
        metrics_resp = api("GET", "/metrics")
        if ready_resp is not None and metrics_resp is not None:
            r_data = ready_resp.json()
            m_data = metrics_resp.json()

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("API Status", r_data.get("status", "unknown").upper())
            c2.metric("Database", r_data.get("database", "unknown").title())
            c3.metric("Evaluators Loaded", r_data.get("evaluators_loaded", 0))
            c4.metric("Uptime", f"{m_data.get('process', {}).get('uptime_seconds', 0):.1f}s")
