from flask import Flask, request, session, redirect, url_for, render_template
import requests
import csv
import os
import urllib3

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

from waitress import serve

if __name__ == "__main__":
    serve(app, host="0.0.0.0", port=5000, threads=10)
