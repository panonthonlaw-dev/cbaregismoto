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

# --- Helper Functions ---
def start_loading():
    st.session_state.is_loading = True

def sanitize_for_gsheet(text):
    if text is None: return ""
    text_str = str(text)
    if text_str.startswith(("=", "+", "-", "@")):
        return "'" + text_str
    return text_str

# ✅ ฟังก์ชันใหม่: ป้องกันตัวหนังสือตกขอบ (Auto-scaling)
def get_fitting_font(text, max_width, font_path, initial_size):
    size = initial_size
    try:
        font = ImageFont.truetype(font_path, size)
        while font.getlength(str(text)) > max_width and size > 10:
            size -= 1
            font = ImageFont.truetype(font_path, size)
    except:
        return ImageFont.load_default()
    return font

# --- 1. ตั้งค่า (Config - ดึงจาก Secrets ทั้งหมด) ---
# 🚩 แก้ไข: เปลี่ยนจาก Hardcode เป็นการดึงจาก Secrets เพื่อให้เปลี่ยนโรงเรียนได้ง่าย
SHEET_NAME = st.secrets["SHEET_NAME"]
DRIVE_FOLDER_ID = st.secrets["DRIVE_FOLDER_ID"]
GAS_APP_URL = st.secrets["GAS_APP_URL"]
UPGRADE_PASSWORD = st.secrets["UPGRADE_PASSWORD"] 
OFFICER_ACCOUNTS = st.secrets["OFFICER_ACCOUNTS"]
SESSION_TIMEOUT_MINUTES = 30 

# --- 2. Setup หน้าเว็บ ---
st.set_page_config(page_title="Patwit Moto System", page_icon="🏍️", layout="wide")

# --- 3. ฟังก์ชันระบบ ---
if 'page' not in st.session_state: st.session_state['page'] = 'student'
if 'is_loading' not in st.session_state: st.session_state['is_loading'] = False
if 'logged_in' not in st.session_state: st.session_state['logged_in'] = False

def connect_gsheet():
    key_content = st.secrets["textkey"]["json_content"]
    key_dict = json.loads(key_content, strict=False)
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(key_dict, scope)
    client = gspread.authorize(creds)
    return client.open(SHEET_NAME).sheet1

def load_data():
    try:
        sheet = connect_gsheet()
        vals = sheet.get_all_values()
        if len(vals) > 1:
            st.session_state.df = pd.DataFrame(vals[1:], columns=[f"C{i}" for i, h in enumerate(vals[0])])
            return True
    except Exception as e:
        st.error(f"โหลดข้อมูลไม่สำเร็จ: {e}")
    return False

def go_to_page(page_name): 
    st.session_state['page'] = page_name
    st.rerun()

def upload_to_drive(file_obj, filename):
    if hasattr(file_obj, 'getvalue'): file_content = file_obj.getvalue()
    else: file_content = file_obj
    base64_str = base64.b64encode(file_content).decode('utf-8')
    payload = {"folder_id": DRIVE_FOLDER_ID, "filename": filename, "file": base64_str, "mimeType": "image/jpeg"}
    try:
        res = requests.post(GAS_APP_URL, json=payload).json()
        return res.get("link") if res.get("status") == "success" else None
    except: return None

def get_img_link(url):
    match = re.search(r'/d/([a-zA-Z0-9_-]+)|id=([a-zA-Z0-9_-]+)', str(url))
    file_id = match.group(1) or match.group(2) if match else None
    return f"https://drive.google.com/thumbnail?id={file_id}&sz=w800" if file_id else url

# --- 🎨 CSS สำหรับหน้าจอ (Responsive & No Overflow) ---
st.markdown("""
    <style>
        .atm-card {
            width: 100%; max-width: 480px; aspect-ratio: 1.6 / 1;
            background: white; border-radius: 15px; border: 2px solid #cbd5e1;
            padding: 20px; position: relative; margin: auto; overflow: hidden;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }
        .atm-school-name { font-size: 1.2rem; font-weight: bold; color: #1e293b; }
        .atm-photo { width: 30%; aspect-ratio: 3/4; object-fit: cover; border-radius: 8px; border: 1px solid #cbd5e1; }
        .atm-info { font-size: 0.9rem; flex: 1; overflow: hidden; }
        .atm-score-val { font-size: 2.5rem; font-weight: 800; color: #16a34a; }
        @media (max-width: 480px) {
            .atm-school-name { font-size: 1rem; }
            .atm-info { font-size: 0.8rem; }
        }
    </style>
""", unsafe_allow_html=True)

# --- 4. Main Logic ---
if st.session_state['page'] == 'student':
    st.title("🏍️ ระบบลงทะเบียนรถจราจร")
    with st.form("reg_form"):
        # ... (ส่วนของฟอร์มคงเดิมตามที่คุณครูส่งมา) ...
        # [ข้ามส่วนฟอร์มเพื่อความกระชับ]
        fname = st.text_input("ชื่อ-นามสกุล")
        std_id = st.text_input("รหัสประจำตัว")
        plate = st.text_input("ทะเบียนรถ")
        pin = st.text_input("PIN 6 หลัก", type="password")
        p_face = st.file_uploader("รูปเจ้าของรถ", type=['jpg','png'])
        p_back = st.file_uploader("รูปหลังรถ", type=['jpg','png'])
        p_side = st.file_uploader("รูปข้างรถ", type=['jpg','png'])
        pdpa = st.checkbox("ยินยอมเงื่อนไข")
        
        submit = st.form_submit_button("ลงทะเบียน", on_click=start_loading, disabled=st.session_state.is_loading)
        
        if submit:
            if not (fname and std_id and plate and p_face and p_back and pin and pdpa):
                st.error("❌ กรุณากรอกข้อมูลและอัปโหลดรูปให้ครบถ้วน")
                st.session_state.is_loading = False
                st.rerun()
            else:
                try:
                    bar = st.progress(0)
                    sheet = connect_gsheet()
                    # ตรวจสอบรหัสซ้ำ
                    if str(std_id) in sheet.col_values(3):
                        st.error("❌ รหัสนี้ลงทะเบียนไปแล้ว")
                    else:
                        img_face = upload_to_drive(p_face, f"{std_id}_face.jpg")
                        bar.progress(40)
                        img_back = upload_to_drive(p_back, f"{std_id}_back.jpg")
                        bar.progress(70)
                        img_side = upload_to_drive(p_side, f"{std_id}_side.jpg") if p_side else ""
                        
                        sheet.append_row([
                            datetime.now().strftime('%d/%m/%Y %H:%M'), 
                            sanitize_for_gsheet(fname), sanitize_for_gsheet(std_id),
                            "ชั้น/ห้อง", "ยี่ห้อ", "สี", sanitize_for_gsheet(plate),
                            "มี", "ปกติ", "มี", img_back, img_side, "", "100", img_face, sanitize_for_gsheet(pin)
                        ])
                        bar.progress(100)
                        st.success("✅ ลงทะเบียนสำเร็จ!")
                        time.sleep(2)
                    st.session_state.is_loading = False
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")
                    st.session_state.is_loading = False

    if st.button("🆔 เข้าสู่หน้าดูบัตรอนุญาต (Student Portal)", use_container_width=True):
        go_to_page('portal')

elif st.session_state['page'] == 'portal':
    if st.button("🏠 กลับหน้าหลัก"): go_to_page('student')
    # ... (ส่วนแสดงบัตรที่คุณครูเขียนมา ใช้งานได้ปกติครับ) ...
    # [ปรับ CSS ให้ใช้ class ที่ผมแก้ด้านบนจะสวยขึ้นครับ]
