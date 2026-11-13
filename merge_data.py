

"""
Assignment 2 (ENCS5341) - Data Integration  (v3)
------------------------------------------------
1) Extracts every student's zip file (also zips nested inside zips) into extracted/<student_id>/
2) Reads every CSV (falls back to Excel only if a student has no CSV), skipping macOS junk
   files (._*, __MACOSX, .DS_Store)
3) Standardizes column NAMES only (lowercase, underscores, obvious variants such as
   photo / image_file / item_photo -> item_photo). Cell values are never modified.
4) Adds tracking columns: global_id (1..N), student_id, source_file, image_path
5) Finds each row's image inside that student's own extracted folder and copies it to
   output/images/<global_id>_<student_id>.<ext> (unique names, no collisions)
6) Saves output/marketplace_raw.csv, merge_report.txt, missing_images.csv

Usage:
    python merge_data.py
    or:  python merge_data.py "C:\\path\\to\\compressed-attachments"

Requirements: Python 3.8+, pandas, openpyxl (only needed for .xlsx files)
"""
import patoolib
import csv
import re
import shutil
import sys
import zipfile
from collections import Counter
from pathlib import Path, PurePosixPath

import pandas as pd

# ============================ Settings (edit if needed) ============================


HERE = Path(__file__).resolve().parent
DEFAULT_BASE = HERE / "compressed-attachments" / "compressed-attachments"
BASE = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_BASE
EXTRACTED = HERE / "extracted"          # zips are extracted here (originals are never touched)
OUTPUT = HERE / "output"                # results (re-created on every run)
IMAGES_OUT = OUTPUT / "images"          # all images together, with unique names

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".jfif", ".heic", ".tif", ".tiff", ".avif"}
EXCEL_EXTS = {".xlsx", ".xlsm", ".xls"}
ENCODINGS = ("utf-8-sig", "cp1256", "cp1252", "latin-1")
IMG_HINTS = ("image", "img", "photo", "pic", "صورة")

# Exact (normalized) column-name variants -> one standard name. Names only, never values.
CANONICAL = {
    "id": "item_id",
    "item_photo_filename": "item_photo",
    "image_path": "item_photo",
    "image_name": "item_photo",
    "item_image_filename": "item_photo",
    "item_photo": "item_photo", "photo": "item_photo", "image": "item_photo",
    "image_file": "item_photo", "image_filename": "item_photo",
    "photo_filename": "item_photo", "item_image": "item_photo",
    "age": "age", "age_years": "age", "age_year": "age",
    "approximate_age": "age", "approximate_age_years": "age",
    "condition": "condition", "condition_1_5": "condition",
    "descreption": "description",
}
# ===================================================================================

report = []


def log(msg=""):
    """Print a message and keep it for merge_report.txt."""
    print(msg)
    report.append(str(msg))


def is_junk(p):
    """macOS metadata files that are not real data."""
    return "__MACOSX" in p.parts or p.name.startswith("._") or p.name == ".DS_Store"


# ------------------------------------------------------------------ extraction
def extract_zip(z, dest):
    with zipfile.ZipFile(z) as zf:
        zf.extractall(dest)


def extract_rar(rar_path, target):
    target.mkdir(parents=True, exist_ok=True)
    patoolib.extract_archive(str(rar_path), outdir=str(target))


