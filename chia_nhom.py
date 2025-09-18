import pandas as pd
import math
import random
from collections import Counter

random.seed(42)

GROUP_SIZE = 5

SKILLS = ["Lập trình", "Thuyết trình", "Thiết kế", "Tìm nội dung"]
TARGETS = ["A", "B", "C", "D"]

def normalize_skill_list(s):
    if pd.isna(s):
        return []
    if isinstance(s, list):
        return s
    return [x.strip() for x in str(s).split(";") if x.strip()]

def prepare_df(path):
    df = pd.read_csv(path, encoding="utf-8-sig")
    df = df.rename(columns=lambda c: c.strip())
    df["GPA"] = pd.to_numeric(df["GPA"], errors="coerce").fillna(0)
    df["Điểm ĐTĐM"] = pd.to_numeric(df.get("Điểm ĐTĐM", 0), errors="coerce").fillna(0)
    df["Điểm mạnh_list"] = df["Điểm mạnh"].apply(normalize_skill_list)
    return df

def compute_scores(df, w_gpa=0.6, w_dtdm=0.4):
    df["ĐTĐM_4"] = df["Điểm ĐTĐM"] * (4/10)
    df["Điểm tổng"] = df.apply(lambda row: row["GPA"] if pd.isna(row["Điểm ĐTĐM"]) or row["Điểm ĐTĐM"] == 0 
                                else w_gpa * row["GPA"] + w_dtdm * row["ĐTĐM_4"], axis=1)
    return df

def snake_draft_assign(df_ca, group_size=GROUP_SIZE):
    n = len(df_ca)
    num_groups = max(1, math.ceil(n / group_size))
    sorted_df = df_ca.sort_values(by="Điểm tổng", ascending=False).reset_index(drop=True)
    groups = [[] for _ in range(num_groups)]

    idx, direction = 0, 1
    for i, row in sorted_df.iterrows():
        groups[idx].append(row.to_dict())
        idx += direction
        if idx == num_groups:
            idx = num_groups - 1
            direction = -1
        elif idx < 0:
            idx = 0
            direction = 1
    return groups

def ensure_leaders(groups):
    for g in groups:
        dfg = pd.DataFrame(g)
        if len(dfg) == 0:
            continue
        n_leaders = (dfg["Vai trò mong muốn"] == "Nhóm trưởng").sum()
        if n_leaders == 0:
            candidates = dfg.copy()
            def pref_score(row):
                skills = normalize_skill_list(row["Điểm mạnh"])
                pref = 1 if ("Lập trình" in skills or "Thuyết trình" in skills) else 0
                return (pref, row["Điểm tổng"])
            candidates["pref"] = candidates.apply(pref_score, axis=1)
            candidates = candidates.sort_values(by=["pref", "Điểm tổng"], ascending=[False, False])
            chosen = candidates.iloc[0]
            for member in g:
                if member["MSSV"] == chosen["MSSV"]:
                    member["Vai trò mong muốn"] = "Nhóm trưởng (tạm)"
                    break
    return groups

def balance_targets(groups, max_iter=200):
    num_groups = len(groups)
    def group_target_counts(groups):
        counts = []
        for g in groups:
            dfg = pd.DataFrame(g)
            cnt = Counter(dfg["Mục tiêu"].tolist())
            counts.append(cnt)
        return counts

    total_counts = Counter()
    for g in groups:
        total_counts.update(pd.DataFrame(g)["Mục tiêu"].tolist())

    desired = {t: [0]*num_groups for t in TARGETS}
    for t in TARGETS:
        total = total_counts.get(t, 0)
        base = total // num_groups
        rem = total % num_groups
        for i in range(num_groups):
            desired[t][i] = base + (1 if i < rem else 0)

    it = 0
    while it < max_iter:
        it += 1
        counts = group_target_counts(groups)
        moved = False
        for t in TARGETS:
            for i in range(num_groups):
                if counts[i].get(t, 0) > desired[t][i]:
                    for j in range(num_groups):
                        if counts[j].get(t, 0) < desired[t][j]:
                            gi = pd.DataFrame(groups[i])
                            gj = pd.DataFrame(groups[j])
                            cand_i = gi[gi["Mục tiêu"] == t]
                            if cand_i.empty:
                                continue
                            cand_j = gj
                            if cand_j.empty:
                                continue
                            best_pair = None
                            best_diff = None
                            for _, a in cand_i.iterrows():
                                for _, b in cand_j.iterrows():
                                    diff = abs(a["Điểm tổng"] - b["Điểm tổng"])
                                    if best_diff is None or diff < best_diff:
                                        best_diff = diff
                                        best_pair = (a, b)
                            if best_pair is None:
                                continue
                            a, b = best_pair
                            def replace_member(group, ms_old, new_row):
                                for idx, mem in enumerate(group):
                                    if mem["MSSV"] == ms_old:
                                        group[idx] = new_row.to_dict()
                                        return True
                                return False
                            replace_member(groups[i], a["MSSV"], b)
                            replace_member(groups[j], b["MSSV"], a)
                            moved = True
                            break
                        if moved:
                            break
                if moved:
                    break
            if moved:
                break
        if not moved:
            break
    return groups

