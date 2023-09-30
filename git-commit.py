import os
import random
import subprocess
import argparse
import time
from datetime import datetime, timedelta


REPO_PATH = os.getcwd()
FILE_NAME = "contribution_log.txt"

START_DATE = "2023-02-17"
END_DATE = "2026-07-08"

MIN_COMMITS_PER_DAY = 15
MAX_COMMITS_PER_DAY = 25

SKIP_WEEKENDS = False

# Co-author used for Pair Extraordinaire. Must be a real GitHub account
# (its "ID+username@users.noreply.github.com" email works best).
# Override with --coauthor "Name <email>".
DEFAULT_COAUTHOR = ""

# Seconds to wait between PRs so GitHub's abuse/rate limits are not tripped.
DEFAULT_SLEEP = 5

# Badge tiers, for reference when picking --count:
#   Pull Shark:          2, 16, 128, 1024 merged PRs
#   Pair Extraordinaire: 1, 10, 24, 48 merged co-authored PRs
#   YOLO:                1 unreviewed merge (single tier)
#   Quickdraw:           1 issue/PR closed within 5 min (single tier)


def run_command(command, repo_path, env=None):
    subprocess.run(
        command,
        cwd=repo_path,
        check=True,
        env=env
    )


def run_output(command, repo_path):
    return subprocess.check_output(command, cwd=repo_path, text=True).strip()


def make_commit(repo_path, commit_date, commit_number, dry_run):
    file_path = os.path.join(repo_path, FILE_NAME)

    if dry_run:
        print(f"Would commit {FILE_NAME} for {commit_date} - commit {commit_number}")
        return

    with open(file_path, "a") as file:
        file.write(f"Contribution on {commit_date} - commit {commit_number}\n")

    commit_datetime = f"{commit_date} 12:{random.randint(10, 59)}:00"

    env = os.environ.copy()
    env["GIT_AUTHOR_DATE"] = commit_datetime
    env["GIT_COMMITTER_DATE"] = commit_datetime

    run_command(["git", "add", FILE_NAME], repo_path, env)
    run_command(["git", "commit", "-m", f"Daily contribution {commit_date}"], repo_path, env)


def run_contributions(args):
    repo_path = os.path.abspath(args.repo)
    if not os.path.isdir(os.path.join(repo_path, ".git")):
        raise SystemExit(f"Not a git repository: {repo_path}")

    start = datetime.strptime(START_DATE, "%Y-%m-%d")
    end = datetime.strptime(END_DATE, "%Y-%m-%d")

    current = start

    while current <= end:
        if SKIP_WEEKENDS and current.weekday() >= 5:
            current += timedelta(days=1)
            continue

        commit_count = random.randint(MIN_COMMITS_PER_DAY, MAX_COMMITS_PER_DAY)
        commit_date = current.strftime("%Y-%m-%d")

        for i in range(commit_count):
            make_commit(repo_path, commit_date, i + 1, dry_run=not args.apply)

        action = "commits done" if args.apply else "commits planned"
        print(f"{commit_date}: {commit_count} {action}")
        current += timedelta(days=1)

    if args.push:
        if not args.apply:
            raise SystemExit("--push requires --apply")
        branch = run_output(["git", "branch", "--show-current"], repo_path)
        run_command(["git", "push", "origin", branch], repo_path)
        print("All commits pushed successfully")


def get_default_branch(repo_path):
    return run_output(
        ["gh", "repo", "view", "--json", "defaultBranchRef",
         "--jq", ".defaultBranchRef.name"],
        repo_path
    )


