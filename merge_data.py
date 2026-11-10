# """
# Assignment 2 (ENCS5341) - Data Integration
# ------------------------------------------
# 1) Extracts every student's zip file (one folder per student)
# 2) Reads every CSV and standardizes column NAMES only (lowercase + underscores);
#    the values themselves are never modified
# 3) Adds new tracking columns: global_id (unified numbering 1..N), student_id, image_path
# 4) Copies all images into one folder with unique names (global_id + student_id),
#    so that "1.jpg" from different students does not collide
# 5) Saves marketplace_raw.csv + merge_report.txt

# Usage:
#     python merge_data.py
#     or:  python merge_data.py "C:\\path\\to\\compressed-attachments"

# Requirements: Python 3.8+ and pandas  (pip install pandas)
# """
# import re
# import shutil
# import sys
# import zipfile
# from collections import Counter
# from pathlib import Path

# import pandas as pd

# # ============================ Settings (edit if needed) ============================
# DEFAULT_BASE = r"C:\Users\Dell\Downloads\compressed-attachments-from-6084002\compressed-attachments"
# BASE = Path(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_BASE)

# HERE = Path(__file__).resolve().parent
# EXTRACTED = HERE / "extracted"          # zips are extracted here (originals are never touched)
# OUTPUT = HERE / "output"                # results
# IMAGES_OUT = OUTPUT / "images"          # all images together, with unique names

# IMG_COL_HINTS = ("image", "img", "photo", "pic", "picture", "صورة")
# IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".jfif"}
# # ===================================================================================

# report = []


# def log(msg=""):
#     """Print a message and keep it for merge_report.txt."""
#     print(msg)
#     report.append(str(msg))


# def read_csv_any(path):
#     """Try several encodings. Values are not modified; pandas only infers dtypes."""
#     last = None
#     for enc in ("utf-8-sig", "cp1256", "cp1252", "latin-1"):
#         try:
#             return pd.read_csv(path, encoding=enc, sep=None, engine="python")
#         except UnicodeDecodeError as e:
#             last = e
#         except pd.errors.EmptyDataError:
#             return pd.DataFrame()
#     raise last


# def clean_col(c):
#     """Standardize a column name: strip, lowercase, spaces/hyphens -> underscore."""
#     c = str(c).strip().lower()
#     c = re.sub(r"[\s\-]+", "_", c)
#     return c


# def extract_all():
#     """Extract each student's zip(s) into extracted/<student_id>/."""
#     EXTRACTED.mkdir(exist_ok=True)
#     folders = sorted(p for p in BASE.iterdir() if p.is_dir())
#     log(f"Number of student folders: {len(folders)}")
#     for folder in folders:
#         target = EXTRACTED / folder.name
#         zips = list(folder.rglob("*.zip"))
#         if not zips:
#             # The student may have uploaded the files without a zip: copy them as-is
#             if not target.exists():
#                 shutil.copytree(folder, target)
#             continue
#         target.mkdir(exist_ok=True)
#         for z in zips:
#             try:
#                 with zipfile.ZipFile(z) as zf:
#                     zf.extractall(target)
#             except zipfile.BadZipFile:
#                 log(f"!! Corrupted zip file: {folder.name}/{z.name}")


# def find_images_dir(csv_path):
#     """Nearest folder named 'images'; otherwise the CSV's own folder."""
#     for d in [csv_path.parent, *csv_path.parent.parents]:
#         if d == EXTRACTED.parent:
#             break
#         for sub in d.iterdir():
#             if sub.is_dir() and sub.name.lower() == "images":
#                 return sub
#         if d.parent == EXTRACTED:
#             break
#     return csv_path.parent


# _dir_cache = {}


# def index_dir(d):
#     """Index the images in a folder by file name and by stem (cached)."""
#     if d not in _dir_cache:
#         by_name, by_stem = {}, {}
#         for f in d.rglob("*"):
#             if f.is_file() and f.suffix.lower() in IMAGE_EXTS:
#                 by_name.setdefault(f.name.lower(), f)
#                 by_stem.setdefault(f.stem.lower(), f)
#         _dir_cache[d] = (by_name, by_stem)
#     return _dir_cache[d]


# def norm_val(v):
#     """Turn a cell value into a clean string (NaN -> '', 3.0 -> '3')."""
#     if pd.isna(v):
#         return ""
#     s = str(v).strip()
#     if re.fullmatch(r"\d+\.0+", s):      # 3.0 -> 3
#         s = s.split(".")[0]
#     return s