def balance_skills(groups, max_iter=300):
    num_groups = len(groups)
    def group_has_skill(group, skill):
        for mem in group:
            if skill in normalize_skill_list(mem.get("Điểm mạnh","")):
                return True
        return False

    it = 0
    while it < max_iter:
        it += 1
        moved = False
        for skill in SKILLS:
            missing_groups = [i for i,g in enumerate(groups) if not group_has_skill(g, skill)]
            if not missing_groups:
                continue
            for tgt in missing_groups:
                donor_found = False
                for donor_idx, donor in enumerate(groups):
                    if donor_idx == tgt:
                        continue
                    donor_members = [m for m in donor if skill in normalize_skill_list(m.get("Điểm mạnh",""))]
                    if not donor_members:
                        continue
                    donor_members_sorted = sorted(donor_members, key=lambda m: (m.get("Vai trò mong muốn","")=="Nhóm trưởng", -m["Điểm tổng"]))
                    donor_candidate = donor_members_sorted[0]
                    tgt_candidates = [m for m in groups[tgt] if skill not in normalize_skill_list(m.get("Điểm mạnh",""))]
                    if not tgt_candidates:
                        continue
                    tgt_candidates_sorted = sorted(tgt_candidates, key=lambda m: (m.get("Vai trò mong muốn","")=="Nhóm trưởng", abs(m["Điểm tổng"]-donor_candidate["Điểm tổng"])))
                    tgt_candidate = tgt_candidates_sorted[0]
                    def swap_members(g1, g2, ms1, ms2):
                        for i, mem in enumerate(g1):
                            if mem["MSSV"] == ms1:
                                row1 = mem
                                idx1 = i
                                break
                        for j, mem in enumerate(g2):
                            if mem["MSSV"] == ms2:
                                row2 = mem
                                idx2 = j
                                break
                        g1[idx1], g2[idx2] = row2, row1

                    swap_members(groups[donor_idx], groups[tgt], donor_candidate["MSSV"], tgt_candidate["MSSV"])
                    moved = True
                    donor_found = True
                    break
                if not donor_found:
                    continue
        if not moved:
            break
    return groups

def balance_scores(groups, max_iter=300):
    """Hoán đổi sinh viên để điểm trung bình các nhóm gần nhau nhất."""
    it = 0
    while it < max_iter:
        it += 1
        moved = False
        avgs = [pd.DataFrame(g)["Điểm tổng"].mean() for g in groups]
        max_gid = int(pd.Series(avgs).idxmax())
        min_gid = int(pd.Series(avgs).idxmin())
        diff = avgs[max_gid] - avgs[min_gid]
        if diff < 0.05:  # chênh lệch nhỏ thì dừng
            break
        gmax = pd.DataFrame(groups[max_gid])
        gmin = pd.DataFrame(groups[min_gid])
        best_pair = None
        best_gap = diff
        for _, a in gmax.iterrows():
            for _, b in gmin.iterrows():
                new_avgs = avgs.copy()
                new_avgs[max_gid] = (gmax["Điểm tổng"].sum() - a["Điểm tổng"] + b["Điểm tổng"]) / len(gmax)
                new_avgs[min_gid] = (gmin["Điểm tổng"].sum() - b["Điểm tổng"] + a["Điểm tổng"]) / len(gmin)
                new_diff = max(new_avgs) - min(new_avgs)
                if new_diff < best_gap:
                    best_gap = new_diff
                    best_pair = (a, b)
        if best_pair is not None:
            a, b = best_pair
            def replace_member(group, ms_old, new_row):
                for idx, mem in enumerate(group):
                    if mem["MSSV"] == ms_old:
                        group[idx] = new_row.to_dict()
                        return True
                return False
            replace_member(groups[max_gid], a["MSSV"], b)
            replace_member(groups[min_gid], b["MSSV"], a)
            moved = True
        if not moved:
            break
    return groups

