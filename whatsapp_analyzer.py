"""WhatsApp chat analyzer - fully local, nothing leaves your machine.

Usage:
    py -3.12 whatsapp_analyzer.py                   -> opens the app in your browser (upload button)
    py -3.12 whatsapp_analyzer.py chat.zip          -> writes chat_report.html directly
    py -3.12 whatsapp_analyzer.py chat.txt --gap 6 --from 2024-01-01 --to 2024-12-31 --anon -o report.html

Reads a WhatsApp export (.txt or .zip, "without media") and shows interactive
charts, or writes a single offline HTML report. Each analysis is one function
below; edit or delete them freely.
"""
import argparse
import html
import io
import math
import re
import zipfile
from collections import Counter
from pathlib import Path

import emoji
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import regex
from plotly.offline import get_plotlyjs
from plotly.subplots import make_subplots
from scipy import stats

# =============================================================================
# SETTINGS - edit these
# =============================================================================
SESSION_GAP_HOURS = 6          # new session after a silence longer than this
LATE_NIGHT_END_HOUR = 5        # late night = 00:00 up to (not including) this hour
LURKER_SHARE = 0.01            # members with less than 1% of messages are lurkers
TOP_N = 20                     # bars in word / emoji charts
MIN_DISTINCTIVE_COUNT = 3      # a word must be used this often by a person to count
MAX_PEOPLE = 8                 # people beyond this are folded into "Others" in charts
SYSTEM = "System"              # sender label for system messages

# Media placeholders (Android, iPhone, a few languages). Matched on the whole message.
MEDIA_RE = re.compile(
    r"^(?:<media omitted>|<multimedia omitido>|<medien ausgeschlossen>|<mídia oculta>"
    r"|<médias omis>|<media weggelaten>|<attached: [^>]+>|null"
    r"|<[^<>]{1,40}>)$"                                    # any short <...> placeholder
    r"|(?:image|video|audio|sticker|gif|document|contact card|photo) omitted$"
    r"|\(file attached\)$",
    re.IGNORECASE,
)
DELETED_RE = re.compile(
    r"^(?:this message was deleted|you deleted this message"
    r"|se eliminó este mensaje|eliminaste este mensaje)\.?$",
    re.IGNORECASE,
)
EDITED_RE = re.compile(r"\s*<(?:this message was edited|se editó este mensaje\.?)>\s*$", re.IGNORECASE)
# Phrases that mark a "Name: ..." line as really being a system notice.
SYSTEM_HINT_RE = re.compile(
    r"\b(?:added|removed|left|joined|created group|changed (?:the|this|their|to|group)"
    r"|security code|end-to-end encrypted|pinned a message|now an admin|disappearing messages)\b",
    re.IGNORECASE,
)

STOPWORDS = set("""
a about after again all also am an and any are as at be because been before being but by can
could did do does doing don dont down for from get got had has have having he her here hers him
his how i if im in into is it its ive just let like me more most my no not now of off on once
only or other our out over own really same she should so some such than that thats the their
them then there these they this those through to too under until up us very was we well were
what when where which while who whom why will with would yes you your youre yours u ur ya yeah
yep nope ok okay okk okkk k kk hmm hm hmmm oh ohh ah lol haha hahaha hehe na nah pls plz please
thanks thx ty gonna wanna gotta one also bhi
hai hain ha haan han ho hoga hogi hoge hu hun hoon ka ki ke ko se me mein main mai mujhe mujhko
tu tum tera teri tere tumhara tumhari mera meri mere apna apni apne aap hum hamara ye yeh wo woh
vo voh kya kyu kyun kyon kaise kab kaha kahan kidhar idhar udhar na nahi nhi nahin mat toh to
aur ya par pe ek jo jab tab kuch sab bas abhi ab phir fir tha thi the thhe raha rahi rahe rha rhi
kar karo kr karna krna karta karti kiya kia diya diye liya liye gaya gya gayi gyi hua hui huye
de do le lo dena lena wala wali wale vala vali vale haa achha acha accha theek thik arre are arey
yaar yar bhai bro re hi hello sach mein bahut bohot bht thoda zyada jaise waise isliye kyunki
""".split())

# "A chat at night" theme (see THEME_CSS). Read-tick blue leads, amber second; fixed order.
SERIES = ["#53BDEB", "#F2B66D", "#3DD68C", "#E879A6", "#9085E9", "#F0805A", "#7FD1C7", "#E66767"]
SOFT = "rgba(83, 189, 235, 0.30)"          # translucent blue for background bars
BLUES = ["#11262B", "#123D4A", "#14586B", "#1A7690", "#2B98B8", "#53BDEB", "#C4ECFB"]
INK, INK2, MUTED = "#E7EEEC", "#AFC2C0", "#7E9796"
GRID, AXIS, SURFACE = "rgba(231, 238, 236, 0.07)", "rgba(231, 238, 236, 0.18)", "rgba(0, 0, 0, 0)"
BG, PANEL = "#0B1A1E", "#12262B"
FONT = "'Segoe UI Variable Text', 'Segoe UI', system-ui, -apple-system, sans-serif"
DISPLAY = "Bahnschrift, 'DIN Alternate', 'Arial Narrow', sans-serif"

# =============================================================================
# PARSING
# =============================================================================
LINE = re.compile(
    r"^\u200e?\[?(\d{1,2}[/.]\d{1,2}[/.]\d{2,4}),?\s(\d{1,2}:\d{2}(?::\d{2})?(?:[\s\u202f]?[APap][Mm])?)\]?\s?-?\s?(.*)$"
)
BIDI = re.compile("[\u200e\u200f\u202a-\u202e\u2066-\u2069]")


def chat_text(data):
    """Chat text from the bytes of an exported .txt or .zip (uses the chat .txt inside the zip)."""
    if zipfile.is_zipfile(io.BytesIO(data)):
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            txts = [i for i in z.infolist() if i.filename.lower().endswith(".txt") and not i.is_dir()]
            if not txts:
                raise ValueError("No chat .txt file found inside the zip.")
            data = z.read(max(txts, key=lambda i: i.file_size))
    return data.decode("utf-8-sig", errors="replace")


def read_lines(text):
    """Group raw lines into messages: [date, time, first line, continuation lines]."""
    rows, cur = [], None
    for line in re.split(r"\r\n|\r|\n", text):
        m = LINE.match(line)
        if m:
            d, t, rest = m.groups()
            cur = [d, t.replace("\u202f", " ").replace("\u00a0", " "), rest, []]
            rows.append(cur)
        elif cur:                                      # continuation of a multiline message
            cur[3].append(line)
    if cur and cur[3] and cur[3][-1] == "":            # trailing newline at end of file
        cur[3].pop()
    return rows