# def find_image(row, img_dir, img_col, id_col):
#     """Return the image file for a row, or None if it cannot be found."""
#     by_name, by_stem = index_dir(img_dir)
#     # Rely on the image column. Fall back to item_id only when the image column is
#     # empty (so we never silently link a wrong image when the listed image is missing).
#     candidates = []
#     img_val = norm_val(row[img_col]) if img_col else ""
#     if img_val:
#         candidates.append(img_val)
#     elif id_col:
#         candidates.append(norm_val(row[id_col]))
#     for v in candidates:
#         if not v:
#             continue
#         name = Path(v).name.lower()
#         if name in by_name:
#             return by_name[name]
#         stem = Path(v).stem.lower()
#         if stem in by_stem:
#             return by_stem[stem]
#     return None


# def main():
#     if not BASE.exists():
#         sys.exit(f"Path does not exist: {BASE}")

#     OUTPUT.mkdir(exist_ok=True)
#     IMAGES_OUT.mkdir(exist_ok=True)

#     log("== 1) Extracting zips ==")
#     extract_all()

#     csv_files = sorted(EXTRACTED.rglob("*.csv"))
#     log(f"\n== 2) Reading CSV files ({len(csv_files)} files) ==")

#     frames, problems = [], []
#     for f in csv_files:
#         student = f.relative_to(EXTRACTED).parts[0]
#         try:
#             df = read_csv_any(f)
#         except Exception as e:
#             problems.append((student, f.name, str(e)))
#             continue
#         if df.empty:
#             problems.append((student, f.name, "empty file"))
#             continue
#         df.columns = [clean_col(c) for c in df.columns]
#         df["student_id"] = student
#         df["_img_dir"] = str(find_images_dir(f))
#         df["_source_file"] = f.name
#         frames.append(df)

#     students_with_csv = {df["student_id"].iloc[0] for df in frames}
#     all_students = {p.name for p in EXTRACTED.iterdir() if p.is_dir()}
#     no_csv = sorted(all_students - students_with_csv)
#     log(f"Students without a valid CSV: {no_csv if no_csv else 'none'}")
#     for p in problems:
#         log(f"!! Problem: {p}")

#     # Compare column layouts across students
#     log("\n== Different column layouts across students ==")
#     col_sets = Counter(
#         tuple(c for c in df.columns if c not in ("student_id", "_img_dir", "_source_file"))
#         for df in frames
#     )
#     for cols, n in col_sets.most_common():
#         log(f"{n} files: {list(cols)}")

#     raw = pd.concat(frames, ignore_index=True)

#     # Unified numbering
#     raw = raw.sort_values("student_id", kind="stable").reset_index(drop=True)
#     raw.insert(0, "global_id", range(1, len(raw) + 1))

#     # Detect the image column and the item-id column
#     img_col = next((c for c in raw.columns if any(h in c for h in IMG_COL_HINTS)
#                     and c not in ("image_path",)), None)
#     id_col = "item_id" if "item_id" in raw.columns else next(
#         (c for c in raw.columns if c in ("id", "item", "itemid")), None)
#     log(f"\nDetected image column: {img_col} | Detected ID column: {id_col}")

#     log("\n== 3) Linking and copying images ==")
#     paths, missing = [], []
#     for _, row in raw.iterrows():
#         src = find_image(row, Path(row["_img_dir"]), img_col, id_col)
#         if src is None:
#             paths.append(pd.NA)
#             missing.append((row["global_id"], row["student_id"],
#                             row[img_col] if img_col else None))
#             continue
#         dst_name = f"{int(row['global_id']):04d}_{row['student_id']}{src.suffix.lower()}"
#         shutil.copy2(src, IMAGES_OUT / dst_name)
#         paths.append(f"images/{dst_name}")
#     raw["image_path"] = paths
#     log(f"Images linked: {raw['image_path'].notna().sum()} | Missing/not found: {len(missing)}")
#     for m in missing[:30]:
#         log(f"   Missing -> global_id={m[0]}, student={m[1]}, column_value={m[2]}")
#     if len(missing) > 30:
#         log(f"   ... and {len(missing) - 30} more (see missing_images.csv)")
#     pd.DataFrame(missing, columns=["global_id", "student_id", "image_value"]).to_csv(
#         OUTPUT / "missing_images.csv", index=False, encoding="utf-8-sig")