def extract_all():
    """Extract each student's zip/rar files into extracted/<student_id>/."""
    EXTRACTED.mkdir(exist_ok=True)
    folders = sorted(p for p in BASE.iterdir() if p.is_dir())

    log(f"Number of student folders: {len(folders)}")

    for folder in folders:
        target = EXTRACTED / folder.name
        target.mkdir(exist_ok=True)

        # loose files uploaded directly
        shutil.copytree(
            folder,
            target,
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns("*.zip", "*.rar")
        )

        # ZIP files
        for z in sorted(p for p in folder.rglob("*.zip") if not is_junk(p)):
            try:
                extract_zip(z, target)
            except Exception as e:
                log(f"!! Could not extract {folder.name}/{z.name}: {e}")

        # RAR files
        for r in sorted(p for p in folder.rglob("*.rar") if not is_junk(p)):
            try:
                extract_rar(r, target)
            except Exception as e:
                log(f"!! Could not extract RAR {folder.name}/{r.name}: {e}")

        seen = set()

        for _ in range(3):
            nested_zips = [
                z for z in target.rglob("*.zip")
                if z not in seen and not is_junk(z)
            ]

            nested_rars = [
                r for r in target.rglob("*.rar")
                if r not in seen and not is_junk(r)
            ]

            nested = nested_zips + nested_rars

            if not nested:
                break

            for f in nested:
                seen.add(f)

                try:
                    if f.suffix.lower() == ".zip":
                        extract_zip(f, f.parent / f.stem)

                    elif f.suffix.lower() == ".rar":
                        extract_rar(f, f.parent / f.stem)

                except Exception as e:
                    log(f"!! Could not extract nested archive {folder.name}/{f.name}: {e}")

# ------------------------------------------------------------------ reading
def clean_col(c):
    """Standardize a column name: lowercase, anything that is not a letter/digit -> underscore."""
    c = str(c).strip().lower()
    c = re.sub(r"[^\w]+", "_", c)
    c = re.sub(r"_+", "_", c)
    return c.strip("_")


def standardize_columns(df):
    names = [clean_col(c) for c in df.columns]
    final = []
    for n in names:
        t = CANONICAL.get(n, n)
        if t != n and (t in names or t in final):   # never create a duplicate column name
            t = n
        final.append(t)
    df.columns = final
    return df


def detect_delimiter(first_line):
    for d in (",", ";", "\t", "|"):
        if len(next(csv.reader([first_line], delimiter=d))) > 1:
            return d
    return ","

def detect_header_row(rows):
    """
    Find the most likely header row.
    Looks for common marketplace column names such as item_id, title,
    description, category, age, condition, price, currency, item_photo.
    """
    expected = {
        "item_id",
        "item_photo",
        "title",
        "description",
        "category",
        "age",
        "condition",
        "price",
        "currency"
    }

    best_index = 0
    best_score = -1

    for i, row in enumerate(rows[:15]):
        normalized = [CANONICAL.get(clean_col(x), clean_col(x)) for x in row]

        score = sum(1 for x in normalized if x in expected)

        if score > best_score:
            best_score = score
            best_index = i

    return best_index

def rows_to_df(rows):
    """
    Header + rows -> DataFrame of strings.

    Detects the real header row automatically, then:
    - drops trailing empty fields
    - rejoins extra fields into the description column
    - pads short rows
    - returns (df, note)
    """

    rows = [
        r for r in rows
        if any(str(x).strip() for x in r)
    ]

    if not rows:
        return pd.DataFrame(), None

    # Detect the real header row instead of assuming rows[0]
    header_idx = detect_header_row(rows)
    rows = rows[header_idx:]

    header = [str(h).strip() for h in rows[0]]

    while header and header[-1] == "" and len(header) > 1:
        header.pop()

    n = len(header)

    norm = [clean_col(h) for h in header]

    merge_idx = next(
        (
            norm.index(k)
            for k in ("description", "descreption")
            if k in norm
        ),
        n - 1
    )

    fixed = []
    repaired = 0

    for r in rows[1:]:
        r = [str(x) for x in r]

        while len(r) > n and r[-1].strip() == "":
            r = r[:-1]

        if len(r) > n:
            extra = len(r) - n

            r = (
                r[:merge_idx]
                + [",".join(r[merge_idx:merge_idx + extra + 1])]
                + r[merge_idx + extra + 1:]
            )

            repaired += 1

        elif len(r) < n:
            r = r + [""] * (n - len(r))
            repaired += 1

        fixed.append(r)

    df = pd.DataFrame(fixed, columns=header)

    df = df.replace("", pd.NA)

    note = (
        f"repaired {repaired} row(s) with a wrong number of fields - please check them"
        if repaired
        else None
    )

    return df, note

