# Part 2: System Design

## 1. How would you handle concurrent uploads?

I would not process every upload directly inside the web request. If many users upload audio at the same time, the API should accept the file, create a transcription job, and return a `job_id`.

The actual transcription should run in background workers.

A simple flow would be:

1. User uploads an audio file.
2. API stores the file.
3. API creates a job record with status `queued`.
4. A worker picks up the job.
5. Worker transcribes the audio.
6. Worker saves the transcript and marks the job as `completed`.

For concurrency, I would use a queue such as Redis Queue, Celery, RabbitMQ, or AWS SQS. This keeps the API fast and prevents the server from crashing when multiple large files arrive at once.

I would also add limits like:

- maximum upload size
- maximum audio duration
- per-user rate limits
- maximum number of active jobs per user

This makes the system predictable even when traffic increases.

## 2. How would you store audio and transcripts?

I would store audio files in object storage, not directly in the application server.

Good options are:

- AWS S3
- Google Cloud Storage
- Azure Blob Storage
- local storage for a small prototype

The database would store metadata, not the large audio file itself.

Example database fields:

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

For transcripts, I would store structured JSON because downstream systems need more than plain text.

Example transcript:

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

The JSON transcript can be stored in a database column, a separate transcript table, or as a JSON file in object storage. For search, I would index the final text in something like PostgreSQL full-text search, Elasticsearch, or OpenSearch.

## 3. How do you retry or recover failed transcriptions?

I would treat transcription as a job with clear states:

```text
queued
processing
completed
failed
retrying
```

If a job fails, I would save the error message and retry it automatically. I would not retry forever. A reasonable setup is 3 retries with exponential backoff.

Example:

- first retry after 1 minute
- second retry after 5 minutes
- third retry after 15 minutes

If the full audio is split into chunks, I would retry only the failed chunk instead of restarting the whole transcription. This is important for long audio files because reprocessing a two-hour recording from the beginning would waste time and money.

I would also make the job idempotent. That means if the same job runs twice by mistake, it should not create duplicate transcripts or corrupt the final output.

For recovery, I would keep enough information in the database to continue:

- original audio file location
- chunk list
- completed chunks
- failed chunks
- retry count
- final transcript status

## 4. How would you expose this as an API?

I would expose it as a small REST API.

The main endpoints would be:

```http
POST /transcriptions
```

Uploads an audio file and creates a transcription job.

Response:

```json
{
  "job_id": "job_123",
  "status": "queued"
}
```

```http
GET /transcriptions/{job_id}
```

Returns the current job status.

Response while processing:

```json
{
  "job_id": "job_123",
  "status": "processing",
  "progress": 45
}
```

Response when completed:

```json
{
  "job_id": "job_123",
  "status": "completed",
  "transcript_url": "/transcriptions/job_123/result"
}
```

```http
GET /transcriptions/{job_id}/result
```

Returns the final transcript with timestamps.

```http
DELETE /transcriptions/{job_id}
```

Deletes the job and optionally deletes the stored audio and transcript.

For security, I would add authentication, file validation, rate limiting, and signed URLs for private audio files.

## 5. Please share the source code in a Git repo

I would share the implementation in a Git repository with a simple structure:

```text
transcription_pipeline_submission/
  transcribe.py
  requirements.txt
  README.md
  PART2_SYSTEM_DESIGN.md
  sample_transcript.json
```

The repo should include:

- source code
- setup instructions
- example command
- sample output
- system design answers

In this submission, the code is already organized this way and can be committed to Git.

Example Git commands:

```bash
git init
git add .
git commit -m "Add transcription pipeline submission"
```

If this needs to be uploaded online, the next step would be creating a GitHub repository and pushing it:

```bash
git remote add origin https://github.com/USERNAME/transcription-pipeline.git
git branch -M main
git push -u origin main
```