def split_senders(firsts):
    """Split 'Name: text' safely, even when names contain ': ' (e.g. 'Dr: Sharma').

    For each line we look at every possible 'Name: ' prefix and keep the longest
    one that is used about as often as the shortest one, i.e. a real sender.
    Returns a list of (sender or None, text, prefix_count).
    """
    cands, counts = [], Counter()
    for rest in firsts:
        prefixes = [rest[:m.start()] for m in re.finditer(": ", rest)][:3]
        prefixes = [p for p in prefixes if 0 < len(p) <= 60]
        cands.append(prefixes)
        counts.update(set(prefixes))
    out = []
    for rest, prefixes in zip(firsts, cands):
        if not prefixes:
            out.append((None, rest, 0))
            continue
        best = prefixes[0]
        for p in prefixes[1:]:
            if counts[p] >= 2 and counts[p] >= 0.5 * counts[prefixes[0]]:
                best = p
        out.append((best, rest[len(best) + 2:], counts[best]))
    return out


def clean_name(name):
    name = BIDI.sub("", name).replace("\u202f", " ").replace("\u00a0", " ").strip()
    return name.lstrip("~").strip()


def parse_chat(text):
    """Parse chat text. Returns (DataFrame[ts, sender, text, is_media, is_deleted, is_edited], info dict)."""
    raw = read_lines(text)
    if not raw:
        raise ValueError("No WhatsApp messages found. Is this an exported WhatsApp chat (.txt or .zip)?")
    split = split_senders([r[2] for r in raw])

    records = []
    for (d, t, _, cont), (sender, first, n) in zip(raw, split):
        text = "\n".join([first] + cont)
        plain = BIDI.sub("", text).strip()
        is_media = bool(MEDIA_RE.search(plain))
        is_deleted = bool(DELETED_RE.match(plain))
        is_edited = bool(EDITED_RE.search(plain))
        if is_edited:
            plain = EDITED_RE.sub("", plain)
        if sender is None:
            sender, plain = SYSTEM, BIDI.sub("", text).strip()
        elif not (is_media or is_deleted) and text.startswith("\u200e"):
            sender = SYSTEM                            # iPhone system notice ("Name: \u200e...")
        elif n == 1 and SYSTEM_HINT_RE.search(sender):
            sender, plain = SYSTEM, BIDI.sub("", f"{sender}: {text}").strip()
        else:
            sender = clean_name(sender)
        records.append((d, t, sender, plain, is_media, is_deleted, is_edited))

    df = pd.DataFrame(records, columns=["d", "t", "sender", "text", "is_media", "is_deleted", "is_edited"])
    n = df["d"].str.extract(r"(\d+)[/.](\d+)").astype(int)
    dayfirst = bool((n[0] > 12).any() or not (n[1] > 12).any())
    df["ts"] = pd.to_datetime(df["d"] + " " + df["t"], dayfirst=dayfirst, format="mixed", errors="coerce")
    bad = int(df["ts"].isna().sum())
    df = df.dropna(subset=["ts"]).drop(columns=["d", "t"])
    df = df.sort_values("ts", kind="stable").reset_index(drop=True)
    return df, {"dayfirst": dayfirst, "bad_timestamps": bad, "lines": len(raw)}


# =============================================================================
# MEMBERS & ANONYMIZING
# =============================================================================
def members_from_system(df):
    """Names added/joined (and left/removed) according to system messages."""
    added, gone = set(), set()
    for text in df.loc[df["sender"] == SYSTEM, "text"]:
        if m := re.match(r"^(.+?) added (.+)$", text):
            added.update(re.split(r", | and ", m.group(2)))
        elif m := re.match(r"^(.+?) joined using", text):
            added.add(m.group(1))
        elif m := re.match(r"^(.+?) left$", text):
            gone.add(m.group(1))
        elif m := re.match(r"^(.+?) removed (.+)$", text):
            gone.update(re.split(r", | and ", m.group(2)))
    clean = lambda names: {clean_name(x) for x in names} - {"You", "you", ""}
    return clean(added), clean(gone)


def letters(i):
    s = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


def anonymize(df, extra_names):
    """Replace names with A, B, C... (most active = A), in senders and inside text."""
    order = list(df.loc[df["sender"] != SYSTEM, "sender"].value_counts().index)
    order += sorted(set(extra_names) - set(order))
    mapping = {name: letters(i) for i, name in enumerate(order)}

    # Full names first, then first names (>= 3 letters) - longest first.
    subs = dict(mapping)
    for name, code in mapping.items():
        first = name.split()[0] if name.split() else ""
        if len(first) >= 3 and first.lower() not in STOPWORDS and first not in subs:
            subs[first] = code
    names = sorted(subs, key=len, reverse=True)
    name_re = re.compile(r"(?<!\w)(" + "|".join(map(re.escape, names)) + r")(?!\w)", re.IGNORECASE) if names else None
    lower = {k.lower(): v for k, v in subs.items()}

    def scrub(text):
        if name_re:
            text = name_re.sub(lambda m: lower[m.group(1).lower()], text)
        text = re.sub(r"\S+@\S+\.\w+", "[email]", text)
        text = re.sub(r"\+?\d[\d \-]{7,}\d", "[number]", text)
        return text

    df = df.copy()
    df["sender"] = df["sender"].map(lambda s: mapping.get(s, s))
    df["text"] = df["text"].map(scrub)
    return df, mapping


# =============================================================================
# ENRICH
# =============================================================================
URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)


def enrich(df, gap_hours):
    df = df.copy()
    df["is_system"] = df["sender"].eq(SYSTEM)
    is_text = ~(df["is_system"] | df["is_media"] | df["is_deleted"])
    df["n_words"] = np.where(is_text, df["text"].str.split().str.len().fillna(0), 0).astype(int)
    df["has_link"] = ~df["is_system"] & df["text"].str.contains(URL_RE)
    df["has_question"] = ~df["is_system"] & df["text"].str.contains("?", regex=False)
    df["session_id"] = (df["ts"].diff() > pd.Timedelta(hours=gap_hours)).cumsum()
    return df


def people_of(df):
    """Real senders, most active first."""
    return list(df.loc[~df["is_system"], "sender"].value_counts().index)


def fold(series, people):
    keep = set(people[:MAX_PEOPLE])
    return series.where(series.isin(keep) | series.eq(SYSTEM), "Others")


# =============================================================================
# METRICS
# =============================================================================
def reply_times(df):
    """Gap from a message to the next message when the sender changes, same session only.

    Measured at every turn change (last message of one person -> first message
    of the next person). System messages count as turns but are never a reply.
    """
    prev = df.shift(1)
    mask = (
        df["session_id"].eq(prev["session_id"])
        & df["sender"].ne(prev["sender"])
        & ~df["is_system"]
        & prev["sender"].ne(SYSTEM)
        & prev["sender"].notna()
    )
    secs = (df["ts"] - prev["ts"]).dt.total_seconds()[mask]
    # Timestamps without seconds: a 0 gap means "under a minute", so use 30s.
    resolution = 60 if (df["ts"].dt.second == 0).all() else 1
    secs = secs.where(secs > 0, resolution / 2)
    return pd.DataFrame({"responder": df.loc[mask, "sender"], "to": prev.loc[mask, "sender"], "secs": secs})


