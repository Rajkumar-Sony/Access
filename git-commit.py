import os
import json
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

# Badge tiers, for reference when picking counts:
#   Pull Shark:          2, 16, 128, 1024 merged PRs
#   Pair Extraordinaire: 1, 10, 24, 48 merged co-authored PRs
#   Galaxy Brain:        2, 8, 16, 32 accepted discussion answers
#   YOLO:                1 unreviewed merge (single tier)
#   Quickdraw:           1 issue/PR closed within 5 min (single tier)
# Not automatable solo:
#   Starstruck:          16/128/512/4096 stars from OTHER accounts
#   Public Sponsor:      requires a paid GitHub Sponsors sponsorship
#   Arctic Code Vault / Mars 2020 Helicopter: retired, no longer earnable


def run_command(command, repo_path, env=None):
    subprocess.run(
        command,
        cwd=repo_path,
        check=True,
        env=env
    )


def run_output(command, repo_path, env=None):
    return subprocess.check_output(command, cwd=repo_path, text=True, env=env).strip()


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


def get_repo_owner_name(repo_path):
    name_with_owner = run_output(
        ["gh", "repo", "view", "--json", "nameWithOwner",
         "--jq", ".nameWithOwner"],
        repo_path
    )
    owner, name = name_with_owner.split("/", 1)
    return owner, name


def gh_graphql(repo_path, query, variables, token=None):
    cmd = ["gh", "api", "graphql", "-f", f"query={query}"]
    for key, value in variables.items():
        cmd += ["-f", f"{key}={value}"]
    env = os.environ.copy()
    if token:
        env["GH_TOKEN"] = token
    return json.loads(run_output(cmd, repo_path, env=env))


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


def do_star(repo_path, dry_run):
    """Star your own repo. Counts 1 toward Starstruck (needs 16 total stars)."""
    owner, name = ("<owner>", "<repo>") if dry_run else get_repo_owner_name(repo_path)
    if dry_run:
        print("Would star the repository (1 of the 16 stars Starstruck needs)")
        return
    run_command(["gh", "api", "-X", "PUT", f"user/starred/{owner}/{name}"], repo_path)
    print(f"Starred {owner}/{name}")


def get_answerable_category(repo_path, owner, name):
    """Enable discussions if needed and return the repo ID and a Q&A category ID."""
    run_command(
        ["gh", "api", "-X", "PATCH", f"repos/{owner}/{name}",
         "-F", "has_discussions=true"],
        repo_path
    )
    query = """
    query($owner: String!, $name: String!) {
      repository(owner: $owner, name: $name) {
        id
        discussionCategories(first: 25) {
          nodes { id name isAnswerable }
        }
      }
    }"""
    data = gh_graphql(repo_path, query, {"owner": owner, "name": name})
    repo = data["data"]["repository"]
    for node in repo["discussionCategories"]["nodes"]:
        if node["isAnswerable"]:
            return repo["id"], node["id"]
    raise SystemExit(
        "No answerable (Q&A) discussion category found. "
        "Enable one under the repo's Discussions settings."
    )


def do_galaxy_brain(repo_path, count, helper_token, dry_run):
    """Galaxy Brain = your answer gets marked as accepted on a discussion.

    The discussion should be created by a DIFFERENT account (answers to your
    own discussion do not count), so pass --helper-token with a token from a
    second account. That account creates the discussion, your main account
    answers, and your main account (as repo maintainer) marks it accepted.
    Tiers: 2, 8, 16, 32 accepted answers."""
    if dry_run:
        who = "helper account" if helper_token else "YOUR OWN account (may not count!)"
        print(f"Would create {count} Q&A discussions (as {who}), "
              f"answer each, and mark the answers accepted")
        return

    if not helper_token:
        print("WARNING: no --helper-token given. Answers on your own "
              "discussions usually do NOT count toward Galaxy Brain.")

    owner, name = get_repo_owner_name(repo_path)
    repo_id, category_id = get_answerable_category(repo_path, owner, name)

    create_q = """
    mutation($repoId: ID!, $catId: ID!, $title: String!, $body: String!) {
      createDiscussion(input: {repositoryId: $repoId, categoryId: $catId,
                               title: $title, body: $body}) {
        discussion { id url }
      }
    }"""
    answer_q = """
    mutation($discussionId: ID!, $body: String!) {
      addDiscussionComment(input: {discussionId: $discussionId, body: $body}) {
        comment { id }
      }
    }"""
    mark_q = """
    mutation($commentId: ID!) {
      markDiscussionCommentAsAnswer(input: {id: $commentId}) {
        discussion { id }
      }
    }"""

    for i in range(1, count + 1):
        created = gh_graphql(
            repo_path, create_q,
            {"repoId": repo_id, "catId": category_id,
             "title": f"Question {i}: best approach?",
             "body": "Looking for the recommended approach here."},
            token=helper_token
        )
        discussion = created["data"]["createDiscussion"]["discussion"]

        answered = gh_graphql(
            repo_path, answer_q,
            {"discussionId": discussion["id"],
             "body": "The recommended approach is documented in the README."}
        )
        comment_id = answered["data"]["addDiscussionComment"]["comment"]["id"]

        gh_graphql(repo_path, mark_q, {"commentId": comment_id})
        print(f"Galaxy Brain {i}/{count}: answered and accepted {discussion['url']}")
        if i < count:
            time.sleep(DEFAULT_SLEEP)


