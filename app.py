import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
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

# ✅ 1. ตั้งค่าพื้นฐาน
thai_tz = pytz.timezone('Asia/Bangkok')
FONT_FILE = "THSarabunNew.ttf" 
FONT_BOLD = "THSarabunNew.ttf" 

# --- 2. ดึงข้อมูลจาก Secrets ---
SHEET_NAME = st.secrets["SHEET_NAME"]
DRIVE_FOLDER_ID = st.secrets["DRIVE_FOLDER_ID"]
GAS_APP_URL = st.secrets["GAS_APP_URL"]
UPGRADE_PASSWORD = st.secrets["UPGRADE_PASSWORD"] 
OFFICER_ACCOUNTS = st.secrets["OFFICER_ACCOUNTS"]

# --- 3. Setup หน้าเว็บ ---
st.set_page_config(page_title=f"ระบบจราจร {SHEET_NAME}", page_icon="🏍️", layout="wide")

# --- 4. จัดการ Session State ---
if 'page' not in st.session_state: st.session_state['page'] = 'student'
if 'logged_in' not in st.session_state: st.session_state['logged_in'] = False
if 'officer_name' not in st.session_state: st.session_state['officer_name'] = ""
if 'officer_role' not in st.session_state: st.session_state['officer_role'] = ""
if 'df_tra' not in st.session_state: st.session_state['df_tra'] = None
if 'traffic_page' not in st.session_state: st.session_state['traffic_page'] = 'main'
if 'edit_data' not in st.session_state: st.session_state['edit_data'] = None

def go_to_page(page_name): 
    if 'portal_user' in st.session_state: del st.session_state['portal_user']
    st.session_state['page'] = page_name
    st.rerun()

# 🛠️ ฟังก์ชันเชื่อมต่อ Sheets (ล้าง JSON Error)
def connect_gsheet():
    try:
        raw_json = st.secrets["textkey"]["json_content"].strip()
        clean_json = re.sub(r'^[\'"]|[\'"]$', '', raw_json)
        key_dict = json.loads(clean_json, strict=False)
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

# 🚩 จัดการโลโก้โรงเรียน
def get_base64_logo():
    logo_file = next((f for f in os.listdir('.') if f.lower().startswith('logo')), None)
    if logo_file:
        with open(logo_file, "rb") as f:
            return f"data:image/png;base64,{base64.b64encode(f.read()).decode()}", logo_file
    return None, None

logo_base64, logo_local_path = get_base64_logo()

# --- 🎨 CSS ตกแต่ง (ห้ามแก้ - เดิมๆ ของคุณครูเลยครับ) ---
st.markdown("""
    <style>
        .atm-card { width: 100%; max-width: 450px; aspect-ratio: 1.586; background: #fff; border-radius: 15px; border: 2px solid #cbd5e1; padding: 20px; position: relative; margin: auto; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1); }
        .atm-school-name { font-size: 16px; font-weight: bold; color: #1e293b; }
        .atm-photo { width: 100px; height: 125px; border-radius: 8px; object-fit: cover; border: 1px solid #cbd5e1; }
        .atm-score-val { font-size: 32px; font-weight: 800; color: #16a34a; }
    </style>
""", unsafe_allow_html=True)