def summarize_groups_html(groups, ca):
    html = f"<h4>===== CA: {ca} | Số nhóm = {len(groups)} =====</h4>"
    
    for gid, g in enumerate(groups, 1):
        df = pd.DataFrame(g)

        avg_score = df["Điểm tổng"].mean()
        leaders = (df["Vai trò mong muốn"].str.contains("Nhóm trưởng")).sum()
        goals = df["Mục tiêu"].value_counts().to_dict()

        skills = set()
        for s in df["Điểm mạnh"]:
            if isinstance(s, str):
                for part in s.split(";"):
                    skills.add(part.strip())

        html += f"""
        <div style='margin:15px 0;padding:10px;border:1px solid #ccc;'>
          <b>Nhóm {gid}:</b> n={len(df)} | 
          Điểm TB = {avg_score:.2f} | 
          Leaders = {leaders}<br>
          <i>Mục tiêu:</i> {goals}<br>
          <i>Kỹ năng có:</i> {skills}<br>
        """

        df = df.reset_index(drop=True)
        df.insert(0, "STT", df.index + 1)

        show_cols = ["STT","MSSV","Họ tên","GPA","Điểm ĐTĐM","Điểm tổng",
                    "Vai trò mong muốn","Mục tiêu","Điểm mạnh"]
        show_cols = [c for c in show_cols if c in df.columns]
        html += df[show_cols].to_html(index=False, escape=False)

        html += "</div>"

    return html

def balance_leader_fairness(groups, score_threshold=0.05):
    """Đảm bảo nhóm nào cũng có leader thực thụ bằng cách hoán đổi hợp lý dựa trên điểm tổng."""
    for i, g in enumerate(groups):
        df_g = pd.DataFrame(g)
        leaders_g = df_g[df_g["Vai trò mong muốn"] == "Nhóm trưởng"]

        # Nếu nhóm này chưa có leader thực thụ
        if leaders_g.empty:
            # Lấy danh sách candidate (thành viên có điểm tổng cao trong nhóm thiếu)
            candidates = df_g.sort_values("Điểm tổng", ascending=False)

            # Duyệt các nhóm khác để tìm nhóm thừa leader
            for j, g2 in enumerate(groups):
                if i == j:
                    continue
                df_g2 = pd.DataFrame(g2)
                leaders_g2 = df_g2[df_g2["Vai trò mong muốn"] == "Nhóm trưởng"]

                # Chỉ xét nhóm có thừa leader
                if len(leaders_g2) <= 1:
                    continue

                # Tìm cặp leader ↔ member có Điểm tổng gần nhau
                best_pair = None
                best_diff = None
                for _, mem in candidates.iterrows():
                    for _, leader in leaders_g2.iterrows():
                        diff = abs(mem["Điểm tổng"] - leader["Điểm tổng"])
                        if diff <= score_threshold:
                            if best_diff is None or diff < best_diff:
                                best_diff = diff
                                best_pair = (mem, leader)

                # Nếu tìm được cặp phù hợp thì hoán đổi
                if best_pair:
                    mem, leader = best_pair

                    # Hàm hỗ trợ thay thế member trong group
                    def replace_member(group, ms_old, new_row):
                        for idx, mem_ in enumerate(group):
                            if mem_["MSSV"] == ms_old:
                                group[idx] = new_row.to_dict()
                                return True
                        return False

                    # Swap
                    replace_member(groups[i], mem["MSSV"], leader)
                    replace_member(groups[j], leader["MSSV"], mem)

                    # Cập nhật vai trò
                    for m in groups[i]:
                        if m["MSSV"] == leader["MSSV"]:
                            m["Vai trò mong muốn"] = "Nhóm trưởng"
                    for m in groups[j]:
                        if m["MSSV"] == mem["MSSV"]:
                            m["Vai trò mong muốn"] = "Thành viên"

                    break  # Xử lý xong nhóm thiếu leader này → thoát
    return groups

