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

# ✅ 1. ตั้งค่า Config และฟอนต์
thai_tz = pytz.timezone('Asia/Bangkok')
FONT_FILE = "THSarabunNew.ttf" 
FONT_BOLD = "THSarabunNew.ttf" 

def start_loading():
    st.session_state.is_loading = True

# --- 2. ดึงข้อมูลจาก Secrets ---
SHEET_NAME = st.secrets["SHEET_NAME"]
DRIVE_FOLDER_ID = st.secrets["DRIVE_FOLDER_ID"]
GAS_APP_URL = st.secrets["GAS_APP_URL"]
UPGRADE_PASSWORD = st.secrets["UPGRADE_PASSWORD"] 
OFFICER_ACCOUNTS = st.secrets["OFFICER_ACCOUNTS"]

# --- 3. Setup หน้าเว็บ ---
st.set_page_config(page_title=f"ระบบจราจร {SHEET_NAME}", page_icon="🏍️", layout="wide")

# --- 4. จัดการ Session State (ระบบล้างข้อมูลอัตโนมัติ) ---
if 'page' not in st.session_state: st.session_state['page'] = 'student'
if 'is_loading' not in st.session_state: st.session_state['is_loading'] = False
if 'logged_in' not in st.session_state: st.session_state['logged_in'] = False
if 'officer_name' not in st.session_state: st.session_state['officer_name'] = ""
if 'officer_role' not in st.session_state: st.session_state['officer_role'] = ""
if 'current_user_pwd' not in st.session_state: st.session_state['current_user_pwd'] = ""
if 'df_tra' not in st.session_state: st.session_state['df_tra'] = None
if 'traffic_page' not in st.session_state: st.session_state['traffic_page'] = 'teacher'

def go_to_page(page_name): 
    if 'portal_user' in st.session_state: del st.session_state['portal_user']
    st.session_state['page'] = page_name
    st.rerun()

def connect_gsheet():
    try:
        key_content = st.secrets["textkey"]["json_content"].strip()
        key_dict = json.loads(key_content.replace('\n', '\\n'), strict=False)
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(key_dict, scope)
        return gspread.authorize(creds).open(SHEET_NAME).sheet1
    except Exception as e:
        st.error(f"❌ JSON Error: {e}"); st.stop()

def upload_to_drive(file_obj, filename):
    if not file_obj: return None
    try:
        base64_str = base64.b64encode(file_obj.getvalue()).decode('utf-8')
        payload = {"folder_id": DRIVE_FOLDER_ID, "filename": filename, "file": base64_str, "mimeType": "image/jpeg"}
        res = requests.post(GAS_APP_URL, json=payload, timeout=20)
        return res.json().get("link") if res.json().get("status") == "success" else None
    except: return None

def get_img_link(url):
    match = re.search(r'/d/([a-zA-Z0-9_-]+)|id=([a-zA-Z0-9_-]+)', str(url))
    file_id = match.group(1) or match.group(2) if match else None
    return f"https://drive.google.com/thumbnail?id={file_id}&sz=w800" if file_id else url

# --- 🎨 CSS ตกแต่ง (ห้ามแก้ - ชุดเดิมของคุณครูเลยครับ) ---
st.markdown("""
    <style>
        .atm-card { width: 100%; max-width: 450px; aspect-ratio: 1.586; background: #fff; border-radius: 15px; border: 2px solid #cbd5e1; padding: 20px; position: relative; margin: auto; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1); }
        .atm-school-name { font-size: 16px; font-weight: bold; color: #1e293b; }
        .atm-photo { width: 100px; height: 125px; border-radius: 8px; object-fit: cover; border: 1px solid #cbd5e1; }
        .atm-score-val { font-size: 32px; font-weight: 800; color: #16a34a; }
    </style>
""", unsafe_allow_html=True)

