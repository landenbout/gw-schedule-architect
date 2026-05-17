import re
import os
import requests
import pandas as pd
import streamlit as st
import matplotlib.pyplot as plt
from bs4 import BeautifulSoup
from datetime import datetime

# --- CONFIGURATION & PAGE INITIALIZATION ---
st.set_page_config(
    page_title="GWU Color-Coded Schedule Architect",
    page_icon="📅",
    layout="wide"
)

# Initialize Session State attributes if they don't exist
if "all_dept_data" not in st.session_state:
    st.session_state.all_dept_data = {}
if "active_courses" not in st.session_state:
    st.session_state.active_courses = set()
if "master_color_map" not in st.session_state:
    st.session_state.master_color_map = {}
if "selected_sections" not in st.session_state:
    st.session_state.selected_sections = {}

# --- CORE FUNCTIONS ---

def fetch_gwu_data(subj_id, term_id):
    subj_id = subj_id.upper().strip()
    term_id = term_id.strip()
    cache_key = f"{subj_id}_{term_id}"
    
    if cache_key in st.session_state.all_dept_data:
        return True
        
    url = f"https://my.gwu.edu/mod/pws/print.cfm?termId={term_id}&subjId={subj_id}"
    headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'}
    
    try:
        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            return False
    except Exception:
        return False

    soup = BeautifulSoup(response.text, 'html.parser')
    course_listings = []
    rows = soup.find_all('tr')

    for row in rows:
        cells = row.find_all('td')
        if len(cells) < 8:
            continue
            
        status_raw = cells[0].text.strip().upper() 
        crn = cells[1].text.strip()
        subject_box = cells[2].text.strip()  
        section_raw = cells[3].text.strip().upper()
        course_title_raw = cells[4].text.strip() 
        
        if crn.isdigit() and len(crn) == 5:
            subject_clean = " ".join(subject_box.split()).upper()
            title_clean = " ".join(course_title_raw.split())
            
            days, time_str = "", ""
            for cell in cells:
                cell_text = cell.text.strip()
                if "-" in cell_text and ("AM" in cell_text or "PM" in cell_text):
                    lines = [line.strip() for line in cell.text.split('\n') if line.strip()]
                    if len(lines) >= 2:
                        days, time_str = lines[0], lines[1]
                    elif len(lines) == 1:
                        match = re.search(r'([MTWRF]+)\s*(\d+:\d+.*)', lines[0])
                        if match:
                            days, time_str = match.group(1), match.group(2)
                    break
            
            if time_str and days:
                course_listings.append({
                    "Status": status_raw,
                    "CourseNum": subject_clean,   
                    "CourseTitle": title_clean,   
                    "CRN": crn,
                    "Section": section_raw,
                    "Days": days,
                    "Time": time_str
                })
                
    if course_listings:
        st.session_state.all_dept_data[cache_key] = pd.DataFrame(course_listings)
        return True
    return False

def parse_time(time_str):
    time_str = time_str.strip().replace(" ", "")
    try:
        t = datetime.strptime(time_str, "%I:%M%p")
        return t.hour + t.minute / 60.0
    except ValueError:
        return None

def get_section_num(sec_str):
    digits = re.findall(r'\d+', str(sec_str))
    return int("".join(digits)) if digits else 0

def get_courses_requiring_discussion_global():
    req_set = set()
    for cache_key, df in st.session_state.all_dept_data.items():
        if df.empty:
            continue
        disc_rows = df[df['Section'].apply(lambda s: get_section_num(s) >= 30)]
        for cnum in disc_rows['CourseNum'].unique():
            req_set.add(cnum)
    return req_set

def get_combined_active_dataframe():
    if not st.session_state.active_courses:
        return pd.DataFrame()
        
    frames = []
    sem_mapping = {"Spring": "01", "Summer": "02", "Fall": "03"}
    
    for tracking_key in st.session_state.active_courses:
        match = re.match(r"^(.+?)(?:\s+Sec\s+([A-Z0-9]+))?\s*\((.+?)\s+(.+?)\)$", tracking_key)
        if match:
            course = match.group(1)
            target_sec = match.group(2)
            year = match.group(3)
            sem_name = match.group(4)
            
            sem_code = sem_mapping.get(sem_name, "03")
            term = f"{year}{sem_code}"
            dept = course.split()[0]
            cache_key = f"{dept}_{term}"
            
            if cache_key in st.session_state.all_dept_data:
                df_dept = st.session_state.all_dept_data[cache_key]
                df_match = df_dept[df_dept['CourseNum'].str.contains(course, na=False)].copy()
                
                if target_sec:
                    df_match = df_match[df_match['Section'] == target_sec].copy()
                    
                frames.append(df_match)
                
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)