# ✅ 5. ฟังก์ชันสร้าง PDF (กันถมดำ + ประวัติครบ + ชื่อผู้ปริ้น)
def create_pdf_tra(vals, img_url1, img_url2, face_url=None, printed_by="N/A"):
    buffer = io.BytesIO(); c = canvas.Canvas(buffer, pagesize=A4); width, height = A4
    if os.path.exists(FONT_FILE):
        pdfmetrics.registerFont(TTFont('Thai', FONT_FILE))
        pdfmetrics.registerFont(TTFont('ThaiBold', FONT_BOLD if os.path.exists(FONT_BOLD) else FONT_FILE))
        fn, fb = 'Thai', 'ThaiBold'
    else: fn, fb = 'Helvetica', 'Helvetica-Bold'
    
    c.setFont(fb, 22); c.drawCentredString(width/2, height - 50, f"ทะเบียนประวัติรถ {SHEET_NAME}")
    c.line(50, height - 85, width - 50, height - 85)
    c.setFont(fn, 16); c.drawString(60, height - 115, f"ชื่อ: {vals[1]}"); c.drawString(350, height - 115, f"ยี่ห้อ: {vals[4]}")
    c.drawString(60, height - 135, f"ID: {vals[2]}"); c.drawString(350, height - 135, f"ทะเบียน: {vals[6]}")
    score = str(vals[13]) if str(vals[13]).isdigit() else "100"
    c.setFont(fb, 18); c.drawString(60, height - 185, f"คะแนนคงเหลือ: {score} คะแนน")
    
    def draw_img(url, x, y, w, h):
        try:
            res = requests.get(url, timeout=5); img = ImageReader(io.BytesIO(res.content))
            c.drawImage(img, x, y, width=w, height=h, preserveAspectRatio=True, mask='auto')
            c.rect(x, y, w, h, stroke=1, fill=0) # fill=0 แก้ไขถมดำ
        except: c.rect(x, y, w, h, stroke=1, fill=0)

    if face_url: draw_img(face_url, 460, height - 200, 80, 100)
    draw_img(img_url1, 60, height - 415, 230, 180); draw_img(img_url2, 305, height - 415, 230, 180)
    
    c.setFont(fb, 14); c.drawString(60, 350, "📝 ประวัติบันทึกคะแนน:")
    h_text = str(vals[12]) if str(vals[12]).lower() != "nan" else "ไม่พบประวัติ"
    to = c.beginText(70, 335); to.setLeading(14)
    for line in h_text.split('\n'):
        for wl in textwrap.wrap(line, width=90): to.textLine(wl)
    c.drawText(to)
    
    c.setFont(fn, 10); c.drawRightString(width-50, 30, f"ผู้สั่งพิมพ์: {printed_by} | {datetime.now(thai_tz).strftime('%d/%m/%Y %H:%M')}")
    c.save(); buffer.seek(0); return buffer