# ✅ 5. ฟังก์ชันสร้าง PDF (ประวัติครบ + ชื่อครู + กันถมดำ)
def create_pdf_tra(vals, img_url1, img_url2, face_url=None, printed_by="N/A"):
    buffer = io.BytesIO(); c = canvas.Canvas(buffer, pagesize=A4); width, height = A4
    if os.path.exists(FONT_FILE):
        pdfmetrics.registerFont(TTFont('Thai', FONT_FILE))
        pdfmetrics.registerFont(TTFont('ThaiBold', FONT_BOLD if os.path.exists(FONT_BOLD) else FONT_FILE))
        fn, fb = 'Thai', 'ThaiBold'
    else: fn, fb = 'Helvetica', 'Helvetica-Bold'
    
    c.setFont(fb, 22); c.drawCentredString(width/2, height - 50, "แบบทะเบียนประวัติรถจักรยานยนต์นักเรียน")
    c.setFont(fn, 18); c.drawCentredString(width/2, height - 75, f"โรงเรียนจันทรุเบกษาอนุสรณ์")
    c.line(50, height - 85, width - 50, height - 85)
    
    c.setFont(fn, 16); c.drawString(60, height - 110, f"ชื่อ-นามสกุล: {vals[1]}"); c.drawString(350, height - 110, f"ยี่ห้อรถ: {vals[4]}")
    c.drawString(60, height - 130, f"รหัสนักเรียน: {vals[2]} "); c.drawString(350, height - 130, f"สีรถ: {vals[5]}")
    c.drawString(60, height - 150, f"ระดับชั้น: {vals[3]}"); c.setFont(fb, 16); c.drawString(350, height - 150, f"ทะเบียน: {vals[6]}")
    
    score = str(vals[13]) if str(vals[13]).isdigit() else "100"
    c.setFont(fb, 18); c.setFillColorRGB(0.7, 0, 0) if int(score) < 80 else c.setFillColorRGB(0, 0.5, 0)
    c.drawString(60, height - 180, f"คะแนนความประพฤติจราจรคงเหลือ: {score} คะแนน"); c.setFillColorRGB(0, 0, 0)
    
    def draw_img(url, x, y, w, h):
        try:
            res = requests.get(url, timeout=5); img = ImageReader(io.BytesIO(res.content))
            c.drawImage(img, x, y, width=w, height=h, preserveAspectRatio=True, mask='auto')
            c.rect(x, y, w, h, stroke=1, fill=0)
        except: c.rect(x, y, w, h, stroke=1, fill=0)

    if face_url: draw_img(face_url, 460, height - 180, 80, 95)
    draw_img(img_url1, 60, height - 380, 230, 180); draw_img(img_url2, 305, height - 380, 230, 180)

    c.setFont(fb, 16); c.drawString(60, height - 410, "📝 ประวัติบันทึกความประพฤติจราจร:")
    c.setFont(fn, 14); raw_history = str(vals[12]).strip()
    history_text = raw_history if raw_history and raw_history.lower() != "nan" else "ไม่พบประวัติ"
    
    text_obj = c.beginText(70, height - 430); text_obj.setLeading(18)
    for line in history_text.split('\n'):
        for w_line in textwrap.wrap(line, width=80): text_obj.textLine(w_line)
    c.drawText(text_obj)

    print_time = datetime.now(thai_tz).strftime('%d/%m/%Y %H:%M')
    c.setFont(fn, 10); c.setFillColorRGB(0.5, 0.5, 0.5)
    c.drawRightString(width - 50, 30, f"ผู้สั่งพิมพ์: {printed_by} | วันที่พิมพ์: {print_time}")
    c.save(); buffer.seek(0); return buffer