#     raw = raw.drop(columns=["_img_dir"]).rename(columns={"_source_file": "source_file"})

#     log("\n== 4) Checks ==")
#     log(f"global_id is unique: {raw['global_id'].is_unique}")
#     if id_col:
#         log(f"Duplicates ({id_col} alone): {raw[id_col].duplicated().sum()}  "
#             f"(expected, each student starts numbering from 1)")
#         log(f"Duplicates (student_id + {id_col}): "
#             f"{raw.duplicated(['student_id', id_col]).sum()}")
#     if "category" in raw.columns:
#         log(f"Number of categories (before standardization): {raw['category'].nunique()}")
#     log(f"Number of observations: {len(raw)}")
#     log(f"Number of students: {raw['student_id'].nunique()}")

#     raw.to_csv(OUTPUT / "marketplace_raw.csv", index=False, encoding="utf-8-sig")
#     (OUTPUT / "merge_report.txt").write_text("\n".join(report), encoding="utf-8")
#     log(f"\nDone. Files are in: {OUTPUT}")


# if __name__ == "__main__":
#     main()
# #///////////////////////////////////////////

# import re
# import shutil
# import sys
# import subprocess
# from pathlib import Path
# from collections import Counter

# import pandas as pd


# # ============================================================
# # 1. SETTINGS
# # ============================================================

# DEFAULT_BASE = (
#     r"C:\Users\Dell\Downloads\compressed-attachments-from-6084002"
#     r"\compressed-attachments"
# )

# BASE = Path(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_BASE)

# HERE = Path(__file__).resolve().parent

# EXTRACTED = HERE / "extracted"
# OUTPUT = HERE / "output"
# IMAGES_OUT = OUTPUT / "images"

# ARCHIVE_EXTS = {".zip", ".rar", ".7z"}

# IMAGE_EXTS = {
#     ".jpg", ".jpeg", ".png", ".webp",
#     ".bmp", ".gif", ".jfif"
# }

# IMG_COL_HINTS = (
#     "image", "img", "photo", "pic",
#     "picture", "صورة"
# )

# INTERNAL_COLS = {
#     "global_id",
#     "student_id",
#     "image_path",
#     "_img_dir",
#     "_source_file",
#     "_image_value",
#     "_id_value"
# }

# report = []


# # ============================================================
# # 2. LOGGING
# # ============================================================

# def log(msg=""):
#     print(msg)
#     report.append(str(msg))


# # ============================================================
# # 3. FIND 7-ZIP
# # ============================================================

# def find_7zip():

#     possible_paths = [
#         Path(r"C:\Program Files\7-Zip\7z.exe"),
#         Path(r"C:\Program Files (x86)\7-Zip\7z.exe")
#     ]

#     found = shutil.which("7z")

#     if found:
#         return found

#     for path in possible_paths:
#         if path.exists():
#             return str(path)

#     raise FileNotFoundError(
#         "7-Zip was not found. Install it from https://www.7-zip.org/"
#     )


# SEVEN_ZIP = None


# # ============================================================
# # 4. EXTRACT ZIP / RAR / 7Z
# # ============================================================

# def safe_extract(archive_file, destination):

#     archive_file = Path(archive_file)
#     destination = Path(destination)

#     destination.mkdir(parents=True, exist_ok=True)

#     result = subprocess.run(
#         [
#             SEVEN_ZIP,
#             "x",
#             str(archive_file),
#             f"-o{destination}",
#             "-y"
#         ],
#         capture_output=True,
#         text=True
#     )

#     if result.returncode >= 2:

#         raise RuntimeError(
#             f"Extraction failed: {archive_file}\n"
#             f"{result.stdout}\n{result.stderr}"
#         )

#     if result.returncode == 1:

#         log(f"Warning during extraction: {archive_file}")

#     return True


# # ============================================================
# # 5. ARCHIVE HELPERS
# # ============================================================

# def is_archive(path):

#     return (
#         path.is_file()
#         and path.suffix.lower() in ARCHIVE_EXTS
#         and not path.name.startswith("._")
#     )


# def get_student_id(filename):

#     stem = Path(filename).stem

#     match = re.search(r"(\d+)$", stem)

#     if match:
#         return match.group(1)

#     return stem


# def ignore_archives(directory, names):

#     ignored = []

#     for name in names:

#         path = Path(directory) / name