def read_table(path):
    """Return (DataFrame, note). Cell values are kept exactly as written (as text)."""

    if path.suffix.lower() in EXCEL_EXTS:
        preview = pd.read_excel(
            path,
            header=None,
            dtype=str
        )

        rows = preview.fillna("").astype(str).values.tolist()

        header_idx = detect_header_row(rows)

        df = pd.read_excel(
            path,
            header=header_idx,
            dtype=str
        )

        return df, None

    last = None

    for enc in ENCODINGS:
        try:
            with open(path, encoding=enc, newline="") as fh:
                text = fh.read()

        except UnicodeDecodeError as e:
            last = e
            continue

        if not text.strip():
            return pd.DataFrame(), None

        delim = detect_delimiter(text.splitlines()[0])

        return rows_to_df(
            list(
                csv.reader(
                    text.splitlines(keepends=True),
                    delimiter=delim
                )
            )
        )

    raise last

def find_data_files():
    """
    student_id -> list of usable data files.

    Rules:
    - Ignore junk/macOS files.
    - Ignore source/reference files.
    - Ignore AutoRecovered backup files.
    - Prefer CSV files.
    - Use Excel only when the student has no usable CSV.
    - Avoid reading identical duplicate files twice.
    """

    per = {}

    for f in sorted(EXTRACTED.rglob("*")):

        if not f.is_file() or is_junk(f):
            continue

        sid = f.relative_to(EXTRACTED).parts[0]
        ext = f.suffix.lower()
        name = f.name.lower()

        # Ignore files that are clearly not the actual dataset
        if "source" in name:
            continue

        if "autorecovered" in name:
            continue

        d = per.setdefault(
            sid,
            {
                "csv": [],
                "xls": []
            }
        )

        if ext == ".csv":
            d["csv"].append(f)

        elif ext in EXCEL_EXTS:
            d["xls"].append(f)

    # ---------------------------------------------------------
    # Remove duplicate files with identical contents
    # ---------------------------------------------------------

    for sid, d in per.items():

        for kind in ("csv", "xls"):

            unique_files = []
            seen_signatures = set()

            for f in d[kind]:

                try:
                    if kind == "csv":
                        df, _ = read_table(f)
                    else:
                        df, _ = read_table(f)

                    if df.empty:
                        unique_files.append(f)
                        continue

                    # Standardize column names before comparing
                    df = standardize_columns(df.copy())

                    # Convert everything to strings for stable comparison
                    compare_df = (
                        df.fillna("")
                        .astype(str)
                        .reset_index(drop=True)
                    )

                    # Create a signature representing the full table
                    signature = pd.util.hash_pandas_object(
                        compare_df,
                        index=True
                    ).sum()

                    if signature in seen_signatures:
                        log(
                            f"!! {sid}/{f.name}: ignored duplicate data file"
                        )
                        continue

                    seen_signatures.add(signature)
                    unique_files.append(f)

                except Exception:
                    # If comparison fails, keep the file.
                    # load_student() will handle/report reading errors later.
                    unique_files.append(f)

            d[kind] = unique_files

    return per

# ------------------------------------------------------------------ images
_img_index = {}


def index_student(student):
    """Index every image under the student's own extracted folder (cached)."""
    if student not in _img_index:
        by_name, by_stem = {}, {}
        for f in sorted((EXTRACTED / student).rglob("*")):
            if f.is_file() and f.suffix.lower() in IMAGE_EXTS and not is_junk(f):
                by_name.setdefault(f.name.lower(), f)
                by_stem.setdefault(f.stem.lower(), f)
        _img_index[student] = (by_name, by_stem)
    return _img_index[student]


def norm_val(v):
    """Cell value -> clean string (NaN -> '', 3.0 -> '3')."""
    if pd.isna(v):
        return ""
    s = str(v).strip()
    if re.fullmatch(r"\d+\.0+", s):
        s = s.split(".")[0]
    return s


