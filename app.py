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
import pytz

# --- ส่วนของ PDF Library ---
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader

# ✅ 1. ตั้งค่าพื้นฐานและฟอนต์
thai_tz = pytz.timezone('Asia/Bangkok')
FONT_FILE = "THSarabunNew.ttf" 
FONT_BOLD = "THSarabunNew.ttf" 

def start_loading():
    st.session_state.is_loading = True

def sanitize_for_gsheet(text):
    if text is None: return ""
    text_str = str(text)
    if text_str.startswith(("=", "+", "-", "@")): return "'" + text_str
    return text_str

# --- 2. ตั้งค่า Config จาก Secrets ---
SHEET_NAME = st.secrets["SHEET_NAME"]
DRIVE_FOLDER_ID = st.secrets["DRIVE_FOLDER_ID"]
GAS_APP_URL = st.secrets["GAS_APP_URL"]
UPGRADE_PASSWORD = st.secrets["UPGRADE_PASSWORD"] 
OFFICER_ACCOUNTS = st.secrets["OFFICER_ACCOUNTS"]

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
if 'df_tra' not in st.session_state: st.session_state['df_tra'] = None
if 'traffic_page' not in st.session_state: st.session_state['traffic_page'] = 'teacher'

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
        payload = {"folder_id": DRIVE_FOLDER_ID, "filename": filename, "file": base64_str, "mimeType": "image/jpeg"}
        res = requests.post(GAS_APP_URL, json=payload, timeout=20)
        res_json = res.json()
        return res_json.get("link") if res_json.get("status") == "success" else None
    except: return None

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

# ✅ ฟังก์ชันสร้าง PDF
def create_pdf_tra(vals, img_url1, img_url2, face_url=None, printed_by="N/A"):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    if os.path.exists(FONT_FILE):
        pdfmetrics.registerFont(TTFont('Thai', FONT_FILE))
        pdfmetrics.registerFont(TTFont('ThaiBold', FONT_BOLD if os.path.exists(FONT_BOLD) else FONT_FILE))
        fn, fb = 'Thai', 'ThaiBold'
    else: fn, fb = 'Helvetica', 'Helvetica-Bold'
    
    c.setFont(fb, 22); c.drawCentredString(width/2, height - 50, "แบบทะเบียนประวัติรถจักรยานยนต์นักเรียน")
    c.setFont(fn, 16); c.drawString(60, height - 115, f"ชื่อ-นามสกุล: {vals[1]}"); c.drawString(300, height - 115, f"ยี่ห้อรถ: {vals[4]}")
    c.drawString(60, height - 135, f"รหัสนักเรียน: {vals[2]} "); c.drawString(300, height - 135, f"ทะเบียน: {vals[6]}")
    score = str(vals[13]) if str(vals[13]).isdigit() else "100"
    c.setFont(fb, 18); c.drawString(60, height - 185, f"คะแนนความประพฤติคงเหลือ: {score} คะแนน")
    
    def draw_img(url, x, y, w, h):
        try:
            res = requests.get(url, timeout=5)
            img = ImageReader(io.BytesIO(res.content))
            c.drawImage(img, x, y, width=w, height=h, preserveAspectRatio=True, mask='auto')
            c.rect(x, y, w, h, stroke=1, fill=0) # 🚩 แก้ไข: fill=0 กันถมดำ
        except: c.rect(x, y, w, h, stroke=1, fill=0)
    
    draw_img(img_url1, 70, height - 415, 180, 180)
    draw_img(img_url2, 300, height - 415, 180, 180)
    if face_url: draw_img(face_url, 450, height - 200, 90, 110)
    c.save(); buffer.seek(0); return buffer

