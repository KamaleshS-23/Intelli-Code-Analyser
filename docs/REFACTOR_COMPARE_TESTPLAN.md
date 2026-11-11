# Refactor and Comparison Test Plan

1. Upload a Java project ZIP; confirm scanning completes.
2. Confirm the detected stack is `java`.
3. Confirm Code Smells and Third-Party Dependencies tabs still work.
4. Open **Generate Optimized Code**; verify every issue is listed.
5. Test **Select All** and **Clear Selection**.
6. Select 2-5 issues and generate optimized code.
7. Confirm generated files are listed and download the ZIP; verify its project structure.
8. Confirm **Comparison** shows before/after scores and improvement percent.
9. Repeat with the Python sample.
10. Repeat with the web sample (HTML/CSS/JS).
11. Repeat with the Django-like sample, if available.
12. Repeat with the Node.js-like sample, if available.
13. Check failures: no issue selected, invalid `project_path`, empty AI response, and missing issue `file_path`.