# ✅ 6. MODULE: TRAFFIC (ค้นหาพร้อมรูป 3 มุม + เพิ่ม/หักคะแนน)
def traffic_module():
    sheet = connect_gsheet()
    if st.session_state.df_tra is None:
        vals = sheet.get_all_values()
        if len(vals) > 1: st.session_state.df_tra = pd.DataFrame(vals[1:], columns=[f"C{i}" for i in range(len(vals[0]))])

    st.markdown(f"### 🚦 ระบบงานจราจร | ผู้ใช้: {st.session_state.officer_name}")
    
    if st.session_state.df_tra is not None:
        df = st.session_state.df_tra; total = len(df)
        has_lic = len(df[df['C7'] == "✅ มี"]); has_tax = len(df[df['C8'].str.contains("ปกติ|✅", na=False)])
        m1, m2, m3 = st.columns(3)
        m1.metric("ลงทะเบียนแล้ว", f"{total} คัน")
        m2.metric("มีใบขับขี่", f"{has_lic} คน", f"{round(has_lic/total*100 if total>0 else 0)}%")
        m3.metric("ภาษีปกติ", f"{has_tax} คัน", f"{round(has_tax/total*100 if total>0 else 0)}%")

    st.write("")
    c_in, c_bt = st.columns([4, 1])
    q = c_in.text_input("🔍 ค้นหา (ชื่อ/รหัส/ทะเบียน)", key="tra_search_main")
    if c_bt.button("⚡ ค้นหาข้อมูล", use_container_width=True, type="primary") or q:
        df = st.session_state.df_tra
        mask = (df['C1'].str.contains(q, case=False) | df['C2'].str.contains(q) | df['C6'].str.contains(q, case=False))
        res = df[mask]
        if res.empty: st.warning("ไม่พบข้อมูล")
        else:
            for i, row in res.iterrows():
                v = row.tolist(); sc = int(v[13]) if str(v[13]).isdigit() else 100
                with st.expander(f"📌 {v[6]} | {v[1]} (แต้ม: {sc})"):
                    img1, img2, img3 = st.columns(3)
                    img1.image(get_img_link(v[14]), caption="👤 เจ้าของ", use_container_width=True)
                    img2.image(get_img_link(v[10]), caption="📝 ทะเบียน", use_container_width=True)
                    img3.image(get_img_link(v[11]), caption="🏍️ ข้างรถ", use_container_width=True)
                    
                    if st.session_state.officer_role in ["admin", "super_admin"]:
                        st.download_button("📥 โหลด PDF", create_pdf_tra(v, get_img_link(v[10]), get_img_link(v[11]), get_img_link(v[14]), st.session_state.officer_name), f"{v[2]}.pdf", key=f"pdf_{i}")
                        with st.form(key=f"score_form_{i}"):
                            pts = st.number_input("ระบุแต้ม", 1, 50, 5); note = st.text_area("หมายเหตุ")
                            b1, b2 = st.columns(2)
                            if b1.form_submit_button("🔴 หักแต้ม", use_container_width=True) and note:
                                cell = sheet.find(str(v[2]))
                                new_sc = max(0, sc - pts)
                                old_log = str(v[12]) if str(v[12]).lower() != "nan" else ""
                                new_log = f"{old_log}\n[{datetime.now(thai_tz).strftime('%d/%m/%Y %H:%M')}] หัก {pts} โดย {st.session_state.officer_name}: {note}"
                                sheet.update(range_name=f'M{cell.row}:N{cell.row}', values=[[new_log, str(new_sc)]])
                                st.success("หักแต้มสำเร็จ!"); st.session_state.df_tra = None; st.rerun()
                            if b2.form_submit_button("🟢 เพิ่มแต้ม", use_container_width=True) and note:
                                cell = sheet.find(str(v[2]))
                                new_sc = min(100, sc + pts)
                                old_log = str(v[12]) if str(v[12]).lower() != "nan" else ""
                                new_log = f"{old_log}\n[{datetime.now(thai_tz).strftime('%d/%m/%Y %H:%M')}] เพิ่ม {pts} โดย {st.session_state.officer_name}: {note}"
                                sheet.update(range_name=f'M{cell.row}:N{cell.row}', values=[[new_log, str(new_sc)]])
                                st.success("เพิ่มแต้มสำเร็จ!"); st.session_state.df_tra = None; st.rerun()

    # ✅ 7. ระบบเลื่อนชั้นเรียน
    if st.session_state.officer_role == "super_admin":
        st.divider()
        with st.expander("⚙️ เมนูเลื่อนชั้นเรียน (Super Admin Only)"):
            up_pwd = st.text_input("รหัสยืนยันเลื่อนชั้น", type="password", key="prom_pwd")
            if st.button("🚀 ตกลงเลื่อนชั้นทั้งโรงเรียน", type="primary"):
                if up_pwd == UPGRADE_PASSWORD:
                    try:
                        all_d = sheet.get_all_values(); header = all_d[0]; rows = all_d[1:]; new_rows = []
                        for r in rows:
                            if len(r) > 3:
                                ol = r[3]
                                if "ม.1" in ol: r[3] = ol.replace("ม.1", "ม.2")
                                elif "ม.2" in ol: r[3] = ol.replace("ม.2", "ม.3")
                                elif "ม.3" in ol: r[3] = "จบการศึกษา 🎓"
                                elif "ม.4" in ol: r[3] = ol.replace("ม.4", "ม.5")
                                elif "ม.5" in ol: r[3] = ol.replace("ม.5", "ม.6")
                                elif "ม.6" in ol: r[3] = "จบการศึกษา 🎓"
                            new_rows.append(r)
                        sheet.clear(); sheet.update(range_name='A1', values=[header] + new_rows)
                        st.success("สำเร็จ!"); st.session_state.df_tra = None; st.rerun()
                    except Exception as e: st.error(f"Error: {e}")