#         if is_archive(path):
#             ignored.append(name)

#     return ignored


# # ============================================================
# # 6. EXTRACT ALL STUDENTS
# # ============================================================

# def extract_all():

#     if EXTRACTED.exists():
#         shutil.rmtree(EXTRACTED)

#     EXTRACTED.mkdir(parents=True)

#     folders = sorted(
#         p for p in BASE.iterdir()
#         if p.is_dir()
#     )

#     log(f"Student folders found: {len(folders)}")

#     # --------------------------------------------------------
#     # A. Copy existing student folders
#     # --------------------------------------------------------

#     for folder in folders:

#         target = EXTRACTED / folder.name

#         shutil.copytree(
#             folder,
#             target,
#             dirs_exist_ok=True,
#             ignore=ignore_archives
#         )

#     # --------------------------------------------------------
#     # B. Extract archives inside student folders
#     # --------------------------------------------------------

#     for folder in folders:

#         target = EXTRACTED / folder.name

#         archives = sorted(
#             f for f in folder.rglob("*")
#             if is_archive(f)
#         )

#         log(f"\nStudent: {folder.name}")
#         log(f"Archives found inside folder: {len(archives)}")

#         for archive in archives:

#             try:

#                 safe_extract(archive, target)

#                 log(f"Extracted: {archive.name}")

#             except Exception as e:

#                 log(f"!! Extraction error: {archive} -> {e}")

#     # --------------------------------------------------------
#     # C. Extract archives directly inside BASE
#     # --------------------------------------------------------

#     root_archives = sorted(
#         f for f in BASE.iterdir()
#         if is_archive(f)
#     )

#     log(f"\nArchives in main folder: {len(root_archives)}")

#     for archive in root_archives:

#         student = get_student_id(archive.name)

#         target = EXTRACTED / student

#         target.mkdir(parents=True, exist_ok=True)

#         try:

#             safe_extract(archive, target)

#             log(
#                 f"Root archive extracted: {archive.name} "
#                 f"-> Student: {student}"
#             )

#         except Exception as e:

#             log(f"!! Root archive error: {archive.name} -> {e}")

#     # --------------------------------------------------------
#     # D. Direct CSV files in BASE
#     # --------------------------------------------------------

#     root_csvs = sorted(
#         f for f in BASE.iterdir()
#         if f.is_file()
#         and f.suffix.lower() == ".csv"
#         and not f.name.startswith("._")
#     )

#     if root_csvs:

#         target = EXTRACTED / "root_upload"

#         target.mkdir(parents=True, exist_ok=True)

#         for f in root_csvs:

#             shutil.copy2(f, target / f.name)

#         log(f"Direct CSV files copied: {len(root_csvs)}")


# # ============================================================
# # 7. MAC FILE DETECTION
# # ============================================================

# def is_appledouble(path):

#     try:

#         with open(path, "rb") as f:

#             signature = f.read(4)

#         return signature == b"\x00\x05\x16\x07"

#     except OSError:

#         return False


# # ============================================================
# # 8. READ CSV FILES
# # ============================================================

# def read_csv_any(path):

#     if path.name.startswith("._") or is_appledouble(path):

#         raise ValueError(
#             "AppleDouble metadata file, not an actual CSV dataset"
#         )

#     last_error = None

#     for encoding in (
#         "utf-8-sig",
#         "utf-8",
#         "cp1256",
#         "cp1252",
#         "latin-1"
#     ):

#         try:

#             return pd.read_csv(
#                 path,
#                 encoding=encoding,
#                 sep=None,
#                 engine="python",
#                 dtype=str,
#                 keep_default_na=False
#             )

#         except pd.errors.EmptyDataError:

#             return pd.DataFrame()

#         except (
#             UnicodeDecodeError,
#             pd.errors.ParserError
#         ) as e:

#             last_error = e

#     raise last_error


# # ============================================================
# # 9. STANDARDIZE COLUMN NAMES
# # ============================================================

# def clean_col(col):

#     col = str(col).strip().lower()

#     col = re.sub(r"[\s\-]+", "_", col)

#     col = re.sub(r"_+", "_", col)

#     return col.strip("_")


# def make_unique_columns(columns):

#     result = []
#     counts = {}

#     for col in columns:

#         name = clean_col(col)

#         if name not in counts:

#             counts[name] = 0
#             result.append(name)

#         else:

#             counts[name] += 1

