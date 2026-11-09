طريقة التشغيل
=============
1) فكي الضغط عن هالفولدر.
2) افتحي merge_data.py وتأكدي من DEFAULT_BASE (مسار فولدر compressed-attachments).
3) دبل كليك على run_merge.bat   (أو: python merge_data.py)

النتائج (فولدر output):
- marketplace_raw.csv  : الداتا المدموجة + global_id + student_id + image_path + source_file
- images/              : كل الصور مرقّمة (0001_<student>.jpg ...)
- merge_report.txt     : تقرير الدمج (أعمدة مختلفة، صور ناقصة، عدد الطلاب...)
- missing_images.csv   : الأغراض اللي ما انلقت صورتها

ملاحظة: القيم الأصلية ما بتتعدّل. بنوحّد أسماء الأعمدة بس (حروف صغيرة + underscore).
