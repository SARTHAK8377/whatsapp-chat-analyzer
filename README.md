# WhatsApp Chat Analyzer

See how a WhatsApp chat really works: who starts conversations, who replies fastest, when the chat is busiest, the words and emoji each person uses, and how activity changes over time.

Everything runs on your own computer. Your chat is never uploaded anywhere.

## Download (Windows)

1. Go to [Releases](../../releases) and download **Chat Analyzer.exe**.
2. Double-click it. Windows may say "Windows protected your PC" because the app isn't signed. Click **More info**, then **Run anyway**.
3. A black window opens, and the app opens in your browser after up to a minute. Keep the black window open while you use it, and close it when you're done.

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

## Run from source

Needs Python 3.10 or newer.

```bash
pip install -r requirements.txt
python whatsapp_analyzer.py
```

This opens the app in your browser. To write an HTML report directly instead:

```bash
python whatsapp_analyzer.py chat.zip --anon
```

Options: `--gap 6` (hours of silence that start a new conversation), `--from 2024-01-01`, `--to 2024-12-31`, `--anon`, `-o report.html`.

On Windows you can also double-click `Start Analyzer.bat`. To build the EXE yourself, run `build_exe.bat` (needs `pip install pyinstaller`; takes about 20 minutes).

## Try it without your own chat

`samples/` has made-up chats (no real people) and the script that generates them:

```bash
python samples/make_samples.py samples
```

## Privacy

- Analysis happens on your computer. The app only accepts connections from your own machine.
- Streamlit's usage statistics are turned off.
- Sentiment is not analysed, because English sentiment tools are unreliable on Hinglish.
