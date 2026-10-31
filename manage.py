#!/usr/bin/env python
import os
import sys


def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "stash.settings")
    args = sys.argv
    # Demo mode: fake students in a separate, throwaway data folder. Never touches your real data.
    if len(args) >= 2 and args[1] == "demo":
        from platformdirs import user_data_dir
        os.environ["STASH_DATA_DIR"] = user_data_dir("STASH Demo", "stash")
        os.environ["STASH_DEMO"] = "1"
    # Always bind to this computer only, even if an address isn't given.
    if len(args) >= 2 and args[1] == "runserver":
        addr = [a for a in args[2:] if not a.startswith("-")]
        if not addr:
            args = args + ["127.0.0.1:8000"]
        elif not addr[0].startswith(("127.0.0.1", "localhost", "[::1]")):
            sys.exit("STASH only runs on this computer. Use: python manage.py runserver 127.0.0.1:8000")
    from django.core.management import execute_from_command_line
    execute_from_command_line(args)


if __name__ == "__main__":
    main()