def longest_streak(df):
    days = pd.Series(sorted(df.loc[~df["is_system"], "ts"].dt.normalize().unique()))
    if days.empty:
        return 0, None, None
    run = (days.diff() != pd.Timedelta(days=1)).cumsum()
    sizes = run.value_counts()
    best = sizes.idxmax()
    span = days[run == best]
    return int(sizes.max()), span.iloc[0], span.iloc[-1]


def double_texts(df):
    """Runs of 2+ consecutive messages by the same sender (System breaks a run)."""
    run = df["sender"].ne(df["sender"].shift()).cumsum().rename("run")
    runs = df.groupby(run).agg(sender=("sender", "first"), size=("sender", "size"))
    runs = runs[(runs["size"] >= 2) & (runs["sender"] != SYSTEM)]
    return runs.groupby("sender").size()


def session_edges(df):
    g = df.groupby("session_id")["sender"]
    return g.first().value_counts(), g.last().value_counts()


def person_table(df, replies):
    msgs = df[~df["is_system"]]
    people = people_of(df)
    g = msgs.groupby("sender")
    text_msgs = msgs[msgs["n_words"] > 0]
    starts, ends = session_edges(df)
    rg = replies.groupby("responder")["secs"]
    t = pd.DataFrame(index=people)
    t["Messages"] = g.size()
    t["Share"] = t["Messages"] / t["Messages"].sum()
    t["Median words"] = text_msgs.groupby("sender")["n_words"].median()
    t["Media"] = g["is_media"].sum()
    t["Links"] = g["has_link"].sum()
    t["Started"] = starts
    t["Ended"] = ends
    t["Double-texts"] = double_texts(df)
    t["Late-night"] = g["ts"].apply(lambda s: (s.dt.hour < LATE_NIGHT_END_HOUR).mean())
    t["Questions"] = g["has_question"].mean()
    t["Reply median"] = rg.median()
    t["Reply p90"] = rg.quantile(0.9)
    t["Replies"] = rg.size()
    return t.fillna({"Started": 0, "Ended": 0, "Double-texts": 0, "Replies": 0})


# =============================================================================
# LANGUAGE
# =============================================================================
WORD_RE = regex.compile(r"[\p{L}\p{M}]+(?:['’][\p{L}\p{M}]+)*")


def tokens(text):
    text = URL_RE.sub(" ", text.lower())
    return [w for w in WORD_RE.findall(text) if len(w) > 1 and w not in STOPWORDS]


def emojis(text):
    return [e["emoji"] for e in emoji.emoji_list(text)]


def word_counts(df):
    """Counter of words per person (text messages only)."""
    msgs = df[df["n_words"] > 0]
    return {p: Counter(w for t in g["text"] for w in tokens(t)) for p, g in msgs.groupby("sender")}


def distinctive_words(counts, top=8):
    """Smoothed log-odds ratio (informative Dirichlet prior, Monroe et al. 2008).

    Each person vs everyone else; the prior is the whole chat's word counts.
    Returns {person: [(word, z-score), ...]} with only clearly over-used words (z > 1.96).
    """
    total = Counter()
    for c in counts.values():
        total.update(c)
    a0 = sum(total.values())
    out = {}
    for p, yi in counts.items():
        ni = sum(yi.values())
        nj = a0 - ni
        scores = []
        for w, y in yi.items():
            if y < MIN_DISTINCTIVE_COUNT:
                continue
            aw, yj = total[w], total[w] - y
            d = math.log((y + aw) / (ni + a0 - y - aw)) - math.log((yj + aw) / (nj + a0 - yj - aw))
            z = d / math.sqrt(1 / (y + aw) + 1 / (yj + aw))
            if z > 1.96:
                scores.append((w, z))
        out[p] = sorted(scores, key=lambda x: -x[1])[:top]
    return out


# =============================================================================
# TRENDS
# =============================================================================
def change_points(y, min_size=4, max_cp=6):
    """Mean-shift change points by CUSUM-style binary segmentation.

    Works on sqrt(counts) to steady the noise. A split is kept only if it explains
    more than 3*log(n) noise-variances (a BIC-like penalty).
    """
    y = np.sqrt(np.asarray(y, dtype=float))
    n = len(y)
    if n < 2 * min_size:
        return []
    sigma = np.median(np.abs(np.diff(y))) / (0.6745 * math.sqrt(2)) or y.std() or 1.0
    penalty = 3 * math.log(n) * sigma ** 2

    def best_split(a, b):
        seg = y[a:b]
        csum = np.cumsum(seg)
        m = len(seg)
        best = (0.0, None)
        for k in range(min_size, m - min_size + 1):
            m1, m2 = csum[k - 1] / k, (csum[-1] - csum[k - 1]) / (m - k)
            gain = k * (m - k) / m * (m1 - m2) ** 2
            if gain > best[0]:
                best = (gain, a + k)
        return best

    cps, segments = [], [(0, n)]
    while len(cps) < max_cp:
        cands = [(best_split(a, b), (a, b)) for a, b in segments]
        (gain, k), (a, b) = max(cands, key=lambda c: c[0][0])
        if k is None or gain < penalty:
            break
        cps.append(k)
        segments.remove((a, b))
        segments += [(a, k), (k, b)]
    return sorted(cps)


def gini(values):
    x = np.sort(np.asarray(values, dtype=float))
    n = len(x)
    if n == 0 or x.sum() == 0:
        return 0.0
    i = np.arange(1, n + 1)
    return float(((2 * i - n - 1) * x).sum() / (n * x.sum()))


# =============================================================================
# CHARTS
# =============================================================================
def style(fig, title, height=380, subtitle=None):
    t = html.escape(title)
    if subtitle:
        t += (f"<br><span style='font-size:12.5px;font-weight:400;color:{INK2};font-family:{FONT}'>"
              f"{html.escape(subtitle)}</span>")
    fig.update_layout(
        title=dict(text=t, x=0, xanchor="left", font=dict(size=19, color=INK, family=DISPLAY, weight=600)),
        height=height, margin=dict(l=60, r=20, t=70 if subtitle else 50, b=50),
        paper_bgcolor=SURFACE, plot_bgcolor=SURFACE,
        font=dict(family=FONT, size=12, color=INK2),
        hoverlabel=dict(bgcolor=BG, bordercolor=AXIS, font=dict(color=INK, size=12.5, family=FONT)),
        legend=dict(orientation="h", y=1.02, yanchor="bottom", x=1, xanchor="right", font_color=INK2),
        bargap=0.25,
    )
    fig.update_xaxes(gridcolor=GRID, linecolor=AXIS, zeroline=False, tickfont_color=MUTED, title_font_color=MUTED)
    fig.update_yaxes(gridcolor=GRID, linecolor=AXIS, zeroline=False, tickfont_color=MUTED, title_font_color=MUTED)
    fig.update_annotations(font_color=INK2)                # subplot titles
    return fig


