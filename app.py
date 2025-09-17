from flask import Flask, request, session, redirect, url_for, render_template, send_file
from chia_nhom import prepare_df, compute_scores, process_ca, summarize_groups_html, GROUP_SIZE
import requests
import csv
import os
import urllib3
import io

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)
app.secret_key = "super_secret_key"

def get_ca(start_index, end_index):
    if start_index == 1 and end_index == 3:
        return "Ca 1"
    elif start_index == 4 and end_index == 6:
        return "Ca 2"
    elif start_index == 7 and end_index == 9:
        return "Ca 3"
    elif start_index == 10 and end_index == 12:
        return "Ca 4"
    return None

def extract_cse414_practice_ca(response_json):
    cas = []
    for course in response_json:
        subj = course.get("courseSubject", {})
        sem_subj = subj.get("semesterSubject", {}).get("subject", {})
        subject_code = sem_subj.get("subjectCode")

        if subject_code == "CSE414" and subj.get("courseSubjectType") == 6:
            for tt in subj.get("timetables", []):
                start_index = tt.get("startHour", {}).get("indexNumber")
                end_index = tt.get("endHour", {}).get("indexNumber")
                ca = get_ca(start_index, end_index)
                if ca:
                    cas.append(ca)

    return list(set(cas))

@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        url_token = "https://sinhvien1.tlu.edu.vn/education/oauth/token"
        data = {
            "client_id": "education_client",
            "client_secret": "password",
            "grant_type": "password",
            "username": username,
            "password": password,
        }
        resp = requests.post(url_token, data=data, verify=False)
        if resp.status_code == 200:
            token_info = resp.json()
            session["access_token"] = token_info["access_token"]
            session["username"] = username
            return redirect(url_for("form"))
        elif username == ADMIN_USER and password == ADMIN_PASS:
            session["is_admin"] = True
            return redirect(url_for("admin"))
        else:
            return render_template("login.html", error="Sai MSSV hoặc mật khẩu")

    return render_template("login.html", error=None)

