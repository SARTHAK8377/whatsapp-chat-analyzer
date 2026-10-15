# WhatsApp analyzer – architecture notes

Single file `whatsapp_analyzer.py`, pipeline in `main()`:

1. `parse_chat(path)` → DataFrame `ts, sender, text, is_media, is_deleted, is_edited` + info dict
   - `read_lines` groups multiline messages; `split_senders` picks the longest `Name: ` prefix that is
     used about as often as the shortest one (handles names with colons).
   - System messages get sender `"System"` (no `Name:`, iPhone `‎` notices, or one-off
     "X added/left/changed…" prefixes).
2. Date filter (`--from/--to`), then `members_from_system` (added/joined/left/removed names).
3. `anonymize` (optional) – letters by message count; scrubs names, phones, emails in text.
4. `enrich(df, gap)` → `is_system, n_words, has_link, has_question, session_id`.
5. `build_report` calls one function per analysis and assembles offline HTML (Plotly JS inlined).

Rules agreed with the user:
- Media and System messages count as turns (start/end sessions, break bursts).
- System is never a reply and is excluded from per-person tables and the speaker matrix.
- Reply time = gap at each sender change within a session; median and P90 only.
- Second-less timestamps: a 0s gap becomes 30s (needed for the log-normal fit).

Entry points (bottom of the file):
- No arguments → `launch_app()` starts Streamlit on localhost (stats off, Deploy button hidden).
  `Start Analyzer.bat` does this on double-click.
- Under Streamlit → `run_app()`: upload (.zip/.txt) → `chat_text` → `parse_chat` → `prepare` → `analyze`,
  cached with `st.cache_data`; the same `analyze()` dict feeds `render_html` for the download button.
- With a file argument → `main()` CLI writes the HTML report.

Look: "a chat at night" (frontend-design skill pass). The key findings are told as a chat thread
(`story()` → `thread_html`): analyzer bubbles on the left with big Bahnschrift numbers, "your" questions
on the right with read ticks. Palette: night #0B1A1E, thread #12262B, sent #0F4D45, tick blue #53BDEB
(the one accent), amber #F2B66D (avatar + 2nd series). Type: Bahnschrift display, Segoe UI body; no
web fonts (offline). Bubbles pop in once on load; nothing else animates.
Design notes: previous pass (neon glass cards, gradient text, 01–07 section numbers, ALL-CAPS kickers,
mono labels, fade-in on every card) read as generic and was removed; don't bring those back.
Colour constants (`SERIES`, `SOFT`, `BLUES`, `INK`…) drive the Plotly charts; `THEME_CSS` is shared by
the HTML report (`CSS`) and the app (`APP_CSS`, plus Streamlit `data-testid` overrides). HTML snippets
come from `header_html`, `thread_html`, `section_html`, `note_html`; the app shows them with `st.html`. Dark Streamlit theme is in
`.streamlit/config.toml`, so `launch_app()` runs Streamlit with this folder as its working directory.

Pipeline: `chat_text(bytes)` → `parse_chat(text)` → `prepare(df, info, gap, start, end, anon)` →
`analyze(df, info)` → `render_html(res, title)` or the Streamlit layout.

Windows EXE: `build_exe.bat` runs PyInstaller (--onefile, ~455 MB, ~20 min) on `exe_launcher.py` and writes
`Chat Analyzer.exe` to Downloads. The launcher runs Streamlit in-process with all settings as CLI flags
(no config.toml inside the bundle), including `logger.hideWelcomeMessage` to suppress Streamlit's promo
pop-up. Rebuild after any change to whatsapp_analyzer.py.

Testing: `py -3.12 samples/make_samples.py samples` writes fake Android group + iPhone 1:1 chats.