def blues_scale():
    return [[i / (len(BLUES) - 1), c] for i, c in enumerate(BLUES)]


def fmt_dur(secs):
    if secs is None or pd.isna(secs):
        return "-"
    if secs < 60:
        return f"{secs:.0f}s"
    if secs < 3600:
        return f"{secs / 60:.0f}m"
    if secs < 86400:
        return f"{secs / 3600:.1f}h"
    return f"{secs / 86400:.1f}d"


def chart_heatmap(df):
    msgs = df[~df["is_system"]]
    days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    grid = (msgs.groupby([msgs["ts"].dt.dayofweek, msgs["ts"].dt.hour]).size()
            .unstack(fill_value=0).reindex(index=range(7), columns=range(24), fill_value=0))
    fig = go.Figure(go.Heatmap(
        z=grid.values, x=[f"{h:02d}" for h in range(24)], y=days, colorscale=blues_scale(),
        xgap=2, ygap=2, colorbar=dict(title="msgs", thickness=10),
        hovertemplate="%{y} %{x}:00 - %{z} messages<extra></extra>"))
    fig.update_yaxes(autorange="reversed", showgrid=False)
    fig.update_xaxes(showgrid=False, title="hour of day", type="category")
    return style(fig, "When the chat is active", 320, "Messages by weekday and hour")


def chart_timeline(df):
    msgs = df[~df["is_system"]]
    daily = msgs.set_index("ts").resample("D").size()
    fig = go.Figure()
    fig.add_bar(x=daily.index, y=daily.values, name="Messages per day", marker_color=SOFT,
                hovertemplate="%{x|%d %b %Y}: %{y}<extra></extra>")
    fig.add_scatter(x=daily.index, y=daily.rolling(7, min_periods=1).mean(), name="7-day average",
                    line=dict(color=SERIES[0], width=2), hovertemplate="%{x|%d %b %Y}: %{y:.1f}<extra></extra>")
    fig.update_layout(hovermode="x unified")
    return style(fig, "Daily messages", 340)


def chart_initiators(table):
    t = table.head(MAX_PEOPLE)
    fig = go.Figure()
    fig.add_bar(x=t.index, y=t["Started"], name="Started sessions", marker_color=SERIES[0])
    fig.add_bar(x=t.index, y=t["Ended"], name="Ended sessions", marker_color=SERIES[1])
    fig.update_layout(barmode="group", bargroupgap=0.08)
    return style(fig, "Who starts and who ends conversations", 340,
                 "Sender of the first / last message of each session")


def chart_replies(replies, people):
    who = [p for p in people[:MAX_PEOPLE] if (replies["responder"] == p).sum() >= 5]
    if not who:
        return None, pd.DataFrame()
    cols = min(len(who), 4)
    rows = math.ceil(len(who) / cols)
    fig = make_subplots(rows=rows, cols=cols, subplot_titles=who, shared_yaxes=True,
                        horizontal_spacing=0.04, vertical_spacing=0.18)
    ticks = [10, 60, 600, 3600, 6 * 3600]
    fits = []
    for i, p in enumerate(who):
        x = replies.loc[replies["responder"] == p, "secs"].to_numpy()
        lx = np.log10(x)
        r, c = i // cols + 1, i % cols + 1
        fig.add_histogram(x=lx, histnorm="probability density", nbinsx=25, marker_color=SOFT,
                          showlegend=False, row=r, col=c, hovertemplate="%{y:.2f}<extra></extra>")
        shape, _, scale = stats.lognorm.fit(x, floc=0)
        grid = np.linspace(lx.min(), lx.max(), 100)
        pdf = stats.norm.pdf(grid, loc=math.log10(scale), scale=shape / math.log(10))
        fig.add_scatter(x=grid, y=pdf, mode="lines", line=dict(color=SERIES[1], width=2),
                        name="Log-normal fit", showlegend=(i == 0), row=r, col=c, hoverinfo="skip")
        med, p90 = np.median(x), np.quantile(x, 0.9)
        fig.add_vline(x=math.log10(med), line=dict(color=INK2, width=1, dash="dot"), row=r, col=c)
        fits.append({"Person": p, "Replies": len(x), "Median": fmt_dur(med), "P90": fmt_dur(p90),
                     "Fitted median": fmt_dur(scale), "Spread (σ)": f"{shape:.2f}"})
    lx_all = np.log10(replies.loc[replies["responder"].isin(who), "secs"])
    fig.update_xaxes(tickvals=[math.log10(t) for t in ticks], ticktext=["10s", "1m", "10m", "1h", "6h"],
                     range=[lx_all.min() - 0.1, lx_all.max() + 0.1])
    fig.update_yaxes(showticklabels=False)
    style(fig, "How fast people reply", 260 * rows + 100,
          "Reply-time distribution (log scale), dotted line = median, pink = log-normal fit")
    fig.update_layout(margin_t=110, legend=dict(y=-0.12, yanchor="top", x=0, xanchor="left"))
    return fig, pd.DataFrame(fits)


def chart_bars(counter, title, color, n=TOP_N):
    items = counter.most_common(n)[::-1]
    if not items:
        return None
    fig = go.Figure(go.Bar(x=[v for _, v in items], y=[k for k, _ in items], orientation="h",
                           marker_color=color, hovertemplate="%{y}: %{x}<extra></extra>"))
    fig.update_yaxes(showgrid=False, tickfont=dict(size=13, color=INK))
    return style(fig, title, max(300, 22 * len(items) + 80))


def chart_lengths(df, people):
    msgs = df[(df["n_words"] > 0) & df["sender"].isin(people[:MAX_PEOPLE])]
    fig = go.Figure()
    for p in people[:MAX_PEOPLE]:
        fig.add_box(y=msgs.loc[msgs["sender"] == p, "n_words"], name=p, marker_color=SERIES[0],
                    boxpoints=False, showlegend=False)
    fig.update_yaxes(type="log", title="words per message")
    return style(fig, "Message length", 340, "Words per text message (log scale)")


