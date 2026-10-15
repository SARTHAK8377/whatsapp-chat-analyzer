# WhatsApp Chat Analyzer

See how a WhatsApp chat really works: who starts conversations, who replies fastest, when the chat is busiest, the words and emoji each person uses, and how activity changes over time.

Everything runs on your own computer. Your chat is never uploaded anywhere.

## Quick start (Windows)

1. Install Python 3.10 or newer from [python.org](https://www.python.org/downloads/). Keep the default options, which include the `py` launcher.
2. Download this repo: click the green **Code** button, then **Download ZIP**, and extract it.
3. Double-click **Start Analyzer.bat**. The first time, it installs what it needs (a few minutes). After that, the app opens in your browser.
4. Keep the black window open while you use the app, and close it when you're done.

## Build your own Windows app (.exe)

If you want a single file you can share with people who don't have Python:

1. Do steps 1 and 2 above.
2. Double-click **build_exe.bat**. It installs the tools it needs and builds the app. This takes about 20 minutes.
3. **Chat Analyzer.exe** (about 450 MB) appears in your **Downloads** folder.

Anyone on Windows can then double-click the EXE, with no Python needed. Windows may say "Windows protected your PC" because the app isn't signed: click **More info**, then **Run anyway**. The app opens in the browser after up to a minute.

## Get your chat file

1. Open the chat in WhatsApp.
2. Android: tap ⋮, then More, then Export chat. iPhone: tap the chat name, then Export Chat.
3. Choose **Without media**.
4. Drop the `.zip` or `.txt` into the upload box in the app.

## What you get

- When the chat is active, by weekday and hour, and day by day
- Each person's share of messages, late-night habits, questions and double-texts
- Who starts and ends conversations, and reply times (median and 90th percentile)
- Top words and emoji, and the words each person uses more than anyone else (Hinglish-aware)
- Weekly trend with automatic detection of big changes
- For groups: who speaks after whom, how evenly talking is shared, and who lurks
- An **Anonymize** switch that replaces names with A, B, C before you share anything
- A downloadable HTML report

## Run from the command line (any system)

Needs Python 3.10 or newer. Works on Windows, macOS and Linux.

```bash
pip install -r requirements.txt
python whatsapp_analyzer.py
```

This opens the app in your browser. To write an HTML report directly instead:

```bash
python whatsapp_analyzer.py chat.zip --anon
```

Options: `--gap 6` (hours of silence that start a new conversation), `--from 2024-01-01`, `--to 2024-12-31`, `--anon`, `-o report.html`.

## Try it without your own chat

`samples/` has made-up chats (no real people) and the script that generates them:

```bash
python samples/make_samples.py samples
```

## Privacy

- Analysis happens on your computer. The app only accepts connections from your own machine.
- Streamlit's usage statistics are turned off.
- Sentiment is not analysed, because English sentiment tools are unreliable on Hinglish.