def rebuild_master_color_map(df_all):
    if df_all.empty:
        st.session_state.master_color_map.clear()
        return
    df_all['UniqueKey'] = df_all['CourseNum'] + " - Sec " + df_all['Section']
    all_possible_keys = sorted(df_all['UniqueKey'].unique())
    
    cmap = plt.get_cmap('tab20')
    for i, key in enumerate(all_possible_keys):
        st.session_state.master_color_map[key] = cmap(i % 20)

def rgba_to_hex(rgba_tuple):
    """Converts a matplotlib RGBA tuple to a web-friendly CSS hex string."""
    return f"#{int(rgba_tuple[0]*255):02x}{int(rgba_tuple[1]*255):02x}{int(rgba_tuple[2]*255):02x}"

# --- UI CONTROL LAYOUT ---
st.title("📅 GWU Schedule Visualizer")

# Row 1 Panel Controls
col1, col1_sec, col2, col3, col4, col5 = st.columns([1.5, 1.0, 1.0, 1.0, 1.2, 1.5])

with col1:
    course_input = st.text_input("Course ID:", value="PSC 1001", help="e.g. PSC 1001").upper().strip()

with col1_sec:
    section_input = st.text_input("Section (Optional):", value="", help="e.g. 10 or MV").upper().strip()

with col2:
    sem_name = st.selectbox("Semester:", ["Spring", "Summer", "Fall"], index=2)

with col3:
    year_input = st.text_input("Year:", value="2026")

with col4:
    view_mode = st.selectbox("View Mode:", ["All Sections", "Lectures Only", "Discussions Only"])

with col5:
    st.write(" ") 
    add_clicked = st.button("➕ Add Course to Matrix", use_container_width=True)

# Add Course Trigger Logic
if add_clicked and course_input:
    if not year_input.isdigit() or len(year_input) != 4:
        st.error("Year must be a 4-digit number (e.g. '2026')")
    else:
        dept_match = re.match(r'^([A-Z]+)', course_input)
        if not dept_match:
            st.error("Please enter a valid format (e.g. 'PSC 1001')")
        else:
            req_dept = dept_match.group(1)
            sem_mapping = {"Spring": "01", "Summer": "02", "Fall": "03"}
            term_input = f"{year_input}{sem_mapping.get(sem_name, '03')}"
            
            with st.spinner(f"Pulling {req_dept} data..."):
                if fetch_gwu_data(req_dept, term_input):
                    if section_input:
                        tracking_key = f"{course_input} Sec {section_input} ({year_input} {sem_name})"
                    else:
                        tracking_key = f"{course_input} ({year_input} {sem_name})"
                        
                    st.session_state.active_courses.add(tracking_key)
                    st.success(f"Added {course_input} {f'Sec {section_input}' if section_input else ''}!")
                else:
                    st.error(f"Could not pull entries for '{req_dept}'")

# Row 2 Filters and Settings Bar
col_f1, col_f2, col_f3, col_f4 = st.columns(4)
with col_f1:
    exclude_mv = st.checkbox("Exclude Mount Vernon Sections", value=False)
with col_f2:
    exclude_wl = st.checkbox("Exclude Waitlisted Sections", value=True)
with col_f3:
    font_size = st.slider("Calendar Label Font Size:", min_value=5.0, max_value=12.0, value=8.5, step=0.5)

# Badges and Management System
if st.session_state.active_courses:
    st.write("**Tracking Badges:**")
    badge_cols = st.columns(len(st.session_state.active_courses) + 1)
    for idx, key in enumerate(sorted(list(st.session_state.active_courses))):
        with badge_cols[idx]:
            if st.button(f"❌ {key}", key=f"del_{key}"):
                st.session_state.active_courses.remove(key)
                st.rerun()

# --- DATA GENERATION & SELECTION MANAGEMENT ---
df_master = get_combined_active_dataframe()
rebuild_master_color_map(df_master)

