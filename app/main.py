"""Local-dev launcher (not used by Docker).

Runs both the public and admin apps as subprocesses so a single
`python -m app.main` serves both ports during development. Docker instead runs
`app.public` and `app.admin` as two separate services.
"""
#region: imports
import subprocess
import sys
#endregion


#region: launcher
def main() -> None:
    procs = [
        subprocess.Popen([sys.executable, "-m", "app.public"]),
        subprocess.Popen([sys.executable, "-m", "app.admin"]),
    ]
    try:
        for proc in procs:
            proc.wait()
    except KeyboardInterrupt:
        for proc in procs:
            proc.terminate()
        for proc in procs:
            proc.wait()


if __name__ == "__main__":
    main()
#endregion