def chart_weekly(df):
    msgs = df[~df["is_system"]]
    weekly = msgs.set_index("ts").resample("W-MON", label="left", closed="left").size()
    cps = change_points(weekly.values)
    bounds = [0] + cps + [len(weekly)]
    level = np.concatenate([np.full(b - a, weekly.values[a:b].mean()) for a, b in zip(bounds, bounds[1:])])
    fig = go.Figure()
    fig.add_bar(x=weekly.index, y=weekly.values, name="Messages per week", marker_color=SOFT,
                hovertemplate="Week of %{x|%d %b %Y}: %{y}<extra></extra>")
    fig.add_scatter(x=weekly.index, y=level, name="Average level", mode="lines",
                    line=dict(color=SERIES[1], width=2, shape="hv"),
                    hovertemplate="Level: %{y:.0f}/week<extra></extra>")
    shifts = []
    for k in cps:
        before, after = level[k - 1], level[k]
        fig.add_vline(x=weekly.index[k], line=dict(color=INK2, width=1, dash="dot"))
        shifts.append({"week": weekly.index[k], "before": before, "after": after,
                       "change": (after - before) / before * 100 if before else float("inf")})
    fig.update_layout(hovermode="x unified")
    return style(fig, "Weekly trend", 340, "Dotted lines mark where the weekly level shifted"), shifts


def chart_markov(df, people):
    d = df[["sender", "session_id"]].copy()
    d["sender"] = fold(d["sender"], people)
    nxt = d.shift(-1)
    mask = d["session_id"].eq(nxt["session_id"]) & d["sender"].ne(SYSTEM) & nxt["sender"].ne(SYSTEM) & nxt["sender"].notna()
    counts = pd.crosstab(d.loc[mask, "sender"], nxt.loc[mask, "sender"])
    order = [p for p in people[:MAX_PEOPLE] + ["Others"] if p in counts.index or p in counts.columns]
    counts = counts.reindex(index=order, columns=order, fill_value=0)
    probs = counts.div(counts.sum(axis=1).replace(0, np.nan), axis=0).fillna(0)
    fig = go.Figure(go.Heatmap(
        z=probs.values, x=order, y=order, colorscale=blues_scale(), zmin=0, zmax=1, xgap=2, ygap=2,
        text=(probs.values * 100).round(0).astype(int), texttemplate="%{text}%",
        colorbar=dict(title="P", thickness=10, tickformat=".0%"),
        hovertemplate="After %{y}, next is %{x}: %{z:.0%}<extra></extra>"))
    fig.update_yaxes(autorange="reversed", title="current sender", showgrid=False)
    fig.update_xaxes(title="next sender", showgrid=False)
    return style(fig, "Who speaks after whom", 160 + 50 * len(order),
                 "P(next sender | current sender), within sessions; diagonal = same person again")


# =============================================================================
# REPORT
# =============================================================================
# Shared look for the app and the HTML report: "a chat at night". The page reads like a chat
# thread: teal-black background, the key findings told as message bubbles, read-tick blue as
# the one accent, Bahnschrift (a condensed DIN face that ships with Windows) for display type.
THEME_CSS = """
:root {
  color-scheme: dark;
  --night: #0B1A1E; --thread: #12262B; --sent: #0F4D45; --line: rgba(231, 238, 236, 0.08);
  --ink: #E7EEEC; --ink2: #AFC2C0; --mute: #7E9796; --tick: #53BDEB; --amber: #F2B66D;
  --display: Bahnschrift, 'DIN Alternate', 'Arial Narrow', sans-serif;
  --text: 'Segoe UI Variable Text', 'Segoe UI', system-ui, -apple-system, sans-serif;
}
.page, .stApp {
  background: radial-gradient(900px 520px at 12% -8%, rgba(15, 77, 69, 0.55), transparent 70%), var(--night);
  background-attachment: fixed;
}
.chathead { display: flex; align-items: center; gap: 16px; padding-bottom: 18px; border-bottom: 1px solid var(--line); }
.avatar { flex: none; width: 56px; height: 56px; border-radius: 50%; display: grid; place-items: center;
          background: var(--sent); color: var(--amber); font: 600 21px/1 var(--display); }
.who { font: 600 clamp(28px, 4vw, 40px)/1.05 var(--display); letter-spacing: -0.01em; color: var(--ink); }
.sub { font: 15px/1.4 var(--text); color: var(--ink2); margin-top: 4px; }
.thread { display: flex; flex-direction: column; gap: 6px; max-width: 660px; margin: 26px 0 10px; }
.b { width: fit-content; max-width: 80%; padding: 10px 14px; border-radius: 14px;
     font: 16px/1.5 var(--text); color: var(--ink); animation: pop .34s cubic-bezier(.2, .9, .3, 1.15) both;
     animation-delay: calc(var(--i, 0) * 240ms); transform-origin: 0 100%; }
.b.in { background: var(--thread); border-top-left-radius: 4px; align-self: flex-start; }
.b.out { background: var(--sent); border-top-right-radius: 4px; align-self: flex-end;
         transform-origin: 100% 100%; margin-top: 10px; }
.b.out + .b.in { margin-top: 10px; }
.b .big { display: block; font: 600 clamp(40px, 6vw, 60px)/1 var(--display); color: var(--tick);
          letter-spacing: -0.01em; margin: 4px 0 8px; font-variant-numeric: tabular-nums; }
.b .ticks { color: var(--tick); font-size: 12px; margin-left: 10px; letter-spacing: -3px; }
.b ol { margin: 6px 0 2px; padding-left: 20px; }
.b li { margin: 3px 0; }
.sh { margin: 76px 0 16px; max-width: 68ch; }
.sh h2 { font: 600 32px/1.15 var(--display); color: var(--ink); margin: 0 0 6px; padding: 0; border: 0; }
.sh p { font: 15.5px/1.5 var(--text); color: var(--ink2); margin: 0; }
.fine { font: 13.5px/1.65 var(--text); color: var(--mute); max-width: 76ch; margin: 10px 0; padding-left: 18px; }
.fine li { margin: 2px 0; }
@keyframes pop { from { opacity: 0; transform: translateY(8px) scale(.94); } }
@media (prefers-reduced-motion: reduce) { .b { animation: none; } }
@media (max-width: 600px) { .b { max-width: 92%; } }
"""

# Extra rules for the downloadable HTML report.
CSS = THEME_CSS + """
body { margin: 0; color: var(--ink); font-family: var(--text); line-height: 1.5; }
main { max-width: 1080px; margin: 0 auto; padding: 48px 20px 80px; }
.card { background: var(--thread); border: 1px solid var(--line); border-radius: 10px; padding: 8px;
        margin: 12px 0; overflow-x: auto; }
table { border-collapse: collapse; width: 100%; font-size: 14px; font-variant-numeric: tabular-nums; }
th, td { padding: 9px 12px; text-align: right; border-bottom: 1px solid var(--line); white-space: nowrap; }
tr:last-child td { border-bottom: 0; }
th:first-child, td:first-child { text-align: left; color: var(--ink); }
th { color: var(--mute); font-weight: 600; }
.grid2 { display: grid; grid-template-columns: repeat(auto-fit, minmax(420px, 1fr)); gap: 12px; }
.footer { color: var(--mute); font-size: 13px; margin-top: 56px; }
@media (max-width: 500px) { .grid2 { grid-template-columns: 1fr; } }
"""