def make_badge_pr(repo_path, base_branch, index, coauthor, dry_run):
    """One merged PR = +1 Pull Shark, +1 Pair Extraordinaire (if coauthored),
    and the first unreviewed self-merge also grants YOLO."""
    branch = f"badge-pr-{int(time.time())}-{index}"

    if dry_run:
        extra = " (co-authored)" if coauthor else ""
        print(f"Would open and merge PR #{index} on branch {branch}{extra}")
        return

    run_command(["git", "checkout", base_branch], repo_path)
    run_command(["git", "pull", "origin", base_branch], repo_path)
    run_command(["git", "checkout", "-b", branch], repo_path)

    file_path = os.path.join(repo_path, FILE_NAME)
    with open(file_path, "a") as file:
        file.write(f"Badge PR {index} at {datetime.now().isoformat()}\n")

    message = f"Badge PR {index}"
    if coauthor:
        message += f"\n\nCo-authored-by: {coauthor}"

    run_command(["git", "add", FILE_NAME], repo_path)
    run_command(["git", "commit", "-m", message], repo_path)
    run_command(["git", "push", "-u", "origin", branch], repo_path)

    run_command(
        ["gh", "pr", "create",
         "--title", f"Badge PR {index}",
         "--body", "Automated badge PR.",
         "--head", branch,
         "--base", base_branch],
        repo_path
    )
    # Merging your own PR with no review is what triggers YOLO.
    run_command(
        ["gh", "pr", "merge", branch, "--merge", "--delete-branch"],
        repo_path
    )
    run_command(["git", "checkout", base_branch], repo_path)
    run_command(["git", "pull", "origin", base_branch], repo_path)
    print(f"PR {index} merged")


def do_quickdraw(repo_path, dry_run):
    """Open an issue and close it immediately (well under the 5-minute limit)."""
    if dry_run:
        print("Would open an issue and close it immediately (Quickdraw)")
        return

    url = run_output(
        ["gh", "issue", "create",
         "--title", "Quickdraw",
         "--body", "Closing this within 5 minutes."],
        repo_path
    )
    run_command(["gh", "issue", "close", url], repo_path)
    print(f"Quickdraw issue opened and closed: {url}")


def run_badges(args):
    repo_path = os.path.abspath(args.repo)
    if not os.path.isdir(os.path.join(repo_path, ".git")):
        raise SystemExit(f"Not a git repository: {repo_path}")

    dry_run = not args.apply
    coauthor = args.coauthor

    if dry_run:
        base_branch = "main"
        print(f"Dry run - planned actions ({args.count} PRs):")
    else:
        base_branch = get_default_branch(repo_path)

    if args.quickdraw:
        do_quickdraw(repo_path, dry_run)

    for i in range(1, args.count + 1):
        make_badge_pr(repo_path, base_branch, i, coauthor, dry_run)
        if not dry_run and i < args.count:
            time.sleep(args.sleep)

    if not dry_run:
        print(f"\nDone: {args.count} PRs merged.")
        print("Badges update within a few minutes on your profile.")
        print("Tiers - Pull Shark: 2/16/128/1024, Pair Extraordinaire: 1/10/24/48")


def main():
    parser = argparse.ArgumentParser(
        description="Contribution graph filler + GitHub achievement badges"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    p_contrib = subparsers.add_parser(
        "contributions", help="Backfill daily commits (original behavior)"
    )
    p_contrib.add_argument("--repo", default=REPO_PATH, help="Local git repository path")
    p_contrib.add_argument("--apply", action="store_true", help="Create commits instead of previewing")
    p_contrib.add_argument("--push", action="store_true", help="Push after creating commits")

    p_badges = subparsers.add_parser(
        "badges",
        help="Earn Pull Shark / Pair Extraordinaire / YOLO / Quickdraw via merged PRs"
    )
    p_badges.add_argument("--repo", default=REPO_PATH, help="Local git repository path")
    p_badges.add_argument("--apply", action="store_true", help="Actually create PRs instead of previewing")
    p_badges.add_argument(
        "--count", type=int, default=2,
        help="Number of PRs to open and merge (Pull Shark tiers: 2/16/128/1024)"
    )
    p_badges.add_argument(
        "--coauthor", default=DEFAULT_COAUTHOR,
        help='Co-author for Pair Extraordinaire, e.g. "Name <id+user@users.noreply.github.com>"'
    )
    p_badges.add_argument("--quickdraw", action="store_true", help="Also open+close an issue for Quickdraw")
    p_badges.add_argument(
        "--sleep", type=int, default=DEFAULT_SLEEP,
        help="Seconds to wait between PRs (avoids GitHub rate limits)"
    )

    args = parser.parse_args()

    if args.command == "contributions":
        run_contributions(args)
    else:
        run_badges(args)


if __name__ == "__main__":
    main()