# --- 8. UI หน้าหลัก (คืนค่าโลโก้ที่หัวเว็บ) ---
logo_path = next((f for f in ["logo.png", "logo.jpg", "logo"] if os.path.exists(f)), None)
cl, ct = st.columns([1, 8])
with cl: 
    if logo_path: st.image(logo_path, width=90)
with ct: st.title(f"ระบบจราจร {SHEET_NAME}")

# --- หน้าลงทะเบียน ---
if st.session_state['page'] == 'student':
    st.info("📝 ลงทะเบียนรถและทำบัตรอนุญาตดิจิทัล")
    with st.form("reg_form"):
        sc1, sc2 = st.columns(2)
        with sc1:
            prefix = st.selectbox("คำนำหน้า", ["นาย", "นางสาว", "เด็กชาย", "เด็กหญิง", "นาง", "ครู"])
            fname = st.text_input("ชื่อ-นามสกุล")
        std_id = sc2.text_input("รหัสประจำตัว")
        sc3, sc4 = st.columns(2)
        level = sc3.selectbox("ชั้น", ["ม.1", "ม.2", "ม.3", "ม.4", "ม.5", "ม.6", "ครู,บุคลากร", "พ่อค้าแม่ค้า"])
        room = sc4.text_input("ห้อง (เช่น 0-13)")
        pin = st.text_input("ตั้ง PIN 6 หลัก", type="password", max_chars=6)
        sc5, sc6 = st.columns(2)
        brand = st.selectbox("ยี่ห้อรถ", ["Honda", "Yamaha", "Suzuki", "GPX", "Kawasaki", "อื่นๆ"])
        color = sc6.text_input("สีรถ"); plate = st.text_input("ทะเบียนรถ")
        doc1, doc2, doc3 = st.columns(3)
        ls = doc1.radio("ใบขับขี่", ["✅ มี", "❌ ไม่มี"], horizontal=True)
        ts = doc2.radio("ภาษี", ["✅ ปกติ", "❌ ขาด"], horizontal=True)
        hs = doc3.radio("หมวก", ["✅ มี", "❌ ไม่มี"], horizontal=True)
        up1, up2, up3 = st.columns(3)
        p1 = up1.file_uploader("1. รูปเจ้าของ", type=['jpg','png','jpeg'])
        p2 = up2.file_uploader("2. รูปหลังรถ", type=['jpg','png','jpeg'])
        p3 = up3.file_uploader("3. รูปข้างรถ", type=['jpg','png','jpeg'])
        pdpa = st.checkbox("ยินยอม PDPA")
        if st.form_submit_button("ส่งข้อมูลลงทะเบียน", type="primary", use_container_width=True):
            if fname and std_id and p1 and p2 and p3:
                try:
                    sheet = connect_gsheet()
                    l1 = upload_to_drive(p1, f"{std_id}_F.jpg"); l2 = upload_to_drive(p2, f"{std_id}_B.jpg"); l3 = upload_to_drive(p3, f"{std_id}_S.jpg")
                    if l1 and l2 and l3:
                        new_d = [datetime.now().strftime('%d/%m/%Y %H:%M'), f"{prefix}{fname}", str(std_id), f"{level}/{room}", brand, color, plate, ls, ts, hs, l2, l3, "", "100", l1, str(pin)]
                        sheet.append_row(new_d); st.success("สำเร็จ!"); st.balloons(); time.sleep(1); st.rerun()
                except Exception as e: st.error(f"Error: {e}")
            else: st.error("❌ กรุณาใส่ข้อมูลและรูปภาพให้ครบ 3 รูป")
    st.divider()
    if st.button("🆔 ดูบัตรอนุญาต", use_container_width=True): go_to_page('portal')
    if st.button("🔐 สำหรับเจ้าหน้าที่", use_container_width=True): go_to_page('teacher')