#             new_name = f"{name}_{counts[name]}"

#             while new_name in counts:

#                 counts[name] += 1
#                 new_name = f"{name}_{counts[name]}"

#             counts[new_name] = 0

#             result.append(new_name)

#     return result


# # ============================================================
# # 10. DETECT IMAGE COLUMN
# # ============================================================

# def detect_image_column(columns):

#     candidates = []

#     for col in columns:

#         if col in INTERNAL_COLS:
#             continue

#         name = col.lower()

#         score = 0

#         if name in ("image", "image_name", "image_file"):

#             score = 100

#         elif name in ("photo", "photo_name", "picture"):

#             score = 90

#         elif "image" in name:

#             score = 80

#         elif "photo" in name or "picture" in name:

#             score = 70

#         elif name in ("img", "img_name", "img_file"):

#             score = 60

#         elif name in ("pic", "pic_name"):

#             score = 50

#         elif "صورة" in name:

#             score = 40

#         if score > 0:

#             candidates.append((score, col))

#     if not candidates:
#         return None

#     candidates.sort(reverse=True)

#     return candidates[0][1]


# # ============================================================
# # 11. DETECT ITEM ID COLUMN
# # ============================================================

# def detect_id_column(columns):

#     preferred = (
#         "item_id",
#         "itemid",
#         "id",
#         "item"
#     )

#     for name in preferred:

#         if name in columns:
#             return name

#     return None


# # ============================================================
# # 12. FIND STUDENT ROOT
# # ============================================================

# def find_student_root(csv_path):

#     relative = csv_path.relative_to(EXTRACTED)

#     student = relative.parts[0]

#     return EXTRACTED / student


# # ============================================================
# # 13. INDEX IMAGES
# # ============================================================

# _dir_cache = {}


# def index_dir(directory):

#     directory = Path(directory)

#     if directory not in _dir_cache:

#         by_name = {}
#         by_stem = {}

#         for f in directory.rglob("*"):

#             if not f.is_file():
#                 continue

#             if f.name.startswith("._"):
#                 continue

#             if f.suffix.lower() not in IMAGE_EXTS:
#                 continue

#             by_name.setdefault(f.name.lower(), f)

#             by_stem.setdefault(f.stem.lower(), f)

#         _dir_cache[directory] = (
#             by_name,
#             by_stem
#         )

#     return _dir_cache[directory]


# # ============================================================
# # 14. NORMALIZE VALUES FOR IMAGE MATCHING ONLY
# # ============================================================

# def norm_val(value):

#     if value is None:
#         return ""

#     value = str(value).strip()

#     if value.lower() in ("nan", "none"):
#         return ""

#     if re.fullmatch(r"\d+\.0+", value):

#         value = value.split(".")[0]

#     return value


# # ============================================================
# # 15. FIND IMAGE FOR EACH ROW
# # ============================================================

# def find_image(row):

#     student_root = Path(row["_img_dir"])

#     by_name, by_stem = index_dir(student_root)

#     candidates = []

#     image_value = norm_val(row["_image_value"])

#     id_value = norm_val(row["_id_value"])

#     if image_value:

#         candidates.append(image_value)

#     elif id_value:

#         candidates.append(id_value)

#     for value in candidates:

#         value = value.replace("\\", "/")

#         name = Path(value).name.lower()

#         if name in by_name:

#             return by_name[name]

#         stem = Path(name).stem.lower()

#         if stem in by_stem:

#             return by_stem[stem]

#     return None


# # ============================================================
# # 16. MAIN
# # ============================================================

# def main():

#     global SEVEN_ZIP

#     if not BASE.exists():

#         sys.exit(f"Path does not exist: {BASE}")

#     if not BASE.is_dir():

#         sys.exit(f"BASE must be a folder: {BASE}")

#     SEVEN_ZIP = find_7zip()

#     log("=" * 60)
#     log("ASSIGNMENT 2 - DATA INTEGRATION")
#     log("=" * 60)

#     log(f"Input folder: {BASE}")
#     log(f"7-Zip executable: {SEVEN_ZIP}")

#     # --------------------------------------------------------
#     # STEP 1: EXTRACT ARCHIVES
#     # --------------------------------------------------------

#     log("\n== STEP 1: Extracting student files ==")

#     extract_all()

#     # --------------------------------------------------------
#     # STEP 2: FIND CSV FILES
#     # --------------------------------------------------------

