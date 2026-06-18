# Transcription Pipeline Submission

GitHub repo: https://github.com/Rahul-AlPHA1/transcription-pipeline

## Problem Statement

Build a simple transcription pipeline that converts audio input into text and processes the result for downstream use.

Allowed:

- Any open-source speech-to-text library or API
- Any programming language
- Mock data where needed

The focus is on engineering decisions, not training a model from scratch.

## What I Built

I built a small Python transcription pipeline using `faster-whisper`, an open-source Whisper implementation.

The script accepts an audio file, normalizes it, transcribes it, and returns structured JSON with timestamps for each segment.

I also added a `--mock` mode so the pipeline can be tested without downloading a speech model.

## Project Files

```text
transcribe.py
requirements.txt
README.md
sample_transcript.json
.gitignore
```

## How To Run

Install dependencies:

```bash
pip install -r requirements.txt
```

Run transcription:

```bash
python transcribe.py meeting.mp3 --output transcript.json
```

Run with mock data:

```bash
python transcribe.py meeting.wav --mock --output transcript.json
```

## Example Output

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

# Part 1: Transcription Pipeline

## 1. Implement a service or script that accepts an audio file

I implemented this as a Python command-line script called `transcribe.py`.

The script accepts an audio file path as input:

```bash
python transcribe.py input.mp3 --output transcript.json
```

Before transcription starts, the script checks that the file exists and that the format is supported.

Supported formats include:

- WAV
- MP3
- M4A
- AAC
- FLAC
- OGG
- WEBM

For a production service, I would keep the same pipeline logic and expose it through an upload API, for example:

```http
POST /transcriptions
```

That API would accept the audio file, store it temporarily, create a transcription job, and return a job ID.

## 2. Implement a service or script that transcribes spoken language into text

For speech-to-text, I used `faster-whisper`.

I chose it because it is open source, practical, and already handles speech recognition well. Since the assignment is focused on engineering decisions, I did not train a model from scratch.

The pipeline works like this:

```text
audio file -> normalize audio -> transcribe with Whisper -> return structured JSON
```

In real use, I would choose the model size based on the need:

- `tiny` or `base` for fast draft transcription
- `small` or `medium` for a good balance of speed and accuracy
- `large-v3` when accuracy matters more than speed

The script also includes mock mode:

```bash
python transcribe.py input.wav --mock
```

This is useful for testing the pipeline without installing or downloading a model.

## 3. Implement a service or script that returns the transcription with timestamps per segment

The script returns the transcript as structured JSON.

Each segment includes:

- `start`: when the segment starts
- `end`: when the segment ends
- `text`: the spoken text in that segment

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

This format is better than only returning one big paragraph because downstream systems can use it for captions, search, summaries, review tools, and analytics.

## 4. How do you handle different audio formats?

I handle different audio formats by normalizing every file before transcription.

The script uses FFmpeg to convert the input into:

```text
WAV format
mono channel
16 kHz sample rate
```

This makes the input predictable for the transcription model. It does not matter if the user uploads MP3, WAV, M4A, FLAC, OGG, AAC, or WEBM. The pipeline converts it to a clean format first.

If FFmpeg is not installed, the script can still handle WAV files in a limited way, but for production I would require FFmpeg because it is the standard tool for audio conversion.

## 5. How do you deal with long audio files?

For long audio files, I split the audio into smaller chunks.

For example, a two-hour file can be split into 10-minute chunks. I also add a small overlap between chunks so words are not cut off at the boundary.

After each chunk is transcribed, the script adjusts the timestamps back to the original audio timeline.

Example:

```text
chunk starts at 1200 seconds
model says segment starts at 8 seconds
final timestamp becomes 1208 seconds
```

This makes the final transcript line up correctly with the original audio.

For production, I would also add:

- background jobs
- progress tracking
- retries per chunk
- chunk-level recovery
- upload size limits
- duration limits

# Part 2: System Design

## 6. How would you handle concurrent uploads?

I would not process transcription directly inside the upload request.

If many users upload audio files at the same time, the API should accept the file, store it, create a job, and return a `job_id`.

The actual transcription should run in background workers.

A simple flow would be:

```text
User uploads audio
API stores the file
API creates a queued job
Worker picks up the job
Worker transcribes the audio
Worker saves the transcript
Job status becomes completed
```

For this, I would use a queue such as:

- Celery
- Redis Queue
- RabbitMQ
- AWS SQS

This keeps the API fast and prevents the server from getting overloaded when multiple large files are uploaded together.

I would also add:

- maximum upload size
- maximum audio duration
- per-user rate limits
- maximum active jobs per user

## 7. How would you store audio and transcripts?

I would store audio files in object storage, not directly inside the application server.

Good options are:

- AWS S3
- Google Cloud Storage
- Azure Blob Storage
- local storage for a prototype

The database would store metadata like:

```text
job_id
user_id
audio_file_url
audio_format
duration_seconds
status
created_at
updated_at
error_message
```

For transcripts, I would store structured JSON.

Example:

```json
{
  "text": "Full transcript here",
  "segments": [
    {
      "start": 0.0,
      "end": 4.5,
      "text": "Hello, welcome to the meeting."
    }
  ]
}
```

This is useful because downstream systems usually need both the full text and the timestamps.

For search, I would index the transcript text in PostgreSQL full-text search, Elasticsearch, or OpenSearch.

## 8. How do you retry or recover failed transcriptions?

I would treat every transcription as a job with clear states:

```text
queued
processing
completed
failed
retrying
```

If a job fails, I would save the error message and retry it automatically.

I would not retry forever. A reasonable setup is 3 retries with exponential backoff:

```text
first retry after 1 minute
second retry after 5 minutes
third retry after 15 minutes
```

For long audio files, I would retry only the failed chunk instead of starting the whole transcription again. This is important because reprocessing a two-hour file from the beginning would waste time and cost.

I would also make the job idempotent. That means if the same job runs twice by mistake, it should not create duplicate transcripts or corrupt the result.

To recover properly, I would store:

- original audio file location
- chunk list
- completed chunks
- failed chunks
- retry count
- final transcript status

## 9. How would you expose this as an API?

I would expose this as a small REST API.

Upload audio:

```http
POST /transcriptions
```

Response:

```json
{
  "job_id": "job_123",
  "status": "queued"
}
```

Check job status:

```http
GET /transcriptions/{job_id}
```

Response while processing:

```json
{
  "job_id": "job_123",
  "status": "processing",
  "progress": 45
}
```

Get final transcript:

```http
GET /transcriptions/{job_id}/result
```

Response:

```json
{
  "job_id": "job_123",
  "status": "completed",
  "text": "Full transcript here",
  "segments": [
    {
      "start": 0.0,
      "end": 4.5,
      "text": "Hello, welcome to the meeting."
    }
  ]
}
```

I would also add:

- authentication
- file validation
- rate limiting
- signed URLs for private audio files
- clear error responses

## 10. Please share the source code in a Git repo

The source code is available in this GitHub repository:

https://github.com/Rahul-AlPHA1/transcription-pipeline

The repo includes the implementation, setup instructions, sample output, and all answers in this README.

## Final Engineering Note

The main decision here is to keep the pipeline simple and reliable.

I did not train a speech model from scratch because that is not the goal of this assignment. Instead, I used an existing open-source speech-to-text model and focused on the practical system around it:

- accepting audio files
- handling formats
- chunking long audio
- returning timestamped JSON
- designing for retries
- designing for concurrent uploads
- making the result useful for downstream systems