@app.route("/form", methods=["GET", "POST"])
def form():
    if "access_token" not in session:
        return redirect(url_for("login"))

    headers = {"Authorization": f"Bearer {session['access_token']}"}
    mssv = session["username"]

    url_summary = "https://sinhvien1.tlu.edu.vn/education/api/studentsummarymark/getbystudent"
    url_marks = "https://sinhvien1.tlu.edu.vn/education/api/studentsubjectmark/getListStudentMarkBySemesterByLoginUser/0"
    url_courses = "https://sinhvien1.tlu.edu.vn/education/api/StudentCourseSubject/studentLoginUser/13"

    from concurrent.futures import ThreadPoolExecutor

    def fetch(url):
        return requests.get(url, headers=headers, verify=False).json()

    with ThreadPoolExecutor() as executor:
        future_summary = executor.submit(fetch, url_summary)
        future_marks = executor.submit(fetch, url_marks)
        future_courses = executor.submit(fetch, url_courses)

        summary = future_summary.result()
        marks_data = future_marks.result()
        courses_data = future_courses.result()

    student = summary.get("student", {})
    name = student.get("displayName")
    class_name = student.get("enrollmentClass", {}).get("className")
    gpa = summary.get("mark4")

    cse393 = None
    for item in marks_data:
        if isinstance(item, dict) and item.get("subject", {}).get("subjectCode") == "CSE393":
            cse393 = item.get("mark")
            break

    cas_cse414 = extract_cse414_practice_ca(courses_data)

    if request.method == "POST":
        registered_class = request.form["registered_class"]
        goal = request.form["goal"]
        strengths = request.form.getlist("strength")
        strength = "; ".join(strengths)
        role = request.form["role"]

        classes = ["64HTTT1", "64HTTT2", "64HTTT3", "64HTTT4"]
        header = ["MSSV", "Họ tên", "Lớp hiện tại", "GPA", "Điểm ĐTĐM", "Ca học",
                  "Mục tiêu", "Điểm mạnh", "Vai trò mong muốn"]

        for cls in classes:
            if cls == registered_class:
                continue
            file_path = f"{cls}.csv"
            if os.path.exists(file_path):
                rows = []
                with open(file_path, "r", newline="", encoding="utf-8-sig") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        if row["MSSV"] != mssv:
                            rows.append(row)
                with open(file_path, "w", newline="", encoding="utf-8-sig") as f:
                    writer = csv.DictWriter(f, fieldnames=reader.fieldnames)
                    writer.writeheader()
                    writer.writerows(rows)

        class_file = f"{registered_class}.csv"
        if not os.path.exists(class_file) or os.path.getsize(class_file) == 0:
            with open(class_file, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.DictWriter(f, fieldnames=header)
                writer.writeheader()

        rows = []
        updated = False
        if os.path.exists(class_file):
            with open(class_file, "r", newline="", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row["MSSV"] == mssv:
                        row = {
                            "MSSV": mssv,
                            "Họ tên": name,
                            "Lớp hiện tại": class_name,
                            "GPA": gpa,
                            "Điểm ĐTĐM": cse393,
                            "Ca học": ", ".join(cas_cse414),
                            "Mục tiêu": goal,
                            "Điểm mạnh": strength,
                            "Vai trò mong muốn": role
                        }
                        updated = True
                    rows.append(row)

        if not updated:
            rows.append({
                "MSSV": mssv,
                "Họ tên": name,
                "Lớp hiện tại": class_name,
                "GPA": gpa,
                "Điểm ĐTĐM": cse393,
                "Ca học": ", ".join(cas_cse414),
                "Mục tiêu": goal,
                "Điểm mạnh": strength,
                "Vai trò mong muốn": role
            })

        with open(class_file, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=header)
            writer.writeheader()
            writer.writerows(rows)

        return render_template("submitted.html", name=name, registered_class=registered_class)


    return render_template("form.html", name=name, mssv=mssv,
                       class_name=class_name, gpa=gpa, cse393=cse393,
                       cas_cse414=cas_cse414)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

import pandas as pd

ADMIN_USER = "admin"
ADMIN_PASS = "123456"  # đổi theo ý bạn

@app.route("/admin", methods=["GET", "POST"])
def admin():
    if "is_admin" not in session:
        return redirect(url_for("login"))

    classes = ["64HTTT1", "64HTTT2", "64HTTT3", "64HTTT4"]
    selected_class = request.args.get("class")
    df = None
    grouped = None
    output_file = None
    html_summaries = []

    if selected_class:
        file_path = f"{selected_class}.csv"
        if os.path.exists(file_path):
            df = pd.read_csv(file_path, encoding="utf-8-sig")
            df = df.reset_index(drop=True)
            df.insert(0, "STT", df.index + 1)

        action = request.args.get("action")
        if action == "group" and df is not None:
            df_scored = compute_scores(prepare_df(file_path))
            for ca in df_scored["Ca học"].unique():
                df_ca = df_scored[df_scored["Ca học"] == ca].copy().reset_index(drop=True)
                if df_ca.empty:
                    continue
                groups = process_ca(df_ca, group_size=GROUP_SIZE)
                html_summary = summarize_groups_html(groups, ca)
                html_summaries.append(html_summary)

            cols_display = [
                "STT","MSSV","Họ tên","Lớp hiện tại","GPA","Điểm ĐTĐM",
                "Ca học","Mục tiêu","Điểm mạnh","Vai trò mong muốn"
            ]
            cols_display = [c for c in cols_display if c in df.columns]
            df = df[cols_display]


        elif action == "export" and df is not None:
            df = compute_scores(prepare_df(file_path))
            all_ca = df["Ca học"].unique()
            result_rows = []

            for ca in all_ca:
                df_ca = df[df["Ca học"] == ca].copy().reset_index(drop=True)
                if df_ca.empty:
                    continue
                groups = process_ca(df_ca, group_size=GROUP_SIZE)
                summarize_groups_html(groups, ca)  # nếu muốn hiện nhóm trên web
                for gid, g in enumerate(groups, 1):
                    for mem in g:
                        row = mem.copy()
                        row["GroupID"] = f"{ca}_G{gid}"
                        result_rows.append(row)

            out_df = pd.DataFrame(result_rows)

            # thêm cột STT
            out_df.insert(0, "STT", range(1, len(out_df) + 1))

            cols_order = [
                "STT","GroupID","MSSV","Họ tên","Lớp hiện tại","Ca học",
                "GPA","Điểm ĐTĐM","ĐTĐM_4","Điểm tổng",
                "Vai trò mong muốn","Mục tiêu","Điểm mạnh"
            ]
            cols_present = [c for c in cols_order if c in out_df.columns]
            out_df = out_df[cols_present]


            # Xuất file trực tiếp về client (không lưu trên server)
            output_file = f"{selected_class}_grouped.csv"
            buf = io.StringIO()
            out_df.to_csv(buf, index=False, encoding="utf-8-sig")
            buf.seek(0)

            return send_file(
                io.BytesIO(buf.getvalue().encode("utf-8-sig")),
                as_attachment=True,
                download_name=output_file,
                mimetype="text/csv"
            )
    return render_template("admin.html", 
                           classes=classes, 
                           selected_class=selected_class,
                           df=df, 
                           grouped=grouped, 
                           output_file=output_file,
                           html_summaries=html_summaries)


from waitress import serve

if __name__ == "__main__":
    serve(app, host="0.0.0.0", port=5000, threads=10)