#     csv_files = sorted(
#         f for f in EXTRACTED.rglob("*")
#         if f.is_file()
#         and f.suffix.lower() == ".csv"
#     )

#     log(f"\n== STEP 2: CSV files found: {len(csv_files)} ==")

#     frames = []
#     problems = []

#     students_with_csv = set()

#     # --------------------------------------------------------
#     # STEP 3: READ CSV FILES
#     # --------------------------------------------------------

#     for f in csv_files:

#         student = f.relative_to(EXTRACTED).parts[0]

#         try:

#             df = read_csv_any(f)

#             if df.empty:

#                 problems.append(
#                     (student, str(f), "Empty CSV")
#                 )

#                 continue

#             df.columns = make_unique_columns(df.columns)

#             # Detect columns before adding internal columns.

#             img_col = detect_image_column(df.columns)

#             id_col = detect_id_column(df.columns)

#             # Save image and ID values separately.

#             if img_col:

#                 df["_image_value"] = df[img_col].apply(norm_val)

#             else:

#                 df["_image_value"] = ""

#             if id_col:

#                 df["_id_value"] = df[id_col].apply(norm_val)

#             else:

#                 df["_id_value"] = ""

#             # Tracking columns.

#             df["student_id"] = student

#             df["_img_dir"] = str(find_student_root(f))

#             df["_source_file"] = f.name

#             frames.append(df)

#             students_with_csv.add(student)

#             log(
#                 f"Read successfully: {student} / {f.name} "
#                 f"| Rows: {len(df)} "
#                 f"| Image column: {img_col}"
#             )

#         except Exception as e:

#             problems.append(
#                 (student, str(f), str(e))
#             )

#             log(f"!! Could not read: {f} -> {e}")

#     # --------------------------------------------------------
#     # STEP 4: STUDENT REPORT
#     # --------------------------------------------------------

#     all_students = {
#         p.name for p in EXTRACTED.iterdir()
#         if p.is_dir()
#     }

#     no_csv = sorted(
#         all_students - students_with_csv
#     )

#     log("\n== STEP 4: STUDENT REPORT ==")

#     log(f"Total student folders: {len(all_students)}")

#     log(f"Students with valid CSV: {len(students_with_csv)}")

#     log(f"Students without valid CSV: {len(no_csv)}")

#     log(f"Students without CSV: {no_csv}")

#     log(f"CSV reading problems: {len(problems)}")

#     for problem in problems:

#         log(f"Problem: {problem}")

#     # --------------------------------------------------------
#     # STEP 5: COLUMN LAYOUT REPORT
#     # --------------------------------------------------------

#     log("\n== STEP 5: DIFFERENT COLUMN LAYOUTS ==")

#     col_sets = Counter()

#     for df in frames:

#         cols = tuple(
#             c for c in df.columns
#             if c not in INTERNAL_COLS
#         )

#         col_sets[cols] += 1

#     log(f"Different layouts: {len(col_sets)}")

#     for cols, count in col_sets.most_common():

#         log(f"{count} files: {list(cols)}")

#     # --------------------------------------------------------
#     # STEP 6: MERGE DATA
#     # --------------------------------------------------------

#     log("\n== STEP 6: MERGING DATA ==")

#     if not frames:

#         log("!! No valid CSV files were found.")

#         return

#     raw = pd.concat(
#         frames,
#         ignore_index=True,
#         sort=False
#     )

#     raw = raw.sort_values(
#         "student_id",
#         kind="stable"
#     ).reset_index(drop=True)

#     raw.insert(
#         0,
#         "global_id",
#         range(1, len(raw) + 1)
#     )

#     log(f"Total observations: {len(raw)}")

#     # --------------------------------------------------------
#     # STEP 7: LINK AND COPY IMAGES
#     # --------------------------------------------------------

#     log("\n== STEP 7: LINKING AND COPYING IMAGES ==")

#     if OUTPUT.exists():

#         shutil.rmtree(OUTPUT)

#     OUTPUT.mkdir(parents=True)

#     IMAGES_OUT.mkdir(parents=True)

#     paths = []

#     missing = []

#     for _, row in raw.iterrows():

#         src = find_image(row)

#         if src is None:

#             paths.append("")

#             missing.append({
#                 "global_id": row["global_id"],
#                 "student_id": row["student_id"],
#                 "image_value": row["_image_value"],
#                 "item_id": row["_id_value"],
#                 "source_file": row["_source_file"]
#             })