# ✅ ฟังก์ชันหลักของงานจราจร (Traffic Module)
def traffic_module():
    if st.session_state.df_tra is None:
        sheet = connect_gsheet()
        vals = sheet.get_all_values()
        if len(vals) > 1:
            st.session_state.df_tra = pd.DataFrame(vals[1:], columns=[f"C{i}" for i in range(len(vals[0]))])

    st.markdown(f"### 🚦 ระบบงานจราจร | ผู้ใช้: {st.session_state.officer_name}")
    
    if st.session_state.df_tra is not None:
        df = st.session_state.df_tra
        total = len(df)
        has_lic = len(df[df['C7'] == "✅ มี"])
        has_tax = len(df[df['C8'].str.contains("ปกติ|✅", na=False)])
        
        m1, m2, m3 = st.columns(3)
        m1.metric("ลงทะเบียนแล้ว", f"{total} คัน")
        m2.metric("มีใบขับขี่", f"{has_lic} คน", f"{round(has_lic/total*100 if total>0 else 0)}%")
        m3.metric("ภาษีปกติ", f"{has_tax} คัน", f"{round(has_tax/total*100 if total>0 else 0)}%")

    st.write("")
    q = st.text_input("🔍 ค้นหานักเรียน (ชื่อ/รหัส/ทะเบียน)")
    if q:
        df = st.session_state.df_tra
        mask = (df['C1'].str.contains(q, case=False) | df['C2'].str.contains(q) | df['C6'].str.contains(q, case=False))
        res = df[mask]
        
        for i, row in res.iterrows():
            v = row.tolist()
            with st.expander(f"📌 {v[6]} | {v[1]}"):
                c1, c2 = st.columns([1, 2])
                c1.image(get_img_link(v[14]), use_container_width=True)
                with c2:
                    st.write(f"**รหัส:** {v[2]} | **ชั้น:** {v[3]}")
                    st.write(f"**สถานะ:** {v[7]} {v[8]} {v[9]}")
                    if st.session_state.officer_role in ["admin", "super_admin"]:
                        st.download_button("📥 โหลด PDF ประวัติ", create_pdf_tra(v, get_img_link(v[10]), get_img_link(v[11]), get_img_link(v[14]), st.session_state.officer_name), f"{v[2]}.pdf", key=f"pdf_{i}")
                        with st.form(key=f"sc_{i}"):
                            pts = st.number_input("แต้ม", 1, 50, 5)
                            note = st.text_area("เหตุผล")
                            if st.form_submit_button("🔴 ตัดคะแนน"):
                                st.success("บันทึกแล้ว (ฟังก์ชันกำลังพัฒนา)")

# --- 5. Main UI Logic ---
logo_path = next((f for f in ["logo.png", "logo.jpg", "logo"] if os.path.exists(f)), None)
c_logo, c_title = st.columns([1, 8])
with c_logo: 
    if logo_path: st.image(logo_path, width=90)
with c_title: st.title(f"ระบบจราจร {SHEET_NAME}")

