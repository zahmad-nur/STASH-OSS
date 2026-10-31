# Security in STASH

STASH stores immigration documents, so it is built on one rule: nothing readable ever sits on disk, and nothing leaves the computer.

## Reporting a vulnerability

Please **don't** open a public issue. Report it privately from this repo's **Security** tab →
**Report a vulnerability** (GitHub private vulnerability reporting). Include what you found, how to reproduce it
with fake data, and what an attacker could do with it.

Reports are answered on a best-effort basis; this is a spare-time project. Fixes go to the `main` branch, which is
the only supported version during the preview.

## What it protects against

| Threat | Protection |
| --- | --- |
| Lost or stolen laptop | Files and fields are encrypted with AES-256-GCM. The key exists only in memory while the app is unlocked. |
| Someone else using your computer | Passphrase lock, auto-lock after 15 minutes idle, unlock cookie tied to one browser |
| Accidentally pushing your data to GitHub | The data folder must sit outside the code folder; `.gitignore` blocks PDFs, images and keys anyway |
| Another device on your Wi-Fi | The server binds to 127.0.0.1, and the app rejects any request that isn't from this computer |
| A malformed or malicious PDF | Files are type-checked by content, size-capped at 20 MB, and read in a separate isolated process with a time limit |
| Browser caching | Every page and file is sent with `Cache-Control: no-store` |
| Logs | Logs record request paths and errors only, never field values or file contents |

## What it does not protect against

- **Malware on your computer.** Software that can read your screen or memory while STASH is unlocked can read what you see. Keep your OS updated.
- **A weak passphrase.** Argon2id makes each guess slow, but a short or common passphrase can still be guessed. Use four or more random words.
- **Losing both your passphrase and recovery key.** No back door exists, so the data cannot be recovered.

Python can't reliably erase memory, so the key may linger in RAM until the process exits. Quit the server when you're done.

## How the keys work

1. On setup, STASH generates a random 256-bit data key.
2. Your passphrase is run through Argon2id (64 MiB, 3 passes) to make a key that wraps the data key. Only the wrapped copy is saved, in `keys.json`.
3. A random recovery key wraps the same data key. It is shown once and never stored.
4. Separate sub-keys are derived for files, fields and duplicate detection, so a weakness in one use doesn't affect the others.
5. Each encrypted value is bound to its own record (authenticated data). An encrypted field can't be moved onto another document without decryption failing.

Changing your passphrase only re-wraps the data key. Nothing else needs re-encrypting.

## What is stored, and how

| Item | Stored as |
| --- | --- |
| Uploaded and signed files | Encrypted, under random file names in `files/` |
| Everything read from your documents (fields, work authorization, corrections, notes, signature checks) | One encrypted blob per document in the database |
| Your name and greeting | Encrypted |
| Display IDs, versions, dates uploaded | Plain. These are needed to list documents and reveal nothing about your status |
| Duplicate fingerprints | A keyed hash only your vault can compute |

## About signing

Adding your signature creates a new version. The original upload is never changed. If the DSO signed the I-20 digitally, adding your signature changes the file, and PDF viewers may report it as modified after signing. That's expected, and the original stays available as v1.

## Dependencies

Versions are pinned in `requirements.txt`. Dependabot opens pull requests for updates, and nothing is merged
automatically. A software bill of materials (SBOM) can be exported from the repo's **Insights → Dependency graph**.

## Before sharing code or screenshots

Only commit fake sample data. Run `git status` before every push, and check that nothing from your data folder
appears. Take screenshots in demo mode only.