def image_key(value):
    """Normalize an image reference for matching."""
    if value is None:
        return ""

    s = str(value).strip().replace("\\", "/").lower()

    if not s:
        return ""

    name = PurePosixPath(s).name

    # Remove repeated image extensions:
    # item_200.jpeg.jpeg -> item_200
    changed = True

    while changed:
        changed = False

        for ext in IMAGE_EXTS:
            if name.endswith(ext):
                name = name[:-len(ext)]
                changed = True
                break

    return name.strip()


def normalize_image_token(value):
    if value is None or pd.isna(value):
        return ""

    s = str(value).strip().lower().replace("\\", "/")

    if not s:
        return ""

    s = PurePosixPath(s).name

    # Remove spaces
    s = re.sub(r"\s+", "", s)

    # Remove strange leading symbols
    s = re.sub(r"^[^a-z0-9]+", "", s)

    # Remove repeated extensions
    changed = True
    while changed:
        changed = False
        for ext in IMAGE_EXTS:
            if s.endswith(ext):
                s = s[:-len(ext)]
                changed = True
                break

    # Fix common typo: iten_015 -> item_015
    s = re.sub(r"^iten[_\-]*", "item_", s)

    # Normalize item numbering
    m = re.search(r"item[_\-]?(\d+)", s)

    if m:
        return f"item_{int(m.group(1)):03d}"

    if re.fullmatch(r"\d+", s):
        return f"item_{int(s):03d}"

    return s


def find_image(student, img_ref, fallback_id):
    """
    Find the image using:
    1) exact image filename
    2) normalized image reference
    3) item_id fallback
    """

    by_name, by_stem = index_student(student)

    # Build normalized index once for this student
    normalized_index = {}

    for actual_name, actual_file in by_name.items():
        key = normalize_image_token(actual_name)

        if key and key not in normalized_index:
            normalized_index[key] = actual_file

    candidates = []

    # Only use img_ref if it looks useful
    if img_ref:
        ref = str(img_ref).strip()

        # Generic values like "Picture" are not real filenames
        if ref.lower() not in {
            "picture",
            "photo",
            "image",
            "pic",
            "img"
        }:
            candidates.append(ref)

    # Always try item_id as fallback
    if fallback_id:
        candidates.append(str(fallback_id))

    for value in candidates:
        value = value.replace("\\", "/")

        name = PurePosixPath(value).name.lower()

        # 1) Exact filename
        if name in by_name:
            return by_name[name]

        # 2) Exact stem
        stem = PurePosixPath(value).stem.lower()

        if stem in by_stem:
            return by_stem[stem]

        # 3) Normalized match
        key = normalize_image_token(value)

        if key in normalized_index:
            return normalized_index[key]

            # 4) Folder fallback: e.g. images/item_011/<actual image>
    for value in candidates:
        key = normalize_image_token(value)

        if not key:
            continue

        student_root = EXTRACTED / student

        for folder in student_root.rglob("*"):
            if folder.is_dir() and normalize_image_token(folder.name) == key:

                images_inside = [
                    p for p in folder.rglob("*")
                    if p.is_file()
                    and p.suffix.lower() in IMAGE_EXTS
                    and not is_junk(p)
                ]

                if images_inside:
                    return sorted(images_inside)[0]
        # Special safe fallback for student 1230011:
    # item_015 exists as a screenshot with a non-standard filename.
       # Special safe fallback for student 1230011
    if student == "1230011":
        key = normalize_image_token(fallback_id)

        if key == "item_015":
            student_root = EXTRACTED / student

            all_images = [
                p for p in student_root.rglob("*")
                if p.is_file()
                and p.suffix.lower() in IMAGE_EXTS
                and not is_junk(p)
            ]

            # Standard images item_001 ... item_014
            standard_images = {
                f"item_{i:03d}"
                for i in range(1, 15)
            }

            unusual_images = [
                p for p in all_images
                if normalize_image_token(p.name) not in standard_images
            ]

            # There should be exactly one unusual image:
            # the screenshot that corresponds to item_015
            if len(unusual_images) == 1:
                return unusual_images[0]

    return None
