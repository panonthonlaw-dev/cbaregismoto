import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta
import json
import requests
import base64
import time
import io
import re
import os
import textwrap
import plotly.express as px
from PIL import Image, ImageDraw, ImageFont, ImageOps

# --- ส่วนของ PDF Library ---
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader

# ✅ 1. ฟังก์ชันระบบ (Copy จากตัวเดิมที่เสถียร)
def start_loading():
    st.session_state.is_loading = True

def sanitize_for_gsheet(text):
    if text is None: return ""
    text_str = str(text)
    if text_str.startswith(("=", "+", "-", "@")):
        return "'" + text_str
    return text_str

def get_img_link(url):
    match = re.search(r'/d/([a-zA-Z0-9_-]+)|id=([a-zA-Z0-9_-]+)', str(url))
    file_id = match.group(1) or match.group(2) if match else None
    return f"https://drive.google.com/thumbnail?id={file_id}&sz=w800" if file_id else url

# --- 2. ตั้งค่า (Config - ดึงจาก Secrets 100%) ---
SHEET_NAME = st.secrets["SHEET_NAME"]
DRIVE_FOLDER_ID = st.secrets["DRIVE_FOLDER_ID"]
GAS_APP_URL = st.secrets["GAS_APP_URL"]
UPGRADE_PASSWORD = st.secrets["UPGRADE_PASSWORD"] 
OFFICER_ACCOUNTS = st.secrets["OFFICER_ACCOUNTS"]
SESSION_TIMEOUT_MINUTES = 30 

# --- 3. Setup หน้าเว็บ ---
st.set_page_config(page_title=f"จราจร {SHEET_NAME}", page_icon="🏍️", layout="wide")

# --- 4. จัดการ Session State ---
if 'page' not in st.session_state: st.session_state['page'] = 'student'
if 'is_loading' not in st.session_state: st.session_state['is_loading'] = False
if 'logged_in' not in st.session_state: st.session_state['logged_in'] = False
if 'officer_name' not in st.session_state: st.session_state['officer_name'] = ""
if 'officer_role' not in st.session_state: st.session_state['officer_role'] = ""
if 'current_user_pwd' not in st.session_state: st.session_state['current_user_pwd'] = ""
if 'search_results_df' not in st.session_state: st.session_state['search_results_df'] = None
if 'edit_data' not in st.session_state: st.session_state['edit_data'] = None

def go_to_page(page_name): 
    st.session_state['page'] = page_name
    st.rerun()

def connect_gsheet():
    try:
        key_content = st.secrets["textkey"]["json_content"].strip()
        if "\\n" not in key_content:
            key_content = key_content.replace("\n", "\\n")
        key_dict = json.loads(key_content, strict=False)
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(key_dict, scope)
        client = gspread.authorize(creds)
        return client.open(SHEET_NAME).sheet1
    except Exception as e:
        st.error(f"❌ ปัญหากุญแจ JSON: {e}")
        st.stop()

def upload_to_drive(file_obj, filename):
    if not file_obj: return ""
    base64_str = base64.b64encode(file_obj.getvalue()).decode('utf-8')
    payload = {"folder_id": DRIVE_FOLDER_ID, "filename": filename, "file": base64_str, "mimeType": "image/jpeg"}
    try:
        res = requests.post(GAS_APP_URL, json=payload).json()
        return res.get("link") if res.get("status") == "success" else None
    except: return None

# --- 🎨 CSS (Copy จากชุดที่สวยและเสถียร) ---
st.markdown("""
    <style>
        .atm-card {
            width: 100%; max-width: 450px; aspect-ratio: 1.586;
            background: #ffffff; border-radius: 15px; border: 2px solid #cbd5e1;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
            padding: 20px; position: relative; margin: auto;
        }
        .atm-school-name { font-size: 16px; font-weight: bold; color: #1e293b; }
        .atm-photo { width: 100px; height: 125px; border-radius: 8px; object-fit: cover; border: 1px solid #cbd5e1; }
        .atm-score-val { font-size: 32px; font-weight: 800; color: #16a34a; }
    </style>
""", unsafe_allow_html=True)

# --- 5. Main UI ---
logo_path = next((f for f in ["logo.png", "logo.jpg", "logo"] if os.path.exists(f)), None)
c_logo, c_title = st.columns([1, 8])
with c_logo: 
    if logo_path: st.image(logo_path, width=90)
with c_title: st.title(f"ระบบจราจร {SHEET_NAME}")