def final_balance_scores(groups, max_iter=300):
    """Cân bằng điểm trung bình giữa các nhóm sau tất cả các bước chia.
       Chỉ hoán đổi thành viên thường, giữ nguyên leader chính thức."""
    it = 0
    while it < max_iter:
        it += 1
        moved = False
        avgs = [pd.DataFrame(g)["Điểm tổng"].mean() for g in groups]
        max_gid = int(pd.Series(avgs).idxmax())
        min_gid = int(pd.Series(avgs).idxmin())
        diff = avgs[max_gid] - avgs[min_gid]

        gmax = pd.DataFrame(groups[max_gid])
        gmin = pd.DataFrame(groups[min_gid])

        best_pair = None
        best_gap = diff

        for _, a in gmax.iterrows():
            if "Nhóm trưởng" in str(a["Vai trò mong muốn"]):  
                continue  # giữ nguyên leader
            for _, b in gmin.iterrows():
                if "Nhóm trưởng" in str(b["Vai trò mong muốn"]):
                    continue
                new_avgs = avgs.copy()
                new_avgs[max_gid] = (gmax["Điểm tổng"].sum() - a["Điểm tổng"] + b["Điểm tổng"]) / len(gmax)
                new_avgs[min_gid] = (gmin["Điểm tổng"].sum() - b["Điểm tổng"] + a["Điểm tổng"]) / len(gmin)
                new_diff = max(new_avgs) - min(new_avgs)
                if new_diff < best_gap:
                    best_gap = new_diff
                    best_pair = (a, b)

        if best_pair:
            a, b = best_pair
            def replace_member(group, ms_old, new_row):
                for idx, mem in enumerate(group):
                    if mem["MSSV"] == ms_old:
                        group[idx] = new_row.to_dict()
                        return True
                return False
            replace_member(groups[max_gid], a["MSSV"], b)
            replace_member(groups[min_gid], b["MSSV"], a)
            moved = True

        if not moved:
            break
    return groups

def rebalance_group_sizes(groups):
    """Nếu có nhóm 5 và nhóm 4, thử mượn 1 thành viên để cân bằng điểm TB."""
    for i, g_small in enumerate(groups):
        if len(g_small) >= 5:
            continue
        for j, g_big in enumerate(groups):
            if len(g_big) <= 4:
                continue

            best_swap = None
            best_diff = None
            for idx, member in enumerate(g_big):
                if member["Vai trò mong muốn"] == "Nhóm trưởng":
                    continue  # không mượn leader

                # Thử di chuyển member này
                new_small = g_small + [member]
                new_big = g_big[:idx] + g_big[idx+1:]

                tb_small = sum(s["Điểm tổng"] for s in new_small) / len(new_small)
                tb_big = sum(s["Điểm tổng"] for s in new_big) / len(new_big)
                tb_all = [sum(s["Điểm tổng"] for s in g) / len(g) for g in groups]

                diff = max(tb_all) - min(tb_all)
                if best_diff is None or diff < best_diff:
                    best_diff = diff
                    best_swap = (i, j, idx)

            if best_swap:
                i, j, idx = best_swap
                member = groups[j].pop(idx)
                groups[i].append(member)
                return groups  # chỉ làm 1 lần
    return groups


def rebalance_scores_threshold(groups, threshold=0.05):
    """Nếu lệch điểm TB vượt ngưỡng, swap để ưu tiên cân bằng điểm."""
    tb_list = [sum(s["Điểm tổng"] for s in g) / len(g) for g in groups]
    if max(tb_list) - min(tb_list) <= threshold:
        return groups  # không cần chỉnh

    # Chọn nhóm cao nhất và thấp nhất
    idx_high = tb_list.index(max(tb_list))
    idx_low = tb_list.index(min(tb_list))
    g_high, g_low = groups[idx_high], groups[idx_low]

    best_pair = None
    best_gap = None
    for m_high in g_high:
        if m_high["Vai trò mong muốn"] == "Nhóm trưởng":
            continue
        for m_low in g_low:
            if m_low["Vai trò mong muốn"] == "Nhóm trưởng":
                continue
            # swap giả định
            new_high = [m if m["MSSV"] != m_high["MSSV"] else m_low for m in g_high]
            new_low = [m if m["MSSV"] != m_low["MSSV"] else m_high for m in g_low]

            tb_high = sum(s["Điểm tổng"] for s in new_high) / len(new_high)
            tb_low = sum(s["Điểm tổng"] for s in new_low) / len(new_low)
            gap = abs(tb_high - tb_low)

            if best_gap is None or gap < best_gap:
                best_gap = gap
                best_pair = (m_high, m_low, idx_high, idx_low)

    if best_pair:
        m_high, m_low, idx_high, idx_low = best_pair
        # thực hiện swap
        for idx, m in enumerate(groups[idx_high]):
            if m["MSSV"] == m_high["MSSV"]:
                groups[idx_high][idx] = m_low
        for idx, m in enumerate(groups[idx_low]):
            if m["MSSV"] == m_low["MSSV"]:
                groups[idx_low][idx] = m_high

    return groups