def detect_image_col(cols):
    if "item_photo" in cols:
        return "item_photo"
    for c in cols:
        if c.endswith("_url"):
            continue
        if any(h in c for h in IMG_HINTS):
            return c
    return None


# ------------------------------------------------------------------ main

def load_student(sid, files):
    frames = []

    for f in files:
        try:
            df, note = read_table(f)

        except Exception as e:
            log(f"!! {sid}/{f.name}: could not read ({e})")
            continue

        if df.empty:
            log(f"!! {sid}/{f.name}: empty file")
            continue

        if note:
            log(f"!! {sid}/{f.name}: {note}")

        # Standardize column names
        df = standardize_columns(df)

        # ---------------------------------------------------------
        # Remove metadata / non-item rows
        # ---------------------------------------------------------

        meaningful_cols = [
            c for c in (
                "title",
                "description",
                "category",
                "age",
                "condition",
                "price",
                "currency",
                "item_photo"
            )
            if c in df.columns
        ]

        def has_value(v):
            return pd.notna(v) and str(v).strip() != ""

        keep_rows = []

        for _, row in df.iterrows():

            # If item_id exists and is filled, definitely keep the row
            has_item_id = (
                "item_id" in df.columns
                and has_value(row.get("item_id"))
            )

            # Count how many real marketplace fields contain values
            meaningful_count = sum(
                has_value(row.get(c))
                for c in meaningful_cols
            )

            # Keep:
            # 1) rows with an item_id
            # OR
            # 2) rows without item_id but with enough real item information
            keep_rows.append(
                has_item_id or meaningful_count >= 3
            )

        before = len(df)

        df = df.loc[keep_rows].reset_index(drop=True)

        removed = before - len(df)

        if removed:
            log(
                f"!! {sid}/{f.name}: removed {removed} "
                f"metadata/non-item row(s)"
            )

        if df.empty:
            log(f"!! {sid}/{f.name}: no item rows after filtering")
            continue

        # ---------------------------------------------------------
        # Continue normal processing
        # ---------------------------------------------------------

        cols = list(df.columns)

        img_col = detect_image_col(cols)

        df["_img_ref"] = (
            df[img_col].map(norm_val)
            if img_col
            else ""
        )

        df["_item_ref"] = (
            df["item_id"].map(norm_val)
            if "item_id" in cols
            else ""
        )

        df["student_id"] = sid
        df["source_file"] = f.name

        frames.append(df)

    return frames