# ✅ 6. MODULE: TRAFFIC (สรุปผล + ค้นหา + แก้ไข + เพิ่ม/หักแต้ม + เลื่อนชั้น)
def traffic_module():
    sheet = connect_gsheet()
    if st.session_state.df_tra is None:
        vals = sheet.get_all_values()
        if len(vals) > 1: st.session_state.df_tra = pd.DataFrame(vals[1:], columns=[f"C{i}" for i in range(len(vals[0]))])

    if st.session_state.traffic_page == 'main':
        st.markdown(f"### 🚦 ระบบงานจราจร | ผู้ใช้: {st.session_state.officer_name}")
        
        # --- 🚩 จุดสำคัญ: ระบบสรุปผล (Dashboard) ---
        if st.session_state.df_tra is not None:
            df = st.session_state.df_tra
            total = len(df)
            has_lic = len(df[df['C7'] == "✅ มี"])
            has_tax = len(df[df['C8'].str.contains("ปกติ|✅", na=False)])
            
            # Metrics
            m1, m2, m3 = st.columns(3)
            m1.metric("ลงทะเบียนทั้งหมด", f"{total} คัน")
            m2.metric("มีใบขับขี่", f"{has_lic} คน", f"{round(has_lic/total*100 if total>0 else 0)}%")
            m3.metric("ภาษีปกติ", f"{has_tax} คัน", f"{round(has_tax/total*100 if total>0 else 0)}%")
            
            # กราฟสรุปผลแยกตามชั้น
            st.write("📊 **สรุปจำนวนรถแยกตามระดับชั้น**")
            df['Level'] = df['C3'].apply(lambda x: x.split('/')[0] if '/' in x else x)
            count_df = df['Level'].value_counts().reset_index()
            fig = px.bar(count_df, x='Level', y='count', color='Level', text_auto=True)
            st.plotly_chart(fig, use_container_width=True)

        st.divider()
        
        # ค้นหา
        c_in, c_bt = st.columns([4, 1])
        q = c_in.text_input("🔍 ค้นหา (ชื่อ/รหัส/ทะเบียน)", key="tra_search_main")
        if c_bt.button("⚡ ค้นหา", use_container_width=True, type="primary") or q:
            df = st.session_state.df_tra
            mask = (df['C1'].str.contains(q, case=False) | df['C2'].str.contains(q) | df['C6'].str.contains(q, case=False))
            res = df[mask]
            if res.empty: st.warning("ไม่พบข้อมูล")
            else:
                for i, row in res.iterrows():
                    v = row.tolist(); sc = int(v[13]) if str(v[13]).isdigit() else 100
                    with st.expander(f"📌 {v[6]} | {v[1]} (แต้ม: {sc})"):
                        i1, i2, i3 = st.columns(3)
                        i1.image(get_img_link(v[14]), caption="👤 เจ้าของ", use_container_width=True)
                        i2.image(get_img_link(v[10]), caption="📝 ทะเบียน", use_container_width=True)
                        i3.image(get_img_link(v[11]), caption="🏍️ ข้างรถ", use_container_width=True)
                        
                        if st.session_state.officer_role in ["admin", "super_admin"]:
                            c_pdf, c_edit = st.columns(2)
                            c_pdf.download_button("📥 โหลด PDF", create_pdf_tra(v, get_img_link(v[10]), get_img_link(v[11]), get_img_link(v[14]), st.session_state.officer_name), f"{v[2]}.pdf", key=f"pdf_{i}")
                            if st.session_state.officer_role == "super_admin":
                                if c_edit.button("✏️ แก้ไขข้อมูล", key=f"ed_{i}", use_container_width=True):
                                    st.session_state.edit_data = v; st.session_state.traffic_page = 'edit'; st.rerun()

                            with st.form(key=f"sc_form_{i}"):
                                pts = st.number_input("ระบุแต้ม", 1, 50, 5); note = st.text_area("เหตุผล")
                                b1, b2 = st.columns(2)
                                if b1.form_submit_button("🔴 หักแต้ม", use_container_width=True) and note:
                                    cell = sheet.find(str(v[2])); new_sc = max(0, sc - pts)
                                    old_log = str(v[12]) if str(v[12]).lower() != "nan" else ""
                                    new_log = f"{old_log}\n[{datetime.now(thai_tz).strftime('%d/%m/%Y %H:%M')}] หัก {pts} โดย {st.session_state.officer_name}: {note}"
                                    sheet.update(range_name=f'M{cell.row}:N{cell.row}', values=[[new_log, str(new_sc)]])
                                    st.success("บันทึกแล้ว!"); st.session_state.df_tra = None; st.rerun()
                                if b2.form_submit_button("🟢 เพิ่มแต้ม", use_container_width=True) and note:
                                    cell = sheet.find(str(v[2])); new_sc = min(100, sc + pts)
                                    old_log = str(v[12]) if str(v[12]).lower() != "nan" else ""
                                    new_log = f"{old_log}\n[{datetime.now(thai_tz).strftime('%d/%m/%Y %H:%M')}] เพิ่ม {pts} โดย {st.session_state.officer_name}: {note}"
                                    sheet.update(range_name=f'M{cell.row}:N{cell.row}', values=[[new_log, str(new_sc)]])
                                    st.success("บันทึกแล้ว!"); st.session_state.df_tra = None; st.rerun()

        if st.session_state.officer_role == "super_admin":
            st.divider()
            with st.expander("⚙️ เมนูเลื่อนชั้นเรียน (Super Admin)"):
                up_p = st.text_input("รหัสยืนยัน", type="password", key="prom_pwd_final")
                if st.button("🚀 ตกลงเลื่อนชั้นทั้งโรงเรียน", type="primary"):
                    if up_p == UPGRADE_PASSWORD:
                        try:
                            all_d = sheet.get_all_values(); h = all_d[0]; rows = all_d[1:]; new_rows = []
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
                            sheet.clear(); sheet.update(range_name='A1', values=[h] + new_rows)
                            st.success("สำเร็จ!"); st.session_state.df_tra = None; st.rerun()
                        except Exception as e: st.error(f"Error: {e}")

    elif st.session_state.traffic_page == 'edit':
        v = st.session_state.edit_data
        st.subheader(f"✏️ แก้ไขข้อมูล: {v[1]}")
        with st.form("edit_student"):
            nm = st.text_input("ชื่อ-นามสกุล", v[1]); cl = st.text_input("ชั้น", v[3]); pl = st.text_input("ทะเบียน", v[6])
            u1 = st.file_uploader("เปลี่ยนรูปเจ้าของ"); u2 = st.file_uploader("เปลี่ยนรูปหลังรถ"); u3 = st.file_uploader("เปลี่ยนรูปข้างรถ")
            if st.form_submit_button("💾 บันทึกการแก้ไข", type="primary"):
                cell = sheet.find(str(v[2])); l1, l2, l3 = v[14], v[10], v[11]
                if u1: l1 = upload_to_drive(u1, f"{v[2]}_F_e.jpg")
                if u2: l2 = upload_to_drive(u2, f"{v[2]}_B_e.jpg")
                if u3: l3 = upload_to_drive(u3, f"{v[2]}_S_e.jpg")
                sheet.update(range_name=f'B{cell.row}:D{cell.row}', values=[[nm, v[2], cl]])
                sheet.update(range_name=f'G{cell.row}:G{cell.row}', values=[[pl]])
                sheet.update(range_name=f'K{cell.row}:L{cell.row}', values=[[l2, l3]])
                sheet.update_cell(cell.row, 15, l1)
                st.success("แก้ไขแล้ว!"); st.session_state.df_tra = None; st.session_state.traffic_page = 'main'; st.rerun()
        if st.button("⬅️ ยกเลิก"): st.session_state.traffic_page = 'main'; st.rerun()