# Filter Dataset according to exclusions rules
df_filtered = df_master.copy()
if not df_filtered.empty:
    if exclude_wl:
        df_filtered = df_filtered[~df_filtered['Status'].str.contains("WAITLIST", na=False)]
    if exclude_mv:
        if not section_input or "MV" not in section_input:
            df_filtered = df_filtered[~df_filtered['Section'].str.contains("MV", na=False)]
    if view_mode == "Lectures Only":
        df_filtered = df_filtered[df_filtered['Section'].apply(lambda s: get_section_num(s) < 30)]
    elif view_mode == "Discussions Only":
        df_filtered = df_filtered[df_filtered['Section'].apply(lambda s: get_section_num(s) >= 30)]

# --- SPLIT SCREEN VIEW ARCHITECTURE ---
plot_layout_col, sidebar_layout_col = st.columns([2.8, 1.4])

with sidebar_layout_col:
    st.subheader("📋 Sections Manager")
    req_disc_set = get_courses_requiring_discussion_global()
    
    if not df_filtered.empty:
        df_filtered['UniqueKey'] = df_filtered['CourseNum'] + " - Sec " + df_filtered['Section']
        df_unique = df_filtered.drop_duplicates(subset=['UniqueKey']).sort_values(by=['CourseNum', 'Section'])
        
        st.caption("Toggle checkboxes within each course tab to customize your timeline grid layout.")
        
        # --- DYNAMIC COURSE-BY-COURSE TAB GENERATION ---
        unique_course_ids = sorted(df_unique['CourseNum'].unique())
        course_tabs = st.tabs(unique_course_ids)
        
        for tab_idx, course_id in enumerate(unique_course_ids):
            with course_tabs[tab_idx]:
                df_course_sections = df_unique[df_unique['CourseNum'] == course_id]
                
                for _, row in df_course_sections.iterrows():
                    ukey = row['UniqueKey']
                    sec = row['Section']
                    star = " *" if (course_id in req_disc_set and get_section_num(sec) < 30) else ""
                    
                    if ukey not in st.session_state.selected_sections:
                        st.session_state.selected_sections[ukey] = True
                        
                    is_active = st.session_state.selected_sections[ukey]
                    
                    row_col1, row_col2 = st.columns([0.15, 0.85])
                    with row_col1:
                        st.markdown('<div style="padding-top: 20px;"></div>', unsafe_allow_html=True)
                        is_checked = st.checkbox(
                            f"chk_val_{ukey}", 
                            value=is_active, 
                            key=f"chk_node_{ukey}",
                            label_visibility="collapsed"
                        )
                        st.session_state.selected_sections[ukey] = is_checked

                    if is_checked:
                        rgba_color = st.session_state.master_color_map.get(ukey, (0.5, 0.5, 0.5, 1.0))
                        hex_bg = rgba_to_hex(rgba_color)
                        text_color = "#000000"
                        opacity_style = "opacity: 1.0;"
                        border_style = "border: 1px solid #222222;"
                        shadow_style = "box-shadow: 1px 1px 4px rgba(0,0,0,0.15);"
                    else:
                        hex_bg = "#f0f2f6"
                        text_color = "#888888"
                        opacity_style = "opacity: 0.55;"
                        border_style = "border: 1px dashed #cccccc;"
                        shadow_style = "box-shadow: none;"
                        
                    with row_col2:
                        st.markdown(
                            f"""
                            <div style="background-color: {hex_bg}; {border_style} {opacity_style} {shadow_style}
                                        padding: 6px 10px; border-radius: 4px; margin-top: 4px; transition: all 0.1s ease-in-out;">
                                <span style="font-weight: bold; font-size: 0.82rem; color: {text_color}; display: block; line-height: 1.1; margin-bottom: 3px;">{row['CourseTitle'][:40]}...</span>
                                <span style="font-weight: 800; font-size: 0.88rem; color: {text_color}; display: block;">{course_id}{star} - Sec {sec}</span>
                                <span style="font-size: 0.72rem; color: {text_color}; font-weight: bold; background-color: rgba(255,255,255,0.4); padding: 1px 4px; border-radius: 2px; display: inline-block; margin-top: 3px;">📅 {row['Days']} @ {row['Time']}</span>
                            </div>
                            """, 
                            unsafe_allow_html=True
                        )
                    st.markdown('<div style="margin-bottom: 2px;"></div>', unsafe_allow_html=True)
    else:
        st.info("No courses cached / matching filter constraints.")