def main():
    if not BASE.exists():
        sys.exit(f"Path does not exist: {BASE}")

    OUTPUT.mkdir(exist_ok=True)
    if IMAGES_OUT.exists():
        shutil.rmtree(IMAGES_OUT)               # our own output from a previous run
    IMAGES_OUT.mkdir()

    log("== 1) Extracting zips ==")
    extract_all()

    log("\n== 2) Reading data files ==")
    per = find_data_files()
    multi_submission_ids = {
        "1220064", "1220161", "1220357", "1220782",
        "1221464", "1230049", "1230110", "1230152",
        "1230196", "1230239", "1230500", "1230746",
        "1230922", "1231050"
    }

    log("\n== Multiple Submission Students ==")

    for sid in sorted(multi_submission_ids):
        student_folder = EXTRACTED / sid

        files = [
            f for f in student_folder.rglob("*")
            if f.is_file() and not is_junk(f)
        ]

        log(f"\n{sid}: {len(files)} file(s)")

        for f in files:
            log(f"   {f.relative_to(student_folder)}")
        frames, no_data = [], []
    all_students = sorted(p.name for p in EXTRACTED.iterdir() if p.is_dir())
    for sid in all_students:
        d = per.get(sid, {"csv": [], "xls": []})
        got = load_student(sid, d["csv"])
        if not got and d["xls"]:
            log(f"   {sid}: no usable CSV, using Excel file(s)")
            got = load_student(sid, d["xls"])
        if got:
            frames.extend(got)
        else:
            no_data.append(sid)

    log(f"Students with data: {len(all_students) - len(no_data)} / {len(all_students)}")
    if no_data:
        log(f"Students WITHOUT usable data: {len(no_data)}  -> what is inside their folders:")
        for sid in no_data:
            exts = Counter(p.suffix.lower() or "(none)" for p in (EXTRACTED / sid).rglob("*")
                           if p.is_file() and not is_junk(p))
            log(f"   {sid}: {dict(exts) if exts else 'EMPTY'}")

    log("\n== Column layouts after name standardization ==")
    internal = ("student_id", "source_file", "_img_ref", "_item_ref")
    layouts = Counter(tuple(c for c in df.columns if c not in internal) for df in frames)
    for cols, n in layouts.most_common():
        log(f"{n} files: {list(cols)}")

    raw = pd.concat(frames, ignore_index=True)
    raw = raw.sort_values("student_id", kind="stable").reset_index(drop=True)
    raw.insert(0, "global_id", range(1, len(raw) + 1))


    # ================= Standardize final integration schema =================

    CORE_COLUMNS = [
        "item_id",
        "item_photo",
        "title",
        "description",
        "category",
        "age",
        "condition",
        "price",
        "currency",
    ]

    # Make sure every expected column exists
    for col in CORE_COLUMNS:
        if col not in raw.columns:
            raw[col] = pd.NA

    # Preserve raw values as text.
    # Numeric conversion will be done later during Data Cleaning.
    for col in CORE_COLUMNS:
        raw[col] = raw[col].astype("string")

    raw["student_id"] = raw["student_id"].astype("string")
    raw["source_file"] = raw["source_file"].astype("string")

    log("\n== Integration schema check ==")
    for col in CORE_COLUMNS:
        log(f"{col}: {raw[col].dtype}")

    log("\n== Final Duplicate Report ==")

    global_duplicates = raw["global_id"].duplicated().sum()

    item_id_duplicates = (
        raw["item_id"]
        .dropna()
        .duplicated()
        .sum()
    )

    student_item_duplicates = (
        raw
        .dropna(subset=["item_id"])
        .duplicated(
            subset=["student_id", "item_id"]
        )
        .sum()
    )

    record_cols = [
        c for c in [
            "item_id",
            "item_photo",
            "title",
            "description",
            "category",
            "age",
            "condition",
            "price",
            "currency"
        ]
        if c in raw.columns
    ]

    full_record_duplicates = raw.duplicated(
        subset=record_cols
    ).sum()

    log(f"Duplicate global_id: {global_duplicates}")
    log(f"Duplicate item_id alone: {item_id_duplicates}")
    log(f"Duplicate (student_id + item_id): {student_item_duplicates}")
    log(f"Duplicate full records: {full_record_duplicates}")
    
    log("\n== 3) Linking and copying images ==")
    missing = []
    img_refs = raw["_img_ref"].tolist()
    item_refs = raw["_item_ref"].tolist()
    out_paths = []
    for i, (gid, sid) in enumerate(zip(raw["global_id"], raw["student_id"])):
        src = find_image(sid, img_refs[i], item_refs[i])
        if src is None:
            out_paths.append(pd.NA)
            missing.append((gid, sid, img_refs[i] or f"(empty; item_id={item_refs[i]})"))
            continue
        dst_name = f"{int(gid):04d}_{sid}{src.suffix.lower()}"
        shutil.copy2(src, IMAGES_OUT / dst_name)
        out_paths.append(f"images/{dst_name}")
    raw["image_path"] = out_paths
    log(f"Images linked: {raw['image_path'].notna().sum()} | Missing/not found: {len(missing)}")
    by_student = Counter(m[1] for m in missing)
    for sid, n in by_student.most_common(30):
        log(f"   {sid}: {n} missing")
    pd.DataFrame(missing, columns=["global_id", "student_id", "image_value"]).to_csv(
        OUTPUT / "missing_images.csv", index=False, encoding="utf-8-sig")

    raw = raw.drop(columns=["_img_ref", "_item_ref"])
    first = ["global_id", "student_id", "source_file"]
    raw = raw[first + [c for c in raw.columns if c not in first + ["image_path"]] + ["image_path"]]

    log("\n== 4) Checks ==")
    log(f"global_id is unique: {raw['global_id'].is_unique}")
    if "item_id" in raw.columns:
        log(f"Rows with empty item_id: {raw['item_id'].isna().sum()}")
        log(f"Duplicates (item_id alone): {raw['item_id'].duplicated().sum()}  "
            f"(expected, each student starts numbering from 1)")
        log(f"Duplicates (student_id + item_id, empty ids ignored): "
            f"{raw.dropna(subset=['item_id']).duplicated(['student_id', 'item_id']).sum()}")
    if "category" in raw.columns:
        log(f"Number of categories (before standardization): {raw['category'].nunique()}")
    log(f"Number of observations: {len(raw)}")
    log(f"Number of students: {raw['student_id'].nunique()}")

    log("\n== 5) Final Data Integration Summary ==")