# --- หน้าลงทะเบียน (Student) กลับมาแล้วครับ! ---
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
            if not fname or not std_id or not p_face or not p_back or not p_side:
                st.error("❌ ข้อมูลไม่ครบ กรุณากรอกข้อมูลและอัปโหลดรูปภาพให้ครบ 3 รูป")
                st.session_state.is_loading = False
            else:
                try:
                    sheet = connect_gsheet()
                    all_data = sheet.get_all_values()
                    next_row = len(all_data) + 1
                    
                    if str(std_id) in [row[2] for row in all_data if len(row) > 2]:
                        st.error("❌ รหัสนี้ลงทะเบียนแล้ว!")
                        st.session_state.is_loading = False
                    else:
                        progress = st.progress(0)
                        l_face = upload_to_drive(p_face, f"{std_id}_Face.jpg"); progress.progress(30)
                        l_back = upload_to_drive(p_back, f"{std_id}_Back.jpg"); progress.progress(60)
                        l_side = upload_to_drive(p_side, f"{std_id}_Side.jpg"); progress.progress(85)
                        
                        if l_face and l_back and l_side:
                            new_data = [
                                datetime.now().strftime('%d/%m/%Y %H:%M'),
                                f"{prefix}{fname}", str(std_id), f"{level}/{room}",
                                brand, color, plate, ls, ts, hs, l_back, l_side, "", "100", l_face, str(pin)
                            ]
                            sheet.update(range_name=f"A{next_row}", values=[new_data])
                            progress.progress(100)
                            st.success(f"✅ ลงทะเบียนสำเร็จ! (แถวที่ {next_row})")
                            st.balloons()
                            time.sleep(2)
                            st.session_state.is_loading = False
                            st.rerun()
                        else:
                            st.error("❌ อัปโหลดรูปภาพไม่สำเร็จ!")
                            st.session_state.is_loading = False
                except Exception as e:
                    st.error(f"❌ เกิดข้อผิดพลาด: {e}")
                    st.session_state.is_loading = False

    st.write("---")
    if st.button("🆔 ดูบัตรอนุญาต (Student Portal)", use_container_width=True): go_to_page('portal')
    if st.button("🔐 สำหรับเจ้าหน้าที่", use_container_width=True): go_to_page('teacher')

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
                    <div class="atm-header">
                        <div class="atm-school-name">🏫 {SHEET_NAME}</div>
                    </div>
                    <div style="display: flex; align-items: flex-start; gap: 20px; margin-top: 15px;">
                        <img src="{get_img_link(v[14])}" class="atm-photo">
                        <div style="flex: 1; color: #1e293b; line-height: 1.6;">
                            <div style="font-size: 1.2rem; font-weight: bold; border-bottom: 2px solid #eee; margin-bottom: 5px; color: #1e3a8a;">{v[1]}</div>
                            <div style="font-size: 0.9rem;">🆔 รหัส: <b>{v[2]}</b></div>
                            <div style="font-size: 0.9rem;">🏍️ ทะเบียน: <b style="color: #1e40af;">{v[6]}</b></div>
                            <div style="font-size: 0.9rem;">📚 ชั้น: {v[3]}</div>
                        </div>
                    </div>
                    <div style="position: absolute; bottom: 15px; right: 20px; text-align: right;">
                        <div style="font-size: 0.8rem; color: #64748b; font-weight: bold; margin-bottom: -5px;">แต้มวินัยจราจร</div>
                        <div class="atm-score-val" style="color:{score_col}; font-size: 2.8rem;">{score}</div>
                    </div>
                </div>
            """, unsafe_allow_html=True)

elif st.session_state['page'] == 'teacher':
    if not st.session_state.logged_in:
        _, center_col, _ = st.columns([1, 2, 1])
        with center_col:
            st.markdown("### 🔐 เจ้าหน้าที่เข้าสู่ระบบ")
            with st.form("admin_login"):
                user_id = st.text_input("Username")
                user_pass = st.text_input("Password", type="password")
                if st.form_submit_button("Log In", use_container_width=True, type="primary"):
                    if user_id in OFFICER_ACCOUNTS and user_pass == OFFICER_ACCOUNTS[user_id]["password"]:
                        st.session_state.logged_in = True
                        st.session_state.officer_name = OFFICER_ACCOUNTS[user_id]["name"]
                        st.session_state.officer_role = OFFICER_ACCOUNTS[user_id]["role"]
                        st.session_state.current_user_pwd = user_pass
                        st.rerun()
                    else: st.error("❌ ข้อมูลไม่ถูกต้อง")
            if st.button("⬅️ กลับหน้าหลัก"): go_to_page('student')
    else:
        c1, c2 = st.columns([8, 2])
        c1.subheader(f"👋 สวัสดี: {st.session_state.officer_name}")
        if c2.button("🚪 ออกจากระบบ", type="secondary"):
            st.session_state.logged_in = False
            st.rerun()
        st.divider()
        traffic_module()