with plot_layout_col:
    if not df_filtered.empty:
        df_filtered['UniqueKey'] = df_filtered['CourseNum'] + " - Sec " + df_filtered['Section']
        df_plot = df_filtered[df_filtered['UniqueKey'].apply(lambda k: st.session_state.selected_sections.get(k, False))].copy()
    else:
        df_plot = pd.DataFrame()

    # --- MATPLOTLIB ENGINE GENERATION ---
    fig, ax = plt.subplots(figsize=(11, 6.5))
    ax.clear()
    ax.set_xlim(-0.5, 4.5)
    ax.set_ylim(21.5, 8)  
    ax.set_xticks(range(5))
    ax.set_xticklabels(['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday'])
    ax.set_ylabel("Time Frame (Military Hours Grid)")
    ax.grid(axis='y', linestyle=':', alpha=0.6)
    
    day_mapping = {'M': 0, 'T': 1, 'W': 2, 'R': 3, 'F': 4}
    
    if not df_plot.empty:
        for idx, row in df_plot.iterrows():
            raw_time = row['Time']
            if '-' not in raw_time: continue
            
            start_str, end_str = raw_time.split('-')
            start_h, end_h = parse_time(start_str), parse_time(end_str)
            if start_h is None or end_h is None: continue
                
            ukey = row['UniqueKey']
            box_color = st.session_state.master_color_map.get(ukey, (0.5, 0.5, 0.5, 1.0))
            duration_hours = end_h - start_h
            
            cnum = row['CourseNum']
            sec = row['Section']
            star_marker = "*" if (cnum in req_disc_set and get_section_num(sec) < 30) else ""
            
            # Text layout for active scheduling blocks inside the matrix grid
            display_text = f"{cnum}{star_marker}\nSec {sec}\n{raw_time}"
            
            for day_char in row['Days']:
                if day_char in day_mapping:
                    day_idx = day_mapping[day_char]
                    rect = plt.Rectangle((day_idx - 0.4, start_h), 0.8, duration_hours, 
                                         facecolor=box_color, edgecolor='black', linewidth=0.8, alpha=0.6, zorder=2)
                    ax.add_patch(rect)
                    ax.text(day_idx, start_h + duration_hours/2, display_text, 
                            ha='center', va='center', fontsize=font_size, weight='bold', zorder=3)

    title_summary = ", ".join(sorted(st.session_state.active_courses)) if st.session_state.active_courses else "Empty Grid"
    ax.set_title(f"Schedule Matrix: {title_summary} ({view_mode})", fontsize=11, weight='bold')
    fig.tight_layout()
    
    st.pyplot(fig)
    
    # --- COMBINED SPREADSHEET & PNG EXPORT SYSTEM ---
    if not df_plot.empty:
        st.subheader("📥 Export Pipeline Tools")
        export_columns = ["CourseNum", "CourseTitle", "Section", "CRN", "Status", "Days", "Time"]
        df_export = df_plot[export_columns].copy()
        df_export.columns = ["Course ID", "Course Title", "Section", "CRN", "Status", "Days", "Meeting Time"]
        
        col_ex1, col_ex2 = st.columns(2)
        with col_ex1:
            csv_data = df_export.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Download Schedule as CSV Spreadsheet",
                data=csv_data,
                file_name="gwu_schedule_plan.csv",
                mime="text/csv",
                use_container_width=True
            )
        with col_ex2:
            from io import BytesIO
            img_buffer = BytesIO()
            fig.savefig(img_buffer, format='png', dpi=200, bbox_inches='tight')
            st.download_button(
                label="🖼️ Download Schedule Map Layout Snapshot (PNG)",
                data=img_buffer.getvalue(),
                file_name="gwu_schedule_matrix_snapshot.png",
                mime="image/png",
                use_container_width=True
            )

# --- NATIVE STREAMLIT FOOTER DISCLAIMER BAR ---
st.markdown("---")
st.caption(
    "**⚠️ Disclaimer:** This website is an independent student utility project. It is **not affiliated with, endorsed by, or connected to** "
    "The George Washington University. All schedule records are gathered dynamically via public interfaces. Since class availability updates, "
    "room placements, and schedule adjustments shift frequently, always cross-reference and finalize your course arrangements directly inside "
    "your official **GWeb Info System** portal."
)