SECTIONS = {  # key: (heading, one-line explanation)
    "Activity": ("When you talk", "Messages by weekday and hour, then day by day."),
    "People": ("Who's who", "Each person's share of the chat, their habits and how fast they reply."),
    "Conversation dynamics": ("Who starts and who replies",
                              "Who opens and closes conversations, and how long replies take."),
    "Language": ("What gets said",
                 "Most-used words and emoji, and the words each person uses more than anyone else."),
    "Trends": ("How it's changing", "Messages per week, with the points where the level clearly shifted."),
    "Group behaviour": ("How the group behaves",
                        "Who tends to speak after whom, and how evenly the talking is shared."),
    "About this report": ("How this was worked out", "Definitions and notes about the data."),
}


def section_html(key):
    title, desc = SECTIONS[key]
    return f'<div class="sh"><h2>{html.escape(title)}</h2><p>{html.escape(desc)}</p></div>'


def chat_title(stem):
    """'WhatsApp Chat with Hostel Gang' -> 'Hostel Gang'."""
    return re.sub(r"^whatsapp chat\s*(?:with|-)\s*", "", stem, flags=re.IGNORECASE).strip() or stem


def list_names(names):
    if len(names) > 3:
        return ", ".join(names[:3]) + f" and {len(names) - 3} more"
    return " and ".join([", ".join(names[:-1]), names[-1]]) if len(names) > 1 else "".join(names)


def header_html(res, name):
    letters_ = "".join(w[0] for w in re.findall(r"[^\W_]+", name)[:2]).upper() or "?"
    return (f'<div class="chathead"><div class="avatar">{html.escape(letters_)}</div><div>'
            f'<div class="who">{html.escape(name)}</div>'
            f'<div class="sub">{html.escape(list_names(res["people"]))}</div></div></div>')


def thread_html(items):
    """items: (side, big, text) with side 'in' (the analyzer) or 'out' (you asking)."""
    out = []
    for i, (side, big, text) in enumerate(items):
        body = (f'<span class="big">{html.escape(big)}</span>' if big else "") + html.escape(text)
        if side == "out":
            body += '<span class="ticks" aria-label="read">✓✓</span>'
        out.append(f'<div class="b {side}" style="--i:{i}">{body}</div>')
    return '<div class="thread">' + "".join(out) + "</div>"


def note_html(lines):
    return '<ul class="fine">' + "".join(f"<li>{html.escape(n)}</li>" for n in lines) + "</ul>"


def fig_html(fig):
    if fig is None:
        return ""
    return '<div class="card">' + fig.to_html(full_html=False, include_plotlyjs=False,
                                              config={"displaylogo": False, "responsive": True}) + "</div>"


def table_html(df, index=True):
    return '<div class="card">' + df.to_html(index=index, border=0, escape=True) + "</div>"


def prepare(df, info, gap, start=None, end=None, anon=False):
    """Date filter -> members -> optional anonymizing -> enrich. Returns (df, info)."""
    info = dict(info, gap=gap, anon=anon)
    if start:
        df = df[df["ts"] >= pd.Timestamp(start)]
    if end:
        df = df[df["ts"] < pd.Timestamp(end) + pd.Timedelta(days=1)]
    if df[df["sender"] != SYSTEM].empty:
        raise ValueError("No messages in the selected date range.")
    info["members_added"], info["members_gone"] = members_from_system(df)
    if anon:
        df, mapping = anonymize(df, info["members_added"] | info["members_gone"])
        info["members_added"] = {mapping.get(n, n) for n in info["members_added"]}
        info["members_gone"] = {mapping.get(n, n) for n in info["members_gone"]}
    return enrich(df.reset_index(drop=True), gap), info


def story(msgs, people, table, replies, streak, shifts):
    """The opening chat thread: the most telling numbers as (side, big, text) message bubbles."""
    s = [("in", f"{len(msgs):,}", f"messages over {msgs['ts'].dt.normalize().nunique():,} active days.")]
    if len(people) >= 2:
        s.append(("in", "", f"{people[0]} sends the most: {table.loc[people[0], 'Share']:.0%} of everything."))
    fast = table.loc[table["Replies"] >= 5, "Reply median"].dropna()
    if not fast.empty:
        s += [("out", "", "Who replies fastest?"),
              ("in", fmt_dur(fast.min()), f"is how long {fast.idxmin()} usually takes, the quickest here. "
                                          f"Across everyone it's {fmt_dur(replies['secs'].median())}.")]
    day, hour = msgs.groupby([msgs["ts"].dt.day_name(), msgs["ts"].dt.hour]).size().idxmax()
    when = {0: "midnight", 12: "noon"}.get(hour, f"{hour % 12} {'am' if hour < 12 else 'pm'}")
    s += [("out", "", "When are we most active?"), ("in", "", f"{day}s around {when}.")]
    n, s_from, s_to = streak
    if n > 1:
        s.append(("in", f"{n} days", f"in a row was the longest streak, from {s_from:%d %b} to {s_to:%d %b %Y}."))
    if shifts:
        big = max(shifts, key=lambda x: abs(x["before"] - x["after"]))
        way = "down" if big["after"] < big["before"] else "up"
        s += [("out", "", "Has anything changed?"),
              ("in", f"{big['change']:+.0f}%".replace("-", "−"),
               f"in weekly messages from the week of {big['week']:%d %b %Y}, {way} from "
               f"{big['before']:.0f} to {big['after']:.0f} a week.")]
    return s