# Data types
    log("\nColumn data types:")
    for col in raw.columns:
     log(f"   {col}: {raw[col].dtype}")

# Category count
    if "category" in raw.columns:
     category_count = raw["category"].nunique(dropna=True)
     log(f"\nNumber of categories: {category_count}")

    log("Category values:")
    for cat, count in raw["category"].value_counts(dropna=False).items():
        log(f"   {cat}: {count}")

# Final counts
    log(f"\nTotal observations: {len(raw)}")
    log(f"Total students: {raw['student_id'].nunique()}")
    


    raw.to_csv(OUTPUT / "marketplace_raw.csv", index=False, encoding="utf-8-sig")

    non_empty = raw[
    raw["item_id"].notna() &
    (raw["item_id"].astype(str).str.strip() != "")
    ].copy()

    duplicate_student_item_ids = non_empty[
    non_empty.duplicated(
        subset=["student_id", "item_id"],
        keep=False
    )
    ].sort_values(["student_id", "item_id"])

    duplicate_student_item_ids.to_csv(
    OUTPUT / "duplicate_student_item_ids.csv",
    index=False,
    encoding="utf-8-sig"
)

    log(
    f"Saved duplicate_student_item_ids.csv: "
    f"{len(duplicate_student_item_ids)} rows"
)


    
     # Extra diagnostic files for Assignment 2

raw_file = OUTPUT / "marketplace_raw.csv"

if raw_file.exists():
    check_df = pd.read_csv(raw_file)

    # 1) Rows with missing/empty item_id
    empty_item_ids = check_df[
        check_df["item_id"].isna() |
        (check_df["item_id"].astype(str).str.strip() == "")
    ]

    empty_item_ids.to_csv(
        OUTPUT / "empty_item_ids.csv",
        index=False
    )

    # 2) Duplicate (student_id + item_id), ignoring empty item_id
    non_empty = check_df[
        check_df["item_id"].notna() &
        (check_df["item_id"].astype(str).str.strip() != "")
    ].copy()

    duplicate_student_item_ids = non_empty[
        non_empty.duplicated(
            subset=["student_id", "item_id"],
            keep=False
        )
    ].sort_values(["student_id", "item_id"])

    duplicate_student_item_ids.to_csv(
        OUTPUT / "duplicate_student_item_ids.csv",
        index=False
    )

    print(f"Saved empty_item_ids.csv: {len(empty_item_ids)} rows")
    print(f"Saved duplicate_student_item_ids.csv: {len(duplicate_student_item_ids)} rows")


    (OUTPUT / "merge_report.txt").write_text("\n".join(report), encoding="utf-8")
    log(f"\nDone. Files are in: {OUTPUT}")

    

   
if __name__ == "__main__":
    main()
