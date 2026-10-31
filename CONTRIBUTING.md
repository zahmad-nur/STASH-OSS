# Contributing to STASH

Thanks for helping. STASH is for F-1 students, so the best contributions start from a real situation:
a kind of I-20 it misreads, a date it gets wrong, something you wish it tracked.

## Ground rules

- **Fake data only.** Never commit, attach or paste a real I-20, a real SEVIS ID, or a screenshot of real
  documents. Use the demo (`python manage.py demo`), the fake generator (`scripts/make_sample_i20.py`), or the
  masked output of `python manage.py structure_check`.
- **Local only.** STASH makes no network requests. Changes that add analytics, cloud services, remote fonts,
  CDNs or telemetry won't be accepted.
- **Encrypted by default.** Anything read from a document is stored encrypted, like the existing fields.
- **Never change the original.** Uploads stay exactly as uploaded; changes become new versions or corrections.

## Setting up

Follow the Quick start in the README, then run the tests:

```bash
python manage.py test tests
```

All tests should pass before you open a pull request. Add a test for any new behaviour, using the fake
generator in `scripts/make_sample_i20.py`.

## Pull requests

- Keep each pull request to one change, and explain the situation it fixes.
- If it touches how a field is read, include the masked `structure_check` output of the layout it handles.
- Dependencies are pinned. If you add or update one, say why.

## License of contributions

STASH is licensed under the AGPL-3.0. By opening a pull request, you agree that your contribution is licensed
under the same terms.

## Security

Found a vulnerability? Please report it privately, not in an issue or pull request. See [SECURITY.md](SECURITY.md).
