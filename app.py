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

# ✅ 1. ฟังก์ชันช่วยงานเบื้องหลัง
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
st.set_page_config(page_title="Patwit Moto System", page_icon="🏍️", layout="wide")

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
        # ดึงข้อมูลจาก Secrets
        key_content = st.secrets["textkey"]["json_content"]
        # ล้างช่องว่างที่อาจติดมา
        key_content = key_content.strip() 
        # แปลงเป็น Dictionary
        key_dict = json.loads(key_content, strict=False)
        
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(key_dict, scope)
        client = gspread.authorize(creds)
        return client.open(SHEET_NAME).sheet1
    except Exception as e:
        st.error(f"❌ ปัญหากุญแจ JSON: {e}")
        st.stop()

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

def upload_to_drive(file_obj, filename):
    if hasattr(file_obj, 'getvalue'): file_content = file_obj.getvalue()
    else: file_content = file_obj
    base64_str = base64.b64encode(file_content).decode('utf-8')
    payload = {"folder_id": DRIVE_FOLDER_ID, "filename": filename, "file": base64_str, "mimeType": "image/jpeg"}
    try:
        res = requests.post(GAS_APP_URL, json=payload).json()
        return res.get("link") if res.get("status") == "success" else None
    except: return None

# --- 🎨 CSS สำหรับตกแต่งบัตร ---
st.markdown("""
    <style>
        .atm-card {
            width: 100%; max-width: 450px; aspect-ratio: 1.586;
            background: #ffffff; border-radius: 15px; border: 2px solid #cbd5e1;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
            padding: 20px; position: relative; margin: auto;
        }
        .atm-header { display: flex; align-items: center; justify-content: space-between; border-bottom: 2px solid #e2e8f0; padding-bottom: 10px; margin-bottom: 15px; }
        .atm-logo { height: 50px; width: auto; }
        .atm-school-name { font-size: 16px; font-weight: bold; color: #1e293b; }
        .atm-card-name { font-size: 14px; color: #059669; font-weight: bold; }
        .atm-body { display: flex; gap: 15px; }
        .atm-photo { width: 100px; height: 125px; border-radius: 8px; object-fit: cover; border: 1px solid #cbd5e1; }
        .atm-info { font-size: 14px; line-height: 1.5; flex: 1; color: #334155; }
        .atm-score-box { position: absolute; bottom: 35px; right: 20px; text-align: right; }
        .atm-score-val { font-size: 32px; font-weight: 800; color: #16a34a; line-height: 1; }
    </style>
""", unsafe_allow_html=True)

# --- 5. การแสดงผลหน้าหลัก ---
logo_path = next((f for f in ["logo.png", "logo.jpg", "logo"] if os.path.exists(f)), None)
c_logo, c_title = st.columns([1, 8])
with c_logo: 
    if logo_path: st.image(logo_path, width=90)
    else: st.write("🏍️")
with c_title: st.title(f"ระบบจราจร {SHEET_NAME}")

# --- หน้าลงทะเบียน (Student) ---
if st.session_state['page'] == 'student':
    st.info("📝 ลงทะเบียนรถและทำบัตรอนุญาตดิจิทัล")
    with st.form("reg_form"):
        sc1, sc2 = st.columns(2)
        with sc1:
            prefix = st.selectbox("คำนำหน้า", ["นาย", "นางสาว", "เด็กชาย", "เด็กหญิง", "นาง", "ครู"])
            fname = st.text_input("ชื่อ-นามสกุล")
        std_id = sc2.text_input("รหัสประจำตัว (นักเรียน/ครู/บุคคล)")
        
        sc3, sc4 = st.columns(2)
        level = sc3.selectbox("ชั้น", ["ม.1", "ม.2", "ม.3", "ม.4", "ม.5", "ม.6", "ครู,บุคลากร", "พ่อค้าแม่ค้า"])
        room = sc4.text_input("ห้อง (เช่น 0-13)")
        
        st.write("🔐 **ตั้งค่าความปลอดภัย**")
        pin = st.text_input("ตั้งรหัส PIN 6 หลัก", type="password", max_chars=6)
        
        sc5, sc6 = st.columns(2)
        brand = sc5.selectbox("ยี่ห้อรถ", ["Honda", "Yamaha", "Suzuki", "GPX", "Kawasaki", "อื่นๆ"])
        color = sc6.text_input("สีรถ")
        plate = st.text_input("ทะเบียนรถ (เช่น 1กข 1234 ร้อยเอ็ด)")
        
        doc_cols = st.columns(3)
        ls = doc_cols[0].radio("ใบขับขี่", ["✅ มี", "❌ ไม่มี"], horizontal=True)
        ts = doc_cols[1].radio("ภาษี/พรบ", ["✅ ปกติ", "❌ ขาด"], horizontal=True)
        hs = doc_cols[2].radio("หมวกกันน็อค", ["✅ มี", "❌ ไม่มี"], horizontal=True)
        
        st.write("📸 **อัปโหลดภาพ**")
        up1, up2, up3 = st.columns(3)
        p_face = up1.file_uploader("1. รูปเจ้าของรถ", type=['jpg','png','jpeg'])
        p_back = up2.file_uploader("2. รูปหลังรถ (ป้ายทะเบียน)", type=['jpg','png','jpeg'])
        p_side = up3.file_uploader("3. รูปข้างรถ", type=['jpg','png','jpeg'])
        
        pdpa = st.checkbox("ยินยอมให้เก็บข้อมูลตามนโยบายโรงเรียน")
        
        submit_btn = st.form_submit_button("ส่งข้อมูลลงทะเบียน", type="primary", use_container_width=True, on_click=start_loading, disabled=st.session_state.is_loading)

        if submit_btn:
            if not (fname and std_id and plate and p_face and p_back and pin and pdpa):
                st.error("❌ ข้อมูลไม่ครบถ้วน")
                st.session_state.is_loading = False
            else:
                try:
                    sheet = connect_gsheet()
                    if str(std_id) in sheet.col_values(3):
                        st.error("❌ รหัสนี้ลงทะเบียนแล้ว")
                    else:
                        pb = st.progress(0)
                        l_face = upload_to_drive(p_face, f"{std_id}_Face.jpg"); pb.progress(30)
                        l_back = upload_to_drive(p_back, f"{std_id}_Back.jpg"); pb.progress(60)
                        l_side = upload_to_drive(p_side, f"{std_id}_Side.jpg") if p_side else ""; pb.progress(80)
                        
                        sheet.append_row([
                            datetime.now().strftime('%d/%m/%Y %H:%M'),
                            f"{prefix}{fname}", str(std_id), f"{level}/{room}",
                            brand, color, plate, ls, ts, hs, l_back, l_side, "", "100", l_face, str(pin)
                        ])
                        pb.progress(100)
                        st.success("✅ ลงทะเบียนสำเร็จ!")
                        time.sleep(2)
                    st.session_state.is_loading = False
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")
                    st.session_state.is_loading = False

    if st.button("🆔 ดูบัตรอนุญาต (Student Portal)", use_container_width=True): go_to_page('portal')
    if st.button("🔐 สำหรับเจ้าหน้าที่", use_container_width=True): go_to_page('teacher')

