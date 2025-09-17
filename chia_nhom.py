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

def summarize_groups(groups, ca_name):
    print(f"\n===== CA: {ca_name} | Số nhóm = {len(groups)} =====")
    for i, g in enumerate(groups, 1):
        if len(g) == 0:
            print(f"\nNhóm {i}: (rỗng)")
            continue
        dfg = pd.DataFrame(g)
        avg = dfg["Điểm tổng"].mean()
        leaders = ((dfg["Vai trò mong muốn"] == "Nhóm trưởng") | (dfg["Vai trò mong muốn"] == "Nhóm trưởng (tạm)")).sum()
        targets = dict(Counter(dfg["Mục tiêu"].tolist()))
        skillset = set()
        for s in dfg["Điểm mạnh_list"]:
            for it in s:
                skillset.add(it)
        print(f"\nNhóm {i}: n={len(dfg)} | Điểm TB = {avg:.2f} | Leaders = {leaders}")
        print("  Mục tiêu:", targets)
        print("  Kỹ năng có:", skillset)
        print(dfg[["MSSV","Họ tên","GPA","Điểm ĐTĐM","Điểm tổng","Vai trò mong muốn","Mục tiêu","Điểm mạnh"]].to_string(index=False))

def process_ca(df_ca, group_size=GROUP_SIZE):
    df_ca = df_ca.copy().reset_index(drop=True)
    groups = snake_draft_assign(df_ca, group_size=group_size)
    groups = ensure_leaders(groups)
    groups = balance_targets(groups)
    groups = balance_skills(groups)
    return groups

def main(input_csv="64HTTT2.csv", output_csv="64HTTT2_grouped.csv"):
    df = prepare_df(input_csv)
    df = compute_scores(df)
    result_rows = []
    all_ca = df["Ca học"].unique()
    for ca in all_ca:
        df_ca = df[df["Ca học"] == ca].copy().reset_index(drop=True)
        if df_ca.empty:
            continue
        groups = process_ca(df_ca, group_size=GROUP_SIZE)
        summarize_groups(groups, ca)
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