# --- 7. Main UI (คืนค่าโลโก้ที่หัวเว็บ) ---
cl, ct = st.columns([1, 8])
with cl: 
    if logo_local_path: st.image(logo_local_path, width=90)
with ct: st.title(f"ระบบจราจร {SHEET_NAME}")

# --- หน้าลงทะเบียน (Student) ---
if st.session_state['page'] == 'student':
    st.info("📝 ลงทะเบียนรถและทำบัตรอนุญาตดิจิทัล")
    with st.form("reg_form"):
        sc1, sc2 = st.columns(2)
        with sc1:
            pre = st.selectbox("คำนำหน้า", ["นาย", "นางสาว", "เด็กชาย", "เด็กหญิง", "นาง", "ครู"])
            fname = st.text_input("ชื่อ-นามสกุล")
        sid = sc2.text_input("รหัสประจำตัว")
        sc3, sc4 = st.columns(2)
        lv = sc3.selectbox("ชั้น", ["ม.1", "ม.2", "ม.3", "ม.4", "ม.5", "ม.6", "ครู,บุคลากร", "พ่อค้าแม่ค้า"])
        rm = sc4.text_input("ห้อง (เช่น 0-13)"); pin = st.text_input("ตั้ง PIN 6 หลัก", type="password", max_chars=6)
        sc5, sc6 = st.columns(2)
        brand = st.selectbox("ยี่ห้อรถ", ["Honda", "Yamaha", "Suzuki", "GPX", "Kawasaki", "อื่นๆ"])
        color = st.text_input("สีรถ"); plate = st.text_input("ทะเบียนรถ")
        doc1, doc2, doc3 = st.columns(3)
        ls = doc1.radio("ใบขับขี่", ["✅ มี", "❌ ไม่มี"], horizontal=True); ts = doc2.radio("ภาษี", ["✅ ปกติ", "❌ ขาด"], horizontal=True); hs = doc3.radio("หมวก", ["✅ มี", "❌ ไม่มี"], horizontal=True)
        up1, up2, up3 = st.columns(3)
        p1 = up1.file_uploader("1. รูปหน้า", type=['jpg','png','jpeg']); p2 = up2.file_uploader("2. รูปทะเบียน", type=['jpg','png','jpeg']); p3 = up3.file_uploader("3. รูปข้างรถ", type=['jpg','png','jpeg'])
        if st.form_submit_button("ส่งข้อมูลลงทะเบียน", type="primary", use_container_width=True):
            if fname and sid and p1 and p2 and p3:
                try:
                    sheet = connect_gsheet()
                    l1 = upload_to_drive(p1, f"{sid}_F.jpg"); l2 = upload_to_drive(p2, f"{sid}_B.jpg"); l3 = upload_to_drive(p3, f"{sid}_S.jpg")
                    if l1 and l2 and l3:
                        new_d = [datetime.now().strftime('%d/%m/%Y %H:%M'), f"{pre}{fname}", str(sid), f"{lv}/{rm}", brand, color, plate, ls, ts, hs, l2, l3, "", "100", l1, str(pin)]
                        sheet.append_row(new_d); st.success("ลงทะเบียนสำเร็จ!"); st.balloons(); time.sleep(1); st.rerun()
                except Exception as e: st.error(f"Error: {e}")
            else: st.error("❌ ข้อมูลไม่ครบ")
    st.divider()
    if st.button("🆔 ดูบัตรอนุญาต", use_container_width=True): go_to_page('portal')
    if st.button("🔐 สำหรับเจ้าหน้าที่", use_container_width=True): go_to_page('teacher')