def print_coverage(args):
    coauthored = "yes" if args.coauthor else "no (--coauthor not set)"
    print("\nBadge coverage this run:")
    print(f"  Pull Shark           {args.count} merged PRs (tiers 2/16/128/1024)")
    print(f"  Pair Extraordinaire  co-authored: {coauthored} (tiers 1/10/24/48)")
    print(f"  YOLO                 first unreviewed merge (single tier)")
    print(f"  Quickdraw            {'yes' if args.quickdraw else 'no (--quickdraw not set)'} (single tier)")
    print(f"  Galaxy Brain         {args.galaxy_brain} accepted answers (tiers 2/8/16/32)")
    print(f"  Starstruck           {'self-star only' if args.star else 'no'} - needs 16+ stars from others")
    print("  Public Sponsor       manual: sponsor anyone $1+ at github.com/sponsors")
    print("  Arctic Code Vault / Mars Helicopter: retired, impossible to earn now")


def run_badges(args):
    repo_path = os.path.abspath(args.repo)
    if not os.path.isdir(os.path.join(repo_path, ".git")):
        raise SystemExit(f"Not a git repository: {repo_path}")

    dry_run = not args.apply
    helper_token = args.helper_token or os.environ.get("HELPER_GH_TOKEN", "")

    if args.all:
        args.quickdraw = True
        args.star = True
        if args.galaxy_brain == 0:
            args.galaxy_brain = 2

    if dry_run:
        base_branch = "main"
        print(f"Dry run - planned actions ({args.count} PRs):")
    else:
        base_branch = get_default_branch(repo_path)

    if args.quickdraw:
        do_quickdraw(repo_path, dry_run)

    if args.star:
        do_star(repo_path, dry_run)

    for i in range(1, args.count + 1):
        make_badge_pr(repo_path, base_branch, i, args.coauthor, dry_run)
        if not dry_run and i < args.count:
            time.sleep(args.sleep)

    if args.galaxy_brain > 0:
        do_galaxy_brain(repo_path, args.galaxy_brain, helper_token, dry_run)

    print_coverage(args)
    if not dry_run:
        print("\nDone. Badges update on your profile within a few minutes.")


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
        help="Earn Pull Shark / Pair Extraordinaire / YOLO / Quickdraw / Galaxy Brain"
    )
    p_badges.add_argument("--repo", default=REPO_PATH, help="Local git repository path")
    p_badges.add_argument("--apply", action="store_true", help="Actually create PRs instead of previewing")
    p_badges.add_argument(
        "--all", action="store_true",
        help="Enable quickdraw, star, and galaxy-brain (2) in one run"
    )
    p_badges.add_argument(
        "--count", type=int, default=2,
        help="Number of PRs to open and merge (Pull Shark tiers: 2/16/128/1024)"
    )
    p_badges.add_argument(
        "--coauthor", default=DEFAULT_COAUTHOR,
        help='Co-author for Pair Extraordinaire, e.g. "Name <id+user@users.noreply.github.com>"'
    )
    p_badges.add_argument("--quickdraw", action="store_true", help="Open+close an issue for Quickdraw")
    p_badges.add_argument("--star", action="store_true", help="Star your own repo (1 toward Starstruck)")
    p_badges.add_argument(
        "--galaxy-brain", type=int, default=0,
        help="Number of accepted discussion answers to create (tiers: 2/8/16/32)"
    )
    p_badges.add_argument(
        "--helper-token", default="",
        help="Token of a SECOND account that creates the Galaxy Brain discussions "
             "(also read from HELPER_GH_TOKEN env var)"
    )
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