def analyze(df, info):
    """Run every analysis once. Returns a dict of figures, tables and notes."""
    people = people_of(df)
    msgs = df[~df["is_system"]]
    replies = reply_times(df)
    table = person_table(df, replies)
    streak, s_from, s_to = longest_streak(df)
    res = {"people": people, "is_group": len(people) > 2, "start": df["ts"].min(), "end": df["ts"].max()}

    res["heatmap"], res["timeline"] = chart_heatmap(df), chart_timeline(df)

    shown = table.copy()
    for c in ["Share", "Late-night", "Questions"]:
        shown[c] = shown[c].map(lambda v: f"{v:.0%}")
    for c in ["Reply median", "Reply p90"]:
        shown[c] = shown[c].map(fmt_dur)
    for c in ["Messages", "Media", "Links", "Started", "Ended", "Double-texts", "Replies"]:
        shown[c] = shown[c].astype(int)
    shown["Median words"] = shown["Median words"].map(lambda v: "-" if pd.isna(v) else f"{v:g}")
    res["people_table"] = shown
    res["people_note"] = (f"Late-night = 00:00–{LATE_NIGHT_END_HOUR:02d}:00. "
                          "Double-texts = runs of 2+ messages in a row by the same person. "
                          "Questions = share of messages containing “?”.")

    res["initiators"] = chart_initiators(table)
    res["replies"], res["reply_fits"] = chart_replies(replies, people)

    counts = word_counts(df)
    all_words = Counter()
    for c in counts.values():
        all_words.update(c)
    all_emoji = Counter(e for t in msgs["text"] for e in emojis(t))
    res["top_words"] = chart_bars(all_words, "Top words", SERIES[0])
    res["top_emoji"] = chart_bars(all_emoji, "Top emoji", SERIES[2])
    res["distinctive"] = None
    if len(people) >= 2:
        dist = distinctive_words(counts)
        rows = []
        for p in people[:MAX_PEOPLE]:
            top_e = Counter(e for t in msgs.loc[msgs["sender"] == p, "text"] for e in emojis(t)).most_common(5)
            rows.append({"Person": p,
                         "Distinctive words": ", ".join(w for w, _ in dist.get(p, [])) or "-",
                         "Favourite emoji": " ".join(e for e, _ in top_e) or "-"})
        res["distinctive"] = pd.DataFrame(rows)
    res["distinctive_note"] = ("Distinctive words = words a person uses much more than everyone else "
                               f"(smoothed log-odds ratio, z > 1.96, used at least {MIN_DISTINCTIVE_COUNT} times).")
    res["lengths"] = chart_lengths(df, people)

    res["weekly"], shifts = chart_weekly(df)
    res["weekly_notes"] = [f"From the week of {s['week']:%d %b %Y}, the chat went from {s['before']:.0f} to "
                           f"{s['after']:.0f} messages a week ({s['change']:+.0f}%)." for s in shifts]

    if res["is_group"]:
        res["markov"] = chart_markov(df, people)
        added, gone = info["members_added"], info["members_gone"]
        silent = sorted(added - gone - set(people))
        member_counts = list(table["Messages"]) + [0] * len(silent)
        low = [p for p in people if table.loc[p, "Share"] < LURKER_SHARE]
        lurkers = [f"{p} ({int(table.loc[p, 'Messages'])} messages)" for p in low] + [f"{p} (0 messages)" for p in silent]
        res["group_story"] = [
            ("in", f"{gini(member_counts):.2f}", "is how unevenly the talking is shared (Gini). 0 would mean "
                                                 "everyone talks equally; 1 that one person does all of it."),
            ("in", "", f"Barely heard from: {list_names(lurkers)}." if lurkers else
                       f"Nobody is lurking. Everyone sends at least {LURKER_SHARE:.0%} of the messages."),
        ]

    res["story"] = story(msgs, people, table, replies, (streak, s_from, s_to), shifts)

    start, end = res["start"], res["end"]
    notes = [
        f"Period: {start:%d %b %Y} – {end:%d %b %Y}. Session gap: {info['gap']:g} hours "
        f"({df['session_id'].nunique():,} sessions).",
        f"Dates read as {'day/month' if info['dayfirst'] else 'month/day'}. "
        f"{info['bad_timestamps']} lines had unreadable timestamps and were skipped.",
        f"{int(df['is_system'].sum())} system messages, {int(df['is_media'].sum())} media, "
        f"{int(df['is_deleted'].sum())} deleted, {int(df['is_edited'].sum())} edited.",
        "Media and system messages count as turns (they can start or end a session and split a burst). "
        "System messages are never counted as a reply and are left out of per-person tables.",
        "Reply time = gap at each change of sender within a session (last message of one person → "
        "first message of the next). Medians and 90th percentiles only, never means.",
        "Sentiment is not analysed: English sentiment tools are unreliable on Hinglish.",
    ]
    if info["anon"]:
        notes.append("Anonymized: names are replaced by letters (A = most active), phone numbers and "
                     "emails are masked. Names of people outside the chat may still appear in words.")
    res["notes"] = notes
    return res