#             continue

#         dst_name = (
#             f"{int(row['global_id']):04d}_"
#             f"{row['student_id']}"
#             f"{src.suffix.lower()}"
#         )

#         dst = IMAGES_OUT / dst_name

#         shutil.copy2(src, dst)

#         paths.append(f"images/{dst_name}")

#     raw["image_path"] = paths

#     linked = sum(
#         1 for p in paths if p
#     )

#     log(f"Images linked: {linked}")

#     log(f"Images missing: {len(missing)}")

#     # Save missing images report.

#     missing_df = pd.DataFrame(
#         missing,
#         columns=[
#             "global_id",
#             "student_id",
#             "image_value",
#             "item_id",
#             "source_file"
#         ]
#     )

#     missing_df.to_csv(
#         OUTPUT / "missing_images.csv",
#         index=False,
#         encoding="utf-8-sig"
#     )

#     # --------------------------------------------------------
#     # STEP 8: CLEAN INTERNAL COLUMNS
#     # --------------------------------------------------------

#     raw = raw.drop(
#         columns=[
#             "_img_dir",
#             "_image_value",
#             "_id_value"
#         ],
#         errors="ignore"
#     )

#     raw = raw.rename(
#         columns={
#             "_source_file": "source_file"
#         }
#     )

#     # --------------------------------------------------------
#     # STEP 9: DATA VALIDATION
#     # --------------------------------------------------------

#     log("\n== STEP 9: DATA VALIDATION ==")

#     log(
#         f"global_id is unique: "
#         f"{raw['global_id'].is_unique}"
#     )

#     if "item_id" in raw.columns:

#         log(
#             f"Duplicate item_id values: "
#             f"{raw['item_id'].duplicated().sum()}"
#         )

#         log(
#             f"Duplicate student_id + item_id: "
#             f"{raw.duplicated(['student_id', 'item_id']).sum()}"
#         )

#     log(f"Total observations: {len(raw)}")

#     log(f"Total students: {raw['student_id'].nunique()}")

#     log(f"Total linked images: {linked}")

#     log(f"Total missing images: {len(missing)}")

#     log(f"Final columns: {len(raw.columns)}")

#     # --------------------------------------------------------
#     # STEP 10: SAVE FINAL DATASET
#     # --------------------------------------------------------

#     raw.to_csv(
#         OUTPUT / "marketplace_raw.csv",
#         index=False,
#         encoding="utf-8-sig"
#     )

#     log("\n" + "=" * 60)

#     log("DATA INTEGRATION COMPLETED")

#     log(f"Output folder: {OUTPUT}")

#     log("=" * 60)

#     (OUTPUT / "merge_report.txt").write_text(
#         "\n".join(report),
#         encoding="utf-8"
#     )


# # ============================================================
# # 17. RUN
# # ============================================================

# if __name__ == "__main__":

#     try:

#         main()

#     except Exception as e:

#         log(f"\nFATAL ERROR: {e}")

#         if OUTPUT.exists():

#             (OUTPUT / "merge_report.txt").write_text(
#                 "\n".join(report),
#                 encoding="utf-8"
#             )

#         raise
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
import csv
import re
import shutil
import sys
import zipfile
from collections import Counter
from pathlib import Path, PurePosixPath

import pandas as pd

# ============================ Settings (edit if needed) ============================
DEFAULT_BASE = r"C:\Users\Dell\Downloads\compressed-attachments-from-6084002\compressed-attachments"
BASE = Path(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_BASE)

HERE = Path(__file__).resolve().parent
EXTRACTED = HERE / "extracted"          # zips are extracted here (originals are never touched)
OUTPUT = HERE / "output"                # results (re-created on every run)
IMAGES_OUT = OUTPUT / "images"          # all images together, with unique names

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".jfif", ".heic", ".tif", ".tiff"}
EXCEL_EXTS = {".xlsx", ".xlsm", ".xls"}
ENCODINGS = ("utf-8-sig", "cp1256", "cp1252", "latin-1")
IMG_HINTS = ("image", "img", "photo", "pic", "صورة")

