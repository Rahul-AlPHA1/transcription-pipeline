# Simple Transcription Pipeline

This is a small, practical transcription pipeline for turning audio into timestamped text.

It uses `faster-whisper`, an open-source implementation of OpenAI Whisper, for real transcription. It also has a `--mock` mode so the pipeline shape can be tested without downloading a model.

## Run it

```bash
pip install -r requirements.txt
python transcribe.py meeting.mp3 --output transcript.json
```

For a dry run without a model:

```bash
python transcribe.py meeting.wav --mock --output transcript.json
```

## Output shape

```json
{
  "source_file": "meeting.mp3",
  "language": "en",
  "duration_seconds": 812.42,
  "segments": [
    {
      "start": 0.0,
      "end": 4.7,
      "text": "Thanks everyone for joining today."
    }
  ],
  "text": "Thanks everyone for joining today."
}
```

## Engineering Answers

### 1. How would I implement a service or script that accepts an audio file?

I would start with a CLI because it is simple to test and easy to wrap inside a web service later.

The script accepts a file path:

```bash
python transcribe.py input.mp3 --output transcript.json
```

Before doing any transcription, it checks that the file exists and that the extension is one we expect, such as `.wav`, `.mp3`, `.m4a`, `.flac`, `.ogg`, or `.webm`.

For a production service, I would expose the same logic through an HTTP endpoint:

```http
POST /transcriptions
Content-Type: multipart/form-data
```

The uploaded file would be stored temporarily, passed into the same pipeline, then removed after the transcript is written.

### 2. How would I transcribe spoken language into text?

I would use an existing speech-to-text model instead of training one from scratch. For this version, I chose `faster-whisper` because it is open source, reliable, and returns segment-level timestamps naturally.

The pipeline is:

1. Receive audio.
2. Normalize it to a consistent format.
3. Send it to the speech-to-text model.
4. Collect each returned segment.
5. Save the final transcript as JSON.

In real use, I would pick the model size based on the business need:

- `tiny` or `base` for fast, cheap drafts.
- `small` or `medium` for a better quality/speed balance.
- `large-v3` when accuracy matters more than runtime.

### 3. How would I return the transcription with timestamps per segment?

The output should not just be one big text block. Downstream systems usually need structure, so I return both:

- `segments`: each chunk of speech with `start`, `end`, and `text`.
- `text`: the full transcript joined together for simple search or display.

Example:

```json
{
  "segments": [
    {
      "start": 12.4,
      "end": 18.9,
      "text": "The customer asked us to follow up next week."
    }
  ],
  "text": "The customer asked us to follow up next week."
}
```

That makes it usable for captions, search indexing, summaries, speaker review, CRM notes, or QA workflows.

### 4. How do I handle different audio formats?

I do not want the model to deal with every possible audio shape directly. I normalize everything first.

The script uses FFmpeg to convert the input into:

- WAV container
- mono audio
- 16 kHz sample rate

That gives the transcription model a predictable input no matter whether the user uploads MP3, WAV, M4A, FLAC, OGG, AAC, or WEBM.

If FFmpeg is not available, the script can still work with WAV files, but for production I would make FFmpeg a required dependency. It is the practical standard for audio format handling.

### 5. How do I deal with long audio files?

Long audio needs to be split. Sending a two-hour file through the model in one pass is slower, harder to retry, and easier to fail.

The script chunks long audio into fixed windows, for example 10 minutes each, with a small overlap between chunks. The overlap matters because words can sit right on the boundary between two chunks.

After transcription, the script adds the chunk offset back to each segment timestamp. So if a segment starts 8 seconds into chunk 3, and chunk 3 starts at 1,200 seconds, the final timestamp becomes 1,208 seconds.

For production, I would also add:

- background jobs for long files
- progress status
- retries per chunk
- storage for intermediate files
- duplicate cleanup around chunk overlaps
- a maximum upload size

### 6. What would I do with the transcript downstream?

I would keep the JSON structure stable so other systems can depend on it.

Good downstream uses include:

- full-text search
- subtitles or captions
- summarization
- action item extraction
- topic tagging
- compliance review
- analytics on call recordings

The important decision is to preserve timestamps, because once timestamps are lost, it is much harder to connect a sentence back to the exact moment in the original audio.

## Why this design?

I kept the pipeline boring on purpose. The hard part is not inventing a new speech model; it is making the file handling, timestamps, long-audio behavior, and output format predictable.

The model can always be swapped later. The pipeline contract should stay stable.