if st.session_state['page'] == 'student':
    st.info("📝 ลงทะเบียนรถและทำบัตรอนุญาตดิจิทัล")
    with st.form("reg_form"):
        sc1, sc2 = st.columns(2)
        with sc1:
            prefix = st.selectbox("คำนำหน้า", ["นาย", "นางสาว", "เด็กชาย", "เด็กหญิง", "นาง", "ครู"])
            fname = st.text_input("ชื่อ-นามสกุล", key="f_name")
        std_id = sc2.text_input("รหัสประจำตัว", key="f_id")
        
        sc3, sc4 = st.columns(2)
        level = sc3.selectbox("ชั้น", ["ม.1", "ม.2", "ม.3", "ม.4", "ม.5", "ม.6", "ครู,บุคลากร", "บุคคลภายนอก"])
        room = sc4.text_input("ห้อง (ถ้ามี)", key="f_room")
        
        pin = st.text_input("ตั้งรหัส PIN 6 หลัก", type="password", max_chars=6, key="f_pin")
        
        sc5, sc6 = st.columns(2)
        brand = sc5.selectbox("ยี่ห้อรถ", ["Honda", "Yamaha", "Suzuki", "GPX", "Kawasaki", "อื่นๆ"])
        plate = st.text_input("ทะเบียนรถ", key="f_plate")
        
        up1, up2 = st.columns(2)
        p_face = up1.file_uploader("1. รูปเจ้าของรถ", type=['jpg','png','jpeg'])
        p_back = up2.file_uploader("2. รูปหลังรถ (ป้ายทะเบียน)", type=['jpg','png','jpeg'])
        
        pdpa = st.checkbox("ยินยอมให้เก็บข้อมูลตามนโยบายโรงเรียน")
        
        submit_btn = st.form_submit_button("ส่งข้อมูลลงทะเบียน", type="primary", use_container_width=True, on_click=start_loading, disabled=st.session_state.is_loading)

        if submit_btn:
            # เช็คละเอียดว่าขาดอะไร
            errors = []
            if not fname: errors.append("ชื่อ-นามสกุล")
            if not std_id: errors.append("รหัสประจำตัว")
            if not plate: errors.append("ทะเบียนรถ")
            if not pin or len(pin) != 6: errors.append("PIN 6 หลัก")
            if not p_face: errors.append("รูปเจ้าของรถ")
            if not p_back: errors.append("รูปหลังรถ")
            if not pdpa: errors.append("การยอมรับเงื่อนไข")

            if errors:
                st.error(f"❌ กรุณากรอกข้อมูลให้ครบ: {', '.join(errors)}")
                st.session_state.is_loading = False
            else:
                try:
                    sheet = connect_gsheet()
                    if str(std_id) in sheet.col_values(3):
                        st.error("❌ รหัสนี้เคยลงทะเบียนแล้ว")
                    else:
                        st.write("⏳ กำลังอัปโหลดรูปภาพ...")
                        l_face = upload_to_drive(p_face, f"{std_id}_face.jpg")
                        l_back = upload_to_drive(p_back, f"{std_id}_back.jpg")
                        
                        if l_face and l_back:
                            sheet.append_row([
                                datetime.now().strftime('%d/%m/%Y %H:%M'),
                                f"{prefix}{fname}", str(std_id), f"{level}/{room}",
                                brand, "", plate, "มี", "ปกติ", "มี", l_back, "", "", "100", l_face, str(pin)
                            ])
                            st.success("✅ ลงทะเบียนสำเร็จ!")
                            st.balloons()
                            time.sleep(2)
                        else:
                            st.error("❌ อัปโหลดรูปไม่สำเร็จ เช็คสิทธิ์โฟลเดอร์หรือ GAS URL")
                except Exception as e:
                    st.error(f"Error: {e}")
                st.session_state.is_loading = False
                st.rerun()

    if st.button("🆔 ดูบัตรอนุญาต (Student Portal)", use_container_width=True): go_to_page('portal')
    if st.button("🔐 สำหรับเจ้าหน้าที่", use_container_width=True): go_to_page('teacher')

elif st.session_state['page'] == 'portal':
    # (ระบบ Portal ดึงข้อมูลบัตร - ใช้จากตัวเดิมได้เลย)
    if st.button("🏠 กลับหน้าหลัก"): go_to_page('student')
    # ... โค้ดส่วน Portal ต่อจากนี้ ...