# Exact (normalized) column-name variants -> one standard name. Names only, never values.
CANONICAL = {
    "id": "item_id",
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


def extract_all():
    """Extract each student's zip(s) into extracted/<student_id>/ (nested zips too)."""
    EXTRACTED.mkdir(exist_ok=True)
    folders = sorted(p for p in BASE.iterdir() if p.is_dir())
    log(f"Number of student folders: {len(folders)}")
    for folder in folders:
        target = EXTRACTED / folder.name
        target.mkdir(exist_ok=True)
        # loose (non-zip) files the student may have uploaded directly
        shutil.copytree(folder, target, dirs_exist_ok=True, ignore=shutil.ignore_patterns("*.zip"))
        for z in sorted(p for p in folder.rglob("*.zip") if not is_junk(p)):
            try:
                extract_zip(z, target)
            except Exception as e:
                log(f"!! Could not extract {folder.name}/{z.name}: {e}")
        seen = set()
        for _ in range(3):                      # zips inside zips
            nested = [z for z in target.rglob("*.zip") if z not in seen and not is_junk(z)]
            if not nested:
                break
            for z in nested:
                seen.add(z)
                try:
                    extract_zip(z, z.parent / z.stem)
                except Exception as e:
                    log(f"!! Could not extract nested zip {folder.name}/{z.name}: {e}")


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


def rows_to_df(rows):
    """Header + rows -> DataFrame of strings. Rows with the wrong number of fields are fixed:
    trailing empty fields are dropped; other extra fields are re-joined into the
    'description' column (or the last column); short rows are padded. Returns (df, note)."""
    rows = [r for r in rows if any(x.strip() for x in r)]
    if not rows:
        return pd.DataFrame(), None
    header = [h.strip() for h in rows[0]]
    while header and header[-1] == "" and len(header) > 1:
        header.pop()
    n = len(header)
    norm = [clean_col(h) for h in header]
    merge_idx = next((norm.index(k) for k in ("description", "descreption") if k in norm), n - 1)
    fixed, repaired = [], 0
    for r in rows[1:]:
        while len(r) > n and r[-1].strip() == "":
            r = r[:-1]
        if len(r) > n:
            extra = len(r) - n
            r = r[:merge_idx] + [",".join(r[merge_idx:merge_idx + extra + 1])] + r[merge_idx + extra + 1:]
            repaired += 1
        elif len(r) < n:
            r = r + [""] * (n - len(r))
            repaired += 1
        fixed.append(r)
    df = pd.DataFrame(fixed, columns=header)
    df = df.replace("", pd.NA)                      # an empty cell is a missing value
    note = f"repaired {repaired} row(s) with a wrong number of fields - please check them" if repaired else None
    return df, note


def read_table(path):
    """Return (DataFrame, note). Cell values are kept exactly as written (as text)."""
    if path.suffix.lower() in EXCEL_EXTS:
        return pd.read_excel(path), None
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
        return rows_to_df(list(csv.reader(text.splitlines(keepends=True), delimiter=delim)))
    raise last


def find_data_files():
    """student_id -> list of data files (CSVs; Excel only when the student has no CSV)."""
    per = {}
    for f in sorted(EXTRACTED.rglob("*")):
        if not f.is_file() or is_junk(f):
            continue
        sid = f.relative_to(EXTRACTED).parts[0]
        ext = f.suffix.lower()
        d = per.setdefault(sid, {"csv": [], "xls": []})
        if ext == ".csv":
            d["csv"].append(f)
        elif ext in EXCEL_EXTS:
            d["xls"].append(f)
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


def find_image(student, img_ref, fallback_id):
    """Look up the image by the value in the image column. Only when that cell is
    empty do we fall back to item_id (so a wrong image is never linked silently)."""
    by_name, by_stem = index_student(student)
    v = img_ref if img_ref else fallback_id
    if not v:
        return None
    v = v.replace("\\", "/")
    name = PurePosixPath(v).name.lower()
    if name in by_name:
        return by_name[name]
    stem = PurePosixPath(v).stem.lower()
    return by_stem.get(stem)


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
        df = standardize_columns(df)
        cols = list(df.columns)
        img_col = detect_image_col(cols)
        df["_img_ref"] = df[img_col].map(norm_val) if img_col else ""
        df["_item_ref"] = df["item_id"].map(norm_val) if "item_id" in cols else ""
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

    raw.to_csv(OUTPUT / "marketplace_raw.csv", index=False, encoding="utf-8-sig")
    (OUTPUT / "merge_report.txt").write_text("\n".join(report), encoding="utf-8")
    log(f"\nDone. Files are in: {OUTPUT}")


if __name__ == "__main__":
    main()