def render_html(res, title):
    """Turn analyze() results into one offline HTML page."""
    parts = [header_html(res, title), thread_html(res["story"]),
             section_html("Activity"), fig_html(res["heatmap"]), fig_html(res["timeline"]),
             section_html("People"), table_html(res["people_table"]), note_html([res["people_note"]]),
             section_html("Conversation dynamics"), fig_html(res["initiators"]), fig_html(res["replies"])]
    if not res["reply_fits"].empty:
        parts.append(table_html(res["reply_fits"], index=False))
    parts += [section_html("Language"),
              '<div class="grid2">' + fig_html(res["top_words"]) + fig_html(res["top_emoji"]) + "</div>"]
    if res["distinctive"] is not None:
        parts += [table_html(res["distinctive"], index=False), note_html([res["distinctive_note"]])]
    parts += [fig_html(res["lengths"]), section_html("Trends"), fig_html(res["weekly"]),
              note_html(res["weekly_notes"] or ["No clear change in weekly activity was detected."])]
    if res["is_group"]:
        parts += [section_html("Group behaviour"), fig_html(res["markov"]), thread_html(res["group_story"])]
    parts += [section_html("About this report"), note_html(res["notes"])]

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>{CSS}</style>
<script>{get_plotlyjs()}</script>
</head><body class="page"><main>
{''.join(parts)}
<p class="footer">Made on this computer with Chat Analyzer. Nothing was uploaded.</p>
</main></body></html>"""


# =============================================================================
# APP (Streamlit) - started by running this file with no arguments
# =============================================================================
# Streamlit-specific overrides on top of the shared theme.
APP_CSS = THEME_CSS + """
header[data-testid="stHeader"] { background: transparent; }
[data-testid="stSidebar"] { border-right: 1px solid var(--line); }
[data-testid="stSidebar"] > div:first-child { background: #0E2025; }
[data-testid="stMainBlockContainer"] { max-width: 1080px; padding-top: 2.6rem; padding-bottom: 5rem; }
[data-testid="stPlotlyChart"], [data-testid="stDataFrame"] {
  background: var(--thread); border: 1px solid var(--line); border-radius: 10px; padding: 8px; }
[data-testid="stFileUploaderDropzone"] { background: rgba(83, 189, 235, 0.06);
  border: 1.5px dashed rgba(83, 189, 235, 0.4); border-radius: 12px; }
[data-testid="stDownloadButton"] button { background: var(--tick) !important; border: 0 !important;
  border-radius: 999px !important; padding: .55rem 1.25rem !important; margin-top: 14px; }
[data-testid="stDownloadButton"] button, [data-testid="stDownloadButton"] button p {
  color: #06212B !important; font-weight: 650 !important; }
[data-testid="stDownloadButton"] button:focus-visible { outline: 2px solid var(--amber); outline-offset: 3px; }
.side-title { font: 600 23px/1.1 var(--display); color: var(--ink); }
.side-sub { font: 13px/1.4 var(--text); color: var(--mute); margin-top: 4px; }
.side-h { font: 600 16px/1.2 var(--display); color: var(--ink); margin-top: 22px; }
"""

LANDING_HTML = """
<div class="chathead"><div class="avatar">CA</div><div><div class="who">Chat Analyzer</div>
<div class="sub">on this computer only</div></div></div>
<div class="thread">
<div class="b in" style="--i:0">Send me an exported WhatsApp chat and I'll show you how the conversation
really works: who starts it, who replies fastest, and what everyone says most.</div>
<div class="b out" style="--i:1">How do I get the file?<span class="ticks" aria-label="read">✓✓</span></div>
<div class="b in" style="--i:2">In WhatsApp:<ol>
<li>Open the chat.</li>
<li>Android: tap ⋮, then More, then Export chat. iPhone: tap the chat name, then Export Chat.</li>
<li>Choose Without media.</li>
<li>Drop the .zip or .txt into the box on the left.</li></ol></div>
<div class="b out" style="--i:3">Does my chat get uploaded anywhere?<span class="ticks" aria-label="read">✓✓</span></div>
<div class="b in" style="--i:4">No. Everything runs on this computer, and nothing is sent over the internet.</div>
</div>
"""


def run_app():
    import streamlit as st

    st.set_page_config(page_title="Chat Analyzer", page_icon="💬", layout="wide", initial_sidebar_state="expanded")
    st.markdown(f"<style>{APP_CSS}</style>", unsafe_allow_html=True)

    @st.cache_data(show_spinner=False, max_entries=3)
    def load(data):
        return parse_chat(chat_text(data))

    @st.cache_data(show_spinner=False, max_entries=3)
    def run(data, gap, start, end, anon):
        df, info = load(data)
        df, info = prepare(df, info, gap, start, end, anon)
        return analyze(df, info)

    with st.sidebar:
        st.html('<div class="side-title">Chat Analyzer</div>'
                '<div class="side-sub">Runs on this computer only.</div><div class="side-h">Chat file</div>')
        up = st.file_uploader("Exported chat (.zip or .txt)", type=["zip", "txt"])
        st.html('<div class="side-h">Settings</div>')
        gap = st.slider("Session gap (hours)", 1, 24, int(SESSION_GAP_HOURS),
                        help="A new conversation starts after this much silence.")
        anon = st.toggle("Anonymize names (A, B, C…)", help="Use this before sharing the report.")

    if up is None:
        st.html(LANDING_HTML)
        return

    data = up.getvalue()
    try:
        with st.spinner("Reading chat…"):
            raw, _ = load(data)
    except (ValueError, zipfile.BadZipFile) as e:
        st.error(f"Couldn't read this file. {e}")
        return
    first, last = raw["ts"].min().date(), raw["ts"].max().date()
    with st.sidebar:
        st.html('<div class="side-h">Dates</div>')
        picked = st.date_input("Date range", (first, last), min_value=first, max_value=last)
    start, end = (picked if len(picked) == 2 else (picked[0], last)) if isinstance(picked, tuple) else (picked, last)

    try:
        with st.spinner("Analysing…"):
            res = run(data, gap, start, end, anon)
    except ValueError as e:
        st.warning(str(e))
        return

    name = "Anonymized chat" if anon else chat_title(Path(up.name).stem)
    st.html(header_html(res, name))
    st.download_button("Download report (HTML)", render_html(res, name),
                       file_name=("chat_anon" if anon else Path(up.name).stem) + "_report.html",
                       mime="text/html")
    st.html(thread_html(res["story"]))

    plot = lambda fig: fig is not None and st.plotly_chart(fig, width="stretch", config={"displaylogo": False})
    note = lambda lines: st.html(note_html(lines))

    st.html(section_html("Activity"))
    plot(res["heatmap"])
    plot(res["timeline"])

    st.html(section_html("People"))
    st.dataframe(res["people_table"], width="stretch")
    note([res["people_note"]])

    st.html(section_html("Conversation dynamics"))
    plot(res["initiators"])
    plot(res["replies"])
    if not res["reply_fits"].empty:
        st.dataframe(res["reply_fits"], width="stretch", hide_index=True)

    st.html(section_html("Language"))
    left, right = st.columns(2)
    with left:
        plot(res["top_words"])
    with right:
        plot(res["top_emoji"])
    if res["distinctive"] is not None:
        st.dataframe(res["distinctive"], width="stretch", hide_index=True)
        note([res["distinctive_note"]])
    plot(res["lengths"])

    st.html(section_html("Trends"))
    plot(res["weekly"])
    note(res["weekly_notes"] or ["No clear change in weekly activity was detected."])

    if res["is_group"]:
        st.html(section_html("Group behaviour"))
        plot(res["markov"])
        st.html(thread_html(res["group_story"]))

    st.html(section_html("About this report"))
    note(res["notes"])


def launch_app():
    """Start the Streamlit app on this computer only (localhost), with usage statistics off."""
    import subprocess
    import sys
    here = Path(__file__).resolve()
    # cwd = this folder so .streamlit/config.toml (dark theme) is picked up.
    subprocess.run([sys.executable, "-m", "streamlit", "run", str(here),
                    "--server.address", "localhost", "--browser.gatherUsageStats", "false",
                    "--client.toolbarMode", "minimal", "--logger.hideWelcomeMessage", "true"], cwd=here.parent)


def in_streamlit():
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx
        return get_script_run_ctx(suppress_warning=True) is not None
    except ImportError:
        return False


# =============================================================================
# COMMAND LINE - run with a chat file to write an HTML report directly
# =============================================================================
def main(argv=None):
    ap = argparse.ArgumentParser(description="Analyze an exported WhatsApp chat (.txt or .zip) into an HTML report. "
                                             "Run with no arguments to open the app instead.")
    ap.add_argument("chat", help="exported chat .txt or .zip file")
    ap.add_argument("--gap", type=float, default=SESSION_GAP_HOURS, help="session gap in hours (default 6)")
    ap.add_argument("--from", dest="start", help="first date to include, YYYY-MM-DD")
    ap.add_argument("--to", dest="end", help="last date to include, YYYY-MM-DD")
    ap.add_argument("--anon", action="store_true", help="replace names with A, B, C...")
    ap.add_argument("-o", "--out", help="output HTML (default: <chat>_report.html next to the chat)")
    args = ap.parse_args(argv)

    path = Path(args.chat)
    try:
        df, info = parse_chat(chat_text(path.read_bytes()))
        df, info = prepare(df, info, args.gap, args.start, args.end, args.anon)
    except (ValueError, zipfile.BadZipFile) as e:
        raise SystemExit(str(e))
    title = "Anonymized chat" if args.anon else chat_title(path.stem)
    report = render_html(analyze(df, info), title)
    out = Path(args.out) if args.out else path.with_name(path.stem + ("_anon" if args.anon else "") + "_report.html")
    out.write_text(report, encoding="utf-8")
    print(f"Report written to {out.resolve()}")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        main()
    elif in_streamlit():
        run_app()
    else:
        launch_app()