def strict_balance_scores(groups, threshold=0.05, max_iter=300):
    it = 0
    while it < max_iter:
        it += 1
        avgs = [pd.DataFrame(g)["Điểm tổng"].mean() for g in groups]
        max_gid = int(pd.Series(avgs).idxmax())
        min_gid = int(pd.Series(avgs).idxmin())
        diff = avgs[max_gid] - avgs[min_gid]

        if diff <= threshold:
            break

        gmax = pd.DataFrame(groups[max_gid])
        gmin = pd.DataFrame(groups[min_gid])

        best_pair = None
        best_gap = diff

        for _, a in gmax.iterrows():
            if "Nhóm trưởng" in str(a["Vai trò mong muốn"]):
                continue
            for _, b in gmin.iterrows():
                if "Nhóm trưởng" in str(b["Vai trò mong muốn"]):
                    continue

                new_avgs = avgs.copy()
                new_avgs[max_gid] = (gmax["Điểm tổng"].sum() - a["Điểm tổng"] + b["Điểm tổng"]) / len(gmax)
                new_avgs[min_gid] = (gmin["Điểm tổng"].sum() - b["Điểm tổng"] + a["Điểm tổng"]) / len(gmin)
                new_diff = max(new_avgs) - min(new_avgs)

                if new_diff < best_gap:
                    best_gap = new_diff
                    best_pair = (a, b)

        if best_pair:
            a, b = best_pair
            # dùng replace_member thay vì gán DataFrame
            def replace_member(group, ms_old, new_row):
                for idx, mem in enumerate(group):
                    if mem["MSSV"] == ms_old:
                        group[idx] = new_row.to_dict()
                        return True
                return False

            replace_member(groups[max_gid], a["MSSV"], b)
            replace_member(groups[min_gid], b["MSSV"], a)
        else:
            break
    return groups



def process_ca(df_ca, group_size=GROUP_SIZE):
    df_ca = df_ca.copy().reset_index(drop=True)
    groups = snake_draft_assign(df_ca, group_size=group_size)
    groups = ensure_leaders(groups)
    groups = balance_targets(groups)
    groups = balance_skills(groups)
    groups = balance_scores(groups)  # thêm bước cân bằng điểm
    groups = ensure_leaders(groups)  # đảm bảo sau khi hoán đổi vẫn có leader
    groups = balance_leader_fairness(groups)
    groups = final_balance_scores(groups)
    groups = rebalance_group_sizes(groups)
    groups = rebalance_scores_threshold(groups, threshold=0.05)
    groups = strict_balance_scores(groups, threshold=0.05)


    for group in groups:
        official_leaders = [s for s in group if s["Vai trò mong muốn"] == "Nhóm trưởng"]
        temp_leaders = [s for s in group if s["Vai trò mong muốn"] == "Nhóm trưởng (tạm)"]

        if not official_leaders and not temp_leaders:
            # Nếu chưa có trưởng nào -> chọn 1 người làm trưởng tạm
            best_candidate = max(group, key=lambda s: s["Điểm tổng"])
            best_candidate["Vai trò mong muốn"] = "Nhóm trưởng (tạm)"
        elif official_leaders:
            # Nếu đã có trưởng chính thức -> xoá hết trưởng tạm
            for s in temp_leaders:
                s["Vai trò mong muốn"] = "Thành viên"
        elif len(temp_leaders) > 1:
            # Nếu chỉ có toàn trưởng tạm nhưng nhiều hơn 1 -> giữ 1 người điểm cao nhất
            best_candidate = max(temp_leaders, key=lambda s: s["Điểm tổng"])
            for s in temp_leaders:
                if s is not best_candidate:
                    s["Vai trò mong muốn"] = "Thành viên"

    return groups

def main(input_csv="sinhvientest.csv", output_csv="sinhvientest_grouped.csv"):
    df = prepare_df(input_csv)
    df = compute_scores(df)
    result_rows = []
    all_ca = df["Ca học"].unique()
    for ca in all_ca:
        df_ca = df[df["Ca học"] == ca].copy().reset_index(drop=True)
        if df_ca.empty:
            continue
        groups = process_ca(df_ca, group_size=GROUP_SIZE)
        summarize_groups_html(groups, ca)
        for gid, g in enumerate(groups, 1):
            for mem in g:
                row = mem.copy()
                row["GroupID"] = f"{ca}_G{gid}"
                result_rows.append(row)
    out_df = pd.DataFrame(result_rows)
    cols_order = ["GroupID","MSSV","Họ tên","Lớp hiện tại","Ca học","GPA","Điểm ĐTĐM","ĐTĐM_4","Điểm tổng","Vai trò mong muốn","Mục tiêu","Điểm mạnh"]
    cols_present = [c for c in cols_order if c in out_df.columns]
    out_df = out_df[cols_present + [c for c in out_df.columns if c not in cols_present]]
    out_df.to_csv(output_csv, index=False, encoding="utf-8-sig")
    print(f"\nKết quả đã được lưu: {output_csv}")

if __name__ == "__main__":
    main()
