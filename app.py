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

# --- ส่วนของ PDF Library ---
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader

# ✅ 1. ฟังก์ชันพื้นฐาน
def start_loading():
    st.session_state.is_loading = True

def sanitize_for_gsheet(text):
    if text is None: return ""
    text_str = str(text)
    if text_str.startswith(("=", "+", "-", "@")): return "'" + text_str
    return text_str

# --- 2. ตั้งค่า (Config - ดึงจาก Secrets 100%) ---
# เพื่อให้คุณครูเปลี่ยนโรงเรียนได้ง่ายๆ แค่แก้ที่หน้าเว็บ Secrets
SHEET_NAME = st.secrets["SHEET_NAME"]
DRIVE_FOLDER_ID = st.secrets["DRIVE_FOLDER_ID"]
GAS_APP_URL = st.secrets["GAS_APP_URL"]
UPGRADE_PASSWORD = st.secrets["UPGRADE_PASSWORD"] 
OFFICER_ACCOUNTS = st.secrets["OFFICER_ACCOUNTS"]
SESSION_TIMEOUT_MINUTES = 30 

# --- 3. Setup หน้าเว็บ ---
st.set_page_config(page_title=f"ระบบจราจร {SHEET_NAME}", page_icon="🏍️", layout="wide")

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
    if not file_obj: return None
    try:
        base64_str = base64.b64encode(file_obj.getvalue()).decode('utf-8')
        payload = {
            "folder_id": DRIVE_FOLDER_ID,
            "filename": filename,
            "file": base64_str, # ต้องชื่อ 'file' ให้ตรงกับใน GAS
            "mimeType": "image/jpeg"
        }
        res = requests.post(GAS_APP_URL, json=payload, timeout=20)
        res_json = res.json()
        
        if res_json.get("status") == "success":
            return res_json.get("link")
        else:
            st.error(f"GAS Error: {res_json.get('message')}")
            return None
    except Exception as e:
        st.error(f"❌ ระบบส่งรูปขัดข้อง: {e}")
        return None

def get_img_link(url):
    match = re.search(r'/d/([a-zA-Z0-9_-]+)|id=([a-zA-Z0-9_-]+)', str(url))
    file_id = match.group(1) or match.group(2) if match else None
    return f"https://drive.google.com/thumbnail?id={file_id}&sz=w800" if file_id else url

# --- 🎨 CSS ตกแต่ง ---
st.markdown("""
    <style>
        .atm-card { width: 100%; max-width: 450px; aspect-ratio: 1.586; background: #fff; border-radius: 15px; border: 2px solid #cbd5e1; padding: 20px; position: relative; margin: auto; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1); }
        .atm-school-name { font-size: 16px; font-weight: bold; color: #1e293b; }
        .atm-photo { width: 100px; height: 125px; border-radius: 8px; object-fit: cover; border: 1px solid #cbd5e1; }
        .atm-score-val { font-size: 32px; font-weight: 800; color: #16a34a; }
    </style>
""", unsafe_allow_html=True)

# --- 5. Main UI Logic ---
logo_path = next((f for f in ["logo.png", "logo.jpg", "logo"] if os.path.exists(f)), None)
c_logo, c_title = st.columns([1, 8])
with c_logo: 
    if logo_path: st.image(logo_path, width=90)
with c_title: st.title(f"ระบบจราจร {SHEET_NAME}")