# --- หน้าดูบัตร ---
elif st.session_state['page'] == 'portal':
    if st.button("🏠 กลับหน้าหลัก"): go_to_page('student')
    with st.form("portal_login"):
        sid_p, spin_p = st.text_input("รหัสประจำตัว"), st.text_input("PIN 6 หลัก", type="password")
        if st.form_submit_button("🔓 แสดงบัตร", use_container_width=True, type="primary"):
            sheet = connect_gsheet(); df = pd.DataFrame(sheet.get_all_values())
            user = df[(df.iloc[:, 2] == sid_p) & (df.iloc[:, 15] == spin_p)]
            if not user.empty: st.session_state.portal_user = user.iloc[0].tolist()
            else: st.error("ข้อมูลไม่ถูกต้อง")
    if 'portal_user' in st.session_state:
        v = st.session_state.portal_user; sc_p = int(v[13]) if str(v[13]).isdigit() else 100
        sc_col = "#16a34a" if sc_p >= 80 else ("#ca8a04" if sc_p >= 50 else "#dc2626")
        st.markdown(f"""
            <div class="atm-card">
                <div class="atm-header"><div class="atm-school-name">🏫 {SHEET_NAME}</div></div>
                <div style="display: flex; gap: 20px; margin-top: 15px;">
                    <img src="{get_img_link(v[14])}" class="atm-photo">
                    <div style="flex: 1; color: #1e293b; line-height: 1.6;">
                        <div style="font-size: 1.2rem; font-weight: bold; color: #1e3a8a;">{v[1]}</div>
                        <div style="font-size: 0.9rem;">🆔 รหัส: <b>{v[2]}</b> | 🏍️ {v[6]}</div>
                        <div style="font-size: 0.9rem;">📚 ชั้น: {v[3]}</div>
                    </div>
                </div>
                <div style="position: absolute; bottom: 15px; right: 20px; text-align: right;">
                    <div style="font-size: 0.8rem; color: #64748b; font-weight: bold; margin-bottom: -5px;">แต้มวินัยจราจร</div>
                    <div class="atm-score-val" style="color:{sc_col}; font-size: 2.8rem;">{sc_p}</div>
                </div>
            </div>
        """, unsafe_allow_html=True)

# --- หน้าเจ้าหน้าที่ ---
elif st.session_state['page'] == 'teacher':
    if not st.session_state.logged_in:
        with st.form("admin_login"):
            u_id, u_p = st.text_input("Username"), st.text_input("Password", type="password")
            if st.form_submit_button("Log In", use_container_width=True, type="primary"):
                if u_id in OFFICER_ACCOUNTS and u_p == OFFICER_ACCOUNTS[u_id]["password"]:
                    st.session_state.logged_in = True; st.session_state.officer_name = OFFICER_ACCOUNTS[u_id]["name"]
                    st.session_state.officer_role = OFFICER_ACCOUNTS[u_id]["role"]; st.session_state.current_user_pwd = u_p; st.rerun()
                else: st.error("ข้อมูลไม่ถูกต้อง")
        if st.button("⬅️ กลับ"): go_to_page('student')
    else:
        c1, c2 = st.columns([8, 2])
        c1.subheader(f"👋 สวัสดี: {st.session_state.officer_name}")
        if c2.button("🚪 ออกจากระบบ", type="secondary"): 
            st.session_state.clear() 
            st.rerun()
        st.divider(); traffic_module()