# --- หน้าดูบัตร (Portal) ---
elif st.session_state['page'] == 'portal':
    if st.button("🏠 กลับหน้าหลัก"): go_to_page('student')
    with st.form("portal_login"):
        sid_p, spin_p = st.text_input("รหัส"), st.text_input("PIN", type="password")
        if st.form_submit_button("🔓 แสดงบัตร", use_container_width=True, type="primary"):
            sheet = connect_gsheet(); df = pd.DataFrame(sheet.get_all_values())
            user = df[(df.iloc[:, 2] == sid_p) & (df.iloc[:, 15] == spin_p)]
            if not user.empty: st.session_state.portal_user = user.iloc[0].tolist()
            else: st.error("ข้อมูลไม่ถูกต้อง")
    if 'portal_user' in st.session_state:
        v = st.session_state.portal_user; sc_p = int(v[13]) if str(v[13]).isdigit() else 100
        sc_col = "#16a34a" if sc_p >= 80 else ("#ca8a04" if sc_p >= 50 else "#dc2626")
        l_img = f'<img src="{logo_base64}" style="width:45px; vertical-align:middle; margin-right:10px;">' if logo_base64 else '🏫 '
        st.markdown(f"""
            <div class="atm-card">
                <div class="atm-header"><div class="atm-school-name">{l_img}{SHEET_NAME}</div></div>
                <div style="display: flex; gap: 20px; margin-top: 15px;">
                    <img src="{get_img_link(v[14])}" class="atm-photo">
                    <div style="flex: 1; color: #1e293b; line-height: 1.6;">
                        <div style="font-size: 1.2rem; font-weight: bold; border-bottom: 2px solid #eee; margin-bottom: 5px; color: #1e3a8a;">{v[1]}</div>
                        <div style="font-size: 0.9rem;">🆔 {v[2]} | 🏍️ {v[6]}</div>
                        <div style="font-size: 0.9rem;">📚 ชั้น: {v[3]}</div>
                    </div>
                </div>
                <div style="position: absolute; bottom: 15px; right: 20px; text-align: right;">
                    <div style="font-size: 0.8rem; color: #64748b; font-weight: bold; margin-bottom: -5px;">แต้มวินัยจราจร</div>
                    <div class="atm-score-val" style="color:{sc_col}; font-size: 2.8rem;">{sc_p}</div>
                </div>
            </div>
        """, unsafe_allow_html=True)

# --- หน้าเจ้าหน้าที่ (Teacher) ---
elif st.session_state['page'] == 'teacher':
    if not st.session_state.logged_in:
        with st.form("admin_login"):
            u_id, u_p = st.text_input("Username"), st.text_input("Password", type="password")
            if st.form_submit_button("Log In", use_container_width=True, type="primary"):
                if u_id in OFFICER_ACCOUNTS and u_p == OFFICER_ACCOUNTS[u_id]["password"]:
                    st.session_state.logged_in = True; st.session_state.officer_name = OFFICER_ACCOUNTS[u_id]["name"]
                    st.session_state.officer_role = OFFICER_ACCOUNTS[u_id]["role"]; st.rerun()
                else: st.error("รหัสผิด")
        if st.button("⬅️ กลับ"): go_to_page('student')
    else:
        c1, c2 = st.columns([8, 2])
        c1.subheader(f"👋 สวัสดี: {st.session_state.officer_name}")
        if c2.button("🚪 ออกจากระบบ", type="secondary"): st.session_state.clear(); st.rerun()
        st.divider(); traffic_module()