# --- หน้าลงทะเบียน (Student) ---
if st.session_state['page'] == 'student':
    st.info("📝 ลงทะเบียนรถและทำบัตรอนุญาตดิจิทัล")
    with st.form("reg_form"):
        sc1, sc2 = st.columns(2)
        with sc1:
            prefix = st.selectbox("คำนำหน้า", ["นาย", "นางสาว", "เด็กชาย", "เด็กหญิง", "นาง", "ครู"])
            fname = st.text_input("ชื่อ-นามสกุล", key="reg_fname")
        std_id = sc2.text_input("รหัสนักเรียน/รหัสบุคลากร", key="reg_id")
        
        sc3, sc4 = st.columns(2)
        level = sc3.selectbox("ชั้น", ["ม.1", "ม.2", "ม.3", "ม.4", "ม.5", "ม.6", "ครู,บุคลากร", "พ่อค้าแม่ค้า"])
        room = sc4.text_input("ห้อง (เช่น 0-13)", key="reg_room")
        
        pin = st.text_input("ตั้งรหัส PIN 6 หลัก", type="password", max_chars=6, key="reg_pin")
        
        sc5, sc6 = st.columns(2)
        brand = sc5.selectbox("ยี่ห้อรถ", ["Honda", "Yamaha", "Suzuki", "GPX", "Kawasaki", "อื่นๆ"], key="reg_brand")
        color = sc6.text_input("สีรถ", key="reg_color")
        plate = st.text_input("ทะเบียนรถ", placeholder="เช่น 1กข 1234 ร้อยเอ็ด", key="reg_plate")
        
        doc_cols = st.columns(3)
        ls = doc_cols[0].radio("ใบขับขี่", ["✅ มี", "❌ ไม่มี"], horizontal=True)
        ts = doc_cols[1].radio("ภาษี/พรบ", ["✅ ปกติ", "❌ ขาด"], horizontal=True)
        hs = doc_cols[2].radio("หมวกกันน็อค", ["✅ มี", "❌ ไม่มี"], horizontal=True)
        
        st.write("📸 **อัปโหลดภาพ (จำเป็น 3 รูป)**")
        up1, up2, up3 = st.columns(3)
        p_face = up1.file_uploader("1. รูปเจ้าของรถ", type=['jpg','png','jpeg'])
        p_back = up2.file_uploader("2. รูปหลังรถ (ป้ายทะเบียน)", type=['jpg','png','jpeg'])
        p_side = up3.file_uploader("3. รูปข้างรถ (เต็มคัน)", type=['jpg','png','jpeg'])
        
        pdpa = st.checkbox("ยินยอมให้โรงเรียนเก็บข้อมูลตามนโยบาย PDPA")
        
        submit_btn = st.form_submit_button("ส่งข้อมูลลงทะเบียน", type="primary", use_container_width=True, on_click=start_loading, disabled=st.session_state.is_loading)

        if submit_btn:
            errors = []
            if not fname: errors.append("ชื่อ-นามสกุล")
            if not std_id: errors.append("รหัสประจำตัว")
            if not plate: errors.append("ทะเบียนรถ")
            if not pin or len(pin) != 6: errors.append("PIN 6 หลัก")
            if not p_face: errors.append("รูปเจ้าของรถ")
            if not p_back: errors.append("รูปหลังรถ")
            if not p_side: errors.append("รูปข้างรถ")
            if not pdpa: errors.append("การยอมรับเงื่อนไข PDPA")

            if errors:
                st.error(f"❌ ข้อมูลไม่ครบ: {', '.join(errors)}")
                st.session_state.is_loading = False
            else:
                try:
                    sheet = connect_gsheet()
                    
                    # 🚩 ขั้นตอนที่ 1: หาจำนวนแถวทั้งหมดที่มีข้อมูลอยู่ปัจจุบัน
                    all_data = sheet.get_all_values()
                    next_row = len(all_data) + 1 # แถวถัดไปที่ว่างจริงๆ
                    
                    # เช็คซ้ำอีกรอบเพื่อความชัวร์ (รหัสประจำตัว)
                    if str(std_id) in [row[2] for row in all_data if len(row) > 2]:
                        st.error("❌ รหัสนี้ลงทะเบียนแล้ว!")
                        st.session_state.is_loading = False
                    else:
                        progress = st.progress(0)
                        l_face = upload_to_drive(p_face, f"{std_id}_Face.jpg"); progress.progress(30)
                        l_back = upload_to_drive(p_back, f"{std_id}_Back.jpg"); progress.progress(60)
                        l_side = upload_to_drive(p_side, f"{std_id}_Side.jpg"); progress.progress(85)
                        
                        # 🚩 ขั้นตอนที่ 2: ใช้คำสั่ง update แทน append_row เพื่อระบุแถวที่ถูกต้อง
                        new_data = [
                            datetime.now().strftime('%d/%m/%Y %H:%M'),
                            f"{prefix}{fname}", str(std_id), f"{level}/{room}",
                            brand, color, plate, ls, ts, hs, l_back, l_side, "", "100", l_face, str(pin)
                        ]
                        
                        # ระบุช่วงที่จะบันทึก เช่น A5:P5
                        sheet.update(range_name=f"A{next_row}", values=[new_data])
                        
                        progress.progress(100)
                        st.success(f"✅ ลงทะเบียนสำเร็จ! (บันทึกในลำดับที่ {next_row-1})")
                        st.balloons()
                            time.sleep(2)
                            st.session_state.is_loading = False
                            st.rerun()
                        else:
                            # ❌ ถ้ามีรูปใดรูปหนึ่งเป็น None (อัปโหลดไม่เข้า)
                            status_text.empty()
                            progress.empty()
                            st.error("❌ อัปโหลดรูปภาพไม่สำเร็จ! (ข้อมูลจะไม่ถูกบันทึก) กรุณาตรวจสอบสิทธิ์โฟลเดอร์ Google Drive หรือ GAS URL")
                            st.session_state.is_loading = False

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
            if st.form_submit_button("🔓 แสดงบัตร", use_container_width=True, type="primary"):
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
                    <div class="atm-header"><div class="atm-school-name">{SHEET_NAME}</div></div>
                    <div class="atm-body">
                        <img src="{get_img_link(v[14])}" class="atm-photo">
                        <div class="atm-info"><b>{v[1]}</b><br>ID: {v[2]}<br>ทะเบียน: <b>{v[6]}</b></div>
                    </div>
                    <div class="atm-score-box"><div class="atm-score-val" style="color:{score_col};">{score}</div></div>
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
                    user_info = OFFICER_ACCOUNTS[u_pwd]
                    st.session_state.logged_in = True
                    st.session_state.officer_name = user_info["name"]
                    st.session_state.officer_role = user_info["role"]
                    st.session_state.current_user_pwd = u_pwd
                    st.rerun()
                else: st.error("รหัสผ่านไม่ถูกต้อง")
    else:
        st.success(f"👤 ผู้ใช้งาน: {st.session_state.officer_name} ({st.session_state.officer_role})")
        if st.button("🏠 กลับหน้าหลัก"): go_to_page('student')
        if st.button("🚪 ออกจากระบบ"): 
            st.session_state.logged_in = False
            go_to_page('student')
