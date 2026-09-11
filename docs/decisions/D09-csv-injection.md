# D09 — CSV formula injection

**Question (review product-policy table):** CSV exports (`evaluation_csv`, the
evaluation-pack template CSV) write user-authored names and imported free text
verbatim. A cell beginning `=`, `+`, `-`, `@`, tab, or CR is interpreted as a
formula by Excel/Sheets when the file is opened.

**Decision:** prefix-guard risky cells in generated CSVs. Any string value whose
first character is one of `= + - @ \t \r` is prefixed with a single quote (`'`)
before writing. Applied in a shared `app/core/csv_safe.py` helper used by both
CSV producers.

**Why this and not blanket quoting:** CSV quoting (`"..."`) controls
*delimiter* parsing, not *formula* interpretation — a quoted `"=1+1"` still
evaluates. The leading-apostrophe convention is what spreadsheet apps honour.

**Numbers are preserved:** a genuine negative number like `-5` becomes `'-5`,
which spreadsheets still read as text; acceptable for an export meant for
human/analytics review. If a strictly-numeric export is later needed, guard
only non-numeric strings.

**Not provisional.**