# --- MINIMALIST BLACK & WHITE FLOATING BUTTON & PURE MODAL POPUP ENGINE ---
st.markdown(
    """
    <style>
    /* Fixed Floating Minimalist Black Button */
    .floating-help-button {
        position: fixed;
        bottom: 25px;
        right: 25px;
        background-color: #000000;
        color: #FFFFFF !important;
        border: 2px solid #FFFFFF;
        border-radius: 50%;
        width: 46px;
        height: 46px;
        display: flex;
        justify-content: center;
        align-items: center;
        font-size: 20px;
        font-weight: bold;
        box-shadow: 0px 4px 12px rgba(0,0,0,0.4);
        text-decoration: none;
        z-index: 999999;
        cursor: pointer;
        transition: transform 0.15s ease-in-out, background-color 0.15s;
    }
    .floating-help-button:hover {
        transform: scale(1.08);
        background-color: #222222;
    }
    
    /* Full Screen Dimmed Overlay Background */
    .modal-overlay-container {
        position: fixed;
        top: 0;
        left: 0;
        width: 100vw;
        height: 100vh;
        background-color: rgba(0, 0, 0, 0.6);
        backdrop-filter: blur(2px);
        display: none;
        justify-content: center;
        align-items: center;
        z-index: 1000000;
    }
    
    /* Trigger visibility when anchor matches current page hash URL target */
    .modal-overlay-container:target {
        display: flex;
    }
    
    /* True Center Centered Lightbox Modal window content card box */
    .modal-lightbox-card {
        background-color: #FFFFFF;
        padding: 30px;
        border-radius: 8px;
        max-width: 550px;
        width: 90%;
        box-shadow: 0 10px 30px rgba(0,0,0,0.3);
        position: relative;
        animation: popupScaleAnimation 0.2s ease-out;
    }
    
    /* Fix: Hardcode dark, high-contrast text sizing rules for the user warning header layout */
    .modal-lightbox-card h5 {
        color: #111111 !important;
        font-size: 0.92rem;
        margin-top: 10px;
        margin-bottom: 15px;
        line-height: 1.4;
        font-weight: 600;
    }

    @keyframes popupScaleAnimation {
        from { transform: scale(0.85); opacity: 0; }
        to { transform: scale(1); opacity: 1; }
    }
    
    /* Top Right X Close Button */
    .modal-close-trigger {
        position: absolute;
        top: 15px;
        right: 20px;
        font-size: 26px;
        font-weight: bold;
        color: #555555;
        text-decoration: none !important;
        transition: color 0.1s;
    }
    .modal-close-trigger:hover {
        color: #000000;
    }
    
    .modal-lightbox-card h3 {
        margin-top: 0;
        color: #000000;
        font-weight: 800;
        border-bottom: 2px solid #EEEEEE;
        padding-bottom: 10px;
    }
    .modal-lightbox-card ul {
        padding-left: 20px;
        line-height: 1.6;
    }
    .modal-lightbox-card li {
        margin-bottom: 10px;
        font-size: 0.92rem;
        color: #222222 !important;
    }
    </style>
    
    <a href="#architect-popup-guide" class="floating-help-button" title="Open Instructions">?</a>
    
    <div id="architect-popup-guide" class="modal-overlay-container">
        <div class="modal-lightbox-card">
            <a href="#" class="modal-close-trigger">&times;</a>
            <h3>ℹ️ Architect Instructions & Usage Guide</h3>
            <h5> <strong>📝 NOTE:</strong> This tool is designed to help you visualize timeline blocks alongside the official <strong>GW Schedule of Classes</strong> and <strong>GW Bulletin</strong>. It serves as a visual layout matrix and <u>does not</u> automatically account for prerequisites, corequisites, or program degree constraints.</h5>
            <ul>
                <li><strong>Add a Course:</strong> Type a department shorthand code and number (e.g., <code>PSC 1001</code>) into the <b>Course ID</b> field, specify a calendar year, and click <code>Add Course to Matrix</code>.</li>
                <li><strong>Search by Section (Optional):</strong> Narrow down specific selections by providing a section key (e.g., <code>10</code> or <code>MV</code>) <i>before</i> clicking add. Leave it blank to load every possible section.</li>
                <li><strong>Filter Layout:</strong> Use the <b>View Mode</b> menu dropdown grids or exclusions checkbars to hide waitlisted rows or Mount Vernon classes dynamically.</li>
                <li><strong>Show or Hide Course Sections:</strong> Use the tabs in the sidebar to customize your schedule. Under <b>Selected Sections</b>, uncheck any class to instantly remove it from your calendar grid. To add an alternative section or bring a class back, switch to the <b>Unselected Sections</b> tab and check its box to reactivate it.</li>
                <li><strong>Export Deliverables:</strong> Download your layout cleanly as a structured spreadsheet data matrix (<code>.csv</code>) or capture timeline layouts as clear snapshots (<code>.png</code>).</li>
            </ul>
        </div>
    </div>
    """,
    unsafe_allow_html=True
)