# --- หน้าดูบัตร (Portal) ---
elif st.session_state['page'] == 'portal':
    if st.button("🏠 กลับหน้าหลัก"): go_to_page('student')
    with st.container(border=True):
        st.subheader("ยืนยันตัวตนเพื่อดูบัตร")
        with st.form("portal_login"):
            sid = st.text_input("รหัสนักเรียน/รหัสที่ใช้สมัคร")
            spin = st.text_input("รหัส PIN 6 หลัก", type="password")
            if st.form_submit_button("🔓 แสดงบัตร", use_container_width=True):
                sheet = connect_gsheet(); all_d = sheet.get_all_values()
                df = pd.DataFrame(all_d[1:], columns=all_d[0])
                user = df[(df.iloc[:, 2] == sid) & (df.iloc[:, 15] == spin)]
                if not user.empty: st.session_state.portal_user = user.iloc[0].tolist()
                else: st.error("❌ ข้อมูลไม่ถูกต้อง")
        
        if 'portal_user' in st.session_state:
            v = st.session_state.portal_user
            score = int(v[13]) if str(v[13]).isdigit() else 100
            score_col = "#16a34a" if score >= 80 else ("#ca8a04" if score >= 50 else "#dc2626")
            st.markdown(f"""
                <div class="atm-card">
                    <div class="atm-header">
                        <div class="atm-school-name">{SHEET_NAME}</div>
                        <div class="atm-card-name">Digital Permit</div>
                    </div>
                    <div class="atm-body">
                        <img src="{get_img_link(v[14])}" class="atm-photo">
                        <div class="atm-info">
                            <b>{v[1]}</b><br>ID: {v[2]}<br>ชั้น: {v[3]}<br>ทะเบียน: <b>{v[6]}</b>
                        </div>
                    </div>
                    <div class="atm-score-box">
                        <div style="font-size:10px; color:#64748b;">แต้มวินัย</div>
                        <div class="atm-score-val" style="color:{score_col};">{score}</div>
                    </div>
                </div>
            """, unsafe_allow_html=True)

# --- หน้าเจ้าหน้าที่ (Teacher) ---
elif st.session_state['page'] == 'teacher':
    if not st.session_state.logged_in:
        with st.form("login"):
            st.subheader("🔐 เจ้าหน้าที่เข้าสู่ระบบ")
            u_pwd = st.text_input("รหัสผ่านเจ้าหน้าที่", type="password")
            if st.form_submit_button("เข้าสู่ระบบ"):
                if u_pwd in OFFICER_ACCOUNTS:
                    st.session_state.logged_in = True
                    st.session_state.officer_name = OFFICER_ACCOUNTS[u_pwd]["name"]
                    st.session_state.officer_role = OFFICER_ACCOUNTS[u_pwd]["role"]
                    st.session_state.current_user_pwd = u_pwd
                    st.rerun()
                else: st.error("รหัสผิด")
    else:
        st.write(f"👤 สวัสดี: {st.session_state.officer_name}")
        if st.button("🏠 หน้าหลัก"): go_to_page('student')
        if st.button("📊 สถิติ"): go_to_page('dashboard')
        if st.button("🚪 ออกจากระบบ"): 
            st.session_state.logged_in = False
            go_to_page('student')
