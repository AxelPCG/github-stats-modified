#!/usr/bin/python3

import asyncio
import os
from typing import Dict, List, Optional, Set, Tuple, Any, cast

import aiohttp
import requests


###############################################################################
# Main Classes
###############################################################################


class Queries(object):
    """
    Class with functions to query the GitHub GraphQL (v4) API and the REST (v3)
    API. Also includes functions to dynamically generate GraphQL queries.
    """

    def __init__(
        self,
        username: str,
        access_token: str,
        session: aiohttp.ClientSession,
        max_connections: int = 10,
    ):
        self.username = username
        self.access_token = access_token
        self.session = session
        self.semaphore = asyncio.Semaphore(max_connections)

    async def query(self, generated_query: str) -> Dict:
        """
        Make a request to the GraphQL API using the authentication token from
        the environment
        :param generated_query: string query to be sent to the API
        :return: decoded GraphQL JSON output
        """
        headers = {
            "Authorization": f"Bearer {self.access_token}",
        }
        try:
            async with self.semaphore:
                r_async = await self.session.post(
                    "https://api.github.com/graphql",
                    headers=headers,
                    json={"query": generated_query},
                )
            result = await r_async.json()
            if result is not None:
                return result
        except Exception:
            print("aiohttp failed for GraphQL query")
            # Fall back on non-async requests
            async with self.semaphore:
                r_requests = requests.post(
                    "https://api.github.com/graphql",
                    headers=headers,
                    json={"query": generated_query},
                )
                result = r_requests.json()
                if result is not None:
                    return result
        return dict()

    async def query_rest(self, path: str, params: Optional[Dict] = None) -> Dict:
        """
        Make a request to the REST API
        :param path: API path to query
        :param params: Query parameters to be passed to the API
        :return: deserialized REST JSON output
        """

        for attempt in range(60):
            headers = {
                "Authorization": f"token {self.access_token}",
            }

            # API de busca de commits requer header especial
            if "/search/commits" in path:
                headers["Accept"] = "application/vnd.github.cloak-preview+json"

            if params is None:
                params = dict()
            if path.startswith("/"):
                path = path[1:]
            try:
                async with self.semaphore:
                    r_async = await self.session.get(
                        f"https://api.github.com/{path}",
                        headers=headers,
                        params=tuple(params.items()),
                    )
                if r_async.status == 202:
                    print(
                        f"Request to {path} returned 202 (processing). Retrying in 2s... (attempt {attempt + 1}/60)"
                    )
                    await asyncio.sleep(2)
                    continue
                elif r_async.status == 403:
                    print(
                        f"Request to {path} returned 403 (rate limit). Retrying in 5s... (attempt {attempt + 1}/60)"
                    )
                    await asyncio.sleep(5)
                    continue
                elif r_async.status == 404:
                    print(f"Request to {path} returned 404 (not found). Skipping...")
                    return dict()

                result = await r_async.json()
                if result is not None:
                    return result
            except Exception as e:
                print(f"aiohttp failed for rest query to {path}: {e}")
                # Fall back on non-async requests
                try:
                    async with self.semaphore:
                        r_requests = requests.get(
                            f"https://api.github.com/{path}",
                            headers=headers,
                            params=tuple(params.items()),
                        )
                        if r_requests.status_code == 202:
                            print(
                                f"Fallback request to {path} returned 202. Retrying in 2s... (attempt {attempt + 1}/60)"
                            )
                            await asyncio.sleep(2)
                            continue
                        elif r_requests.status_code == 403:
                            print(
                                f"Fallback request to {path} returned 403. Retrying in 5s... (attempt {attempt + 1}/60)"
                            )
                            await asyncio.sleep(5)
                            continue
                        elif r_requests.status_code == 404:
                            print(
                                f"Fallback request to {path} returned 404. Skipping..."
                            )
                            return dict()
                        elif r_requests.status_code == 200:
                            result_json = r_requests.json()
                            if result_json is not None:
                                return result_json
                except Exception as e2:
                    print(f"Both aiohttp and requests failed for {path}: {e2}")

        print(f"Too many retries for {path}. Data will be incomplete.")
        return dict()

    @staticmethod
    def summary_query() -> str:
        """
        :return: GraphQL query with summary of user stats
        """
        return """query {
  viewer {
    login
    name
    repositories(first: 100, ownerAffiliations: OWNER, isFork: false) {
      totalCount
      edges {
        node {
          stargazers {
            totalCount
          }
          forkCount
        }
      }
    }
    pullRequests(first: 1) {
      totalCount
    }
    issues(first: 1) {
        totalCount
    }
    contributionsCollection {
      totalCommitContributions
      restrictedContributionsCount
    }
  }
}
"""

    @staticmethod
    def repos_overview(
        contrib_cursor: Optional[str] = None, owned_cursor: Optional[str] = None
    ) -> str:
        """
        :return: GraphQL query with overview of user repositories
        """
        return f"""{{
  viewer {{
    login
    name
    repositories(
        first: 100,
        orderBy: {{
            field: UPDATED_AT,
            direction: DESC
        }},
        isFork: false,
        after: {"null" if owned_cursor is None else '"' + owned_cursor + '"'}
    ) {{
      pageInfo {{
        hasNextPage
        endCursor
      }}
      nodes {{
        nameWithOwner
        stargazers {{
          totalCount
        }}
        forkCount
        languages(first: 10, orderBy: {{field: SIZE, direction: DESC}}) {{
          edges {{
            size
            node {{
              name
              color
            }}
          }}
        }}
      }}
    }}
    repositoriesContributedTo(
        first: 100,
        includeUserRepositories: false,
        orderBy: {{
            field: UPDATED_AT,
            direction: DESC
        }},
        contributionTypes: [
            COMMIT,
            PULL_REQUEST,
            REPOSITORY,
            PULL_REQUEST_REVIEW
        ]
        after: {"null" if contrib_cursor is None else '"' + contrib_cursor + '"'}
    ) {{
      pageInfo {{
        hasNextPage
        endCursor
      }}
      nodes {{
        nameWithOwner
        stargazers {{
          totalCount
        }}
        forkCount
        languages(first: 10, orderBy: {{field: SIZE, direction: DESC}}) {{
          edges {{
            size
            node {{
              name
              color
            }}
          }}
        }}
      }}
    }}
  }}
}}
"""

    @staticmethod
    def contrib_years() -> str:
        """
        :return: GraphQL query to get all years the user has been a contributor
        """
        return """
query {
  viewer {
    contributionsCollection {
      contributionYears
    }
  }
}
"""

    @staticmethod
    def contribs_by_year(year: str) -> str:
        """
        :param year: year to query for
        :return: portion of a GraphQL query with desired info for a given year
        """
        return f"""
    year{year}: contributionsCollection(
        from: "{year}-01-01T00:00:00Z",
        to: "{int(year) + 1}-01-01T00:00:00Z"
    ) {{
      contributionCalendar {{
        totalContributions
      }}
    }}
"""

    @classmethod
    def all_contribs(cls, years: List[str]) -> str:
        """
        :param years: list of years to get contributions for
        :return: query to retrieve contribution information for all user years
        """
        by_years = "\n".join(map(cls.contribs_by_year, years))
        return f"""
query {{
  viewer {{
    {by_years}
  }}
}}
"""


class Stats(object):
    """
    Retrieve and store statistics about GitHub usage.
    """

    def __init__(
        self,
        username: str,
        access_token: str,
        session: aiohttp.ClientSession,
        exclude_repos: Optional[Set] = None,
        exclude_langs: Optional[Set] = None,
        ignore_forked_repos: bool = False,
        emails: Optional[List[str]] = None,
    ):
        self.username = username
        self._ignore_forked_repos = ignore_forked_repos
        self._exclude_repos = set() if exclude_repos is None else exclude_repos
        self._exclude_langs = set() if exclude_langs is None else exclude_langs
        self.queries = Queries(username, access_token, session)
        self._emails = emails

        self._name: Optional[str] = None
        self._stargazers: Optional[int] = None
        self._forks: Optional[int] = None
        self._forks_made: Optional[int] = None
        self._total_contributions: Optional[int] = None
        self._total_commits: Optional[int] = None
        self._prs: Optional[int] = None
        self._issues: Optional[int] = None
        self._languages: Optional[Dict[str, Any]] = None
        self._repos: Optional[Set[str]] = None
        self._lines_changed: Optional[Tuple[int, int]] = None
        self._views: Optional[int] = None

        # Lock to prevent concurrent get_stats calls
        self._stats_lock: Optional[asyncio.Lock] = None
        self._stats_fetched: bool = False

    async def to_str(self) -> str:
        """
        :return: summary of all available statistics
        """
        languages = await self.languages_proportional
        formatted_languages = "\n  - ".join(
            [f"{k}: {v:0.4f}%" for k, v in languages.items()]
        )
        lines_changed = await self.lines_changed
        return f"""Name: {await self.name}
Stargazers: {await self.stargazers:,}
Forks: {await self.forks:,}
All-time contributions: {await self.total_contributions:,}
Repositories with contributions: {len(await self.repos)}
Lines of code added: {lines_changed[0]:,}
Lines of code deleted: {lines_changed[1]:,}
Lines of code changed: {lines_changed[0] + lines_changed[1]:,}
Project page views: {await self.views:,}
Languages:
  - {formatted_languages}"""

    async def get_summary_stats(self) -> None:
        """
        Get lots of summary statistics using one big query. Sets many attributes.
        NOTE: This only sets _prs and _issues. Other stats come from get_stats()
        or dedicated methods to avoid conflicts.
        """
        raw_results = await self.queries.query(self.queries.summary_query())
        if raw_results is None:
            return
        viewer = raw_results.get("data", {}).get("viewer", {})
        if not viewer:
            return

        if self._name is None:
            self._name = viewer.get("name") or viewer.get("login", "No Name")

        # Only set PRs and Issues here - stars/forks come from get_stats()
        self._prs = viewer.get("pullRequests", {}).get("totalCount", 0)
        self._issues = viewer.get("issues", {}).get("totalCount", 0)

    async def get_stats(self) -> None:
        """
        Get lots of summary statistics using one big query. Sets many attributes.
        Thread-safe: uses lock to prevent concurrent calls.
        """
        # Initialize lock if needed
        if self._stats_lock is None:
            self._stats_lock = asyncio.Lock()

        async with self._stats_lock:
            # Check if already fetched (another coroutine may have done it while we waited)
            if self._stats_fetched:
                return

            self._stargazers = 0
            self._forks = 0
            self._languages = dict()
            self._repos = set()

            exclude_langs_lower = {x.lower() for x in self._exclude_langs}
            print(f"Fetching stats for user: {self.username}")
            print(f"Excluding repositories: {self._exclude_repos}")
            print(f"Excluding languages: {self._exclude_langs}")
            print(f"Ignore forked repos: {self._ignore_forked_repos}")

            next_owned = None
            next_contrib = None
            page_count = 0
            while True:
                page_count += 1
                print(f"Fetching page {page_count}...")

                raw_results = await self.queries.query(
                    Queries.repos_overview(
                        owned_cursor=next_owned, contrib_cursor=next_contrib
                    )
                )
                raw_results = raw_results if raw_results is not None else {}

                self._name = (
                    raw_results.get("data", {}).get("viewer", {}).get("name", None)
                )
                if self._name is None:
                    self._name = (
                        raw_results.get("data", {})
                        .get("viewer", {})
                        .get("login", "No Name")
                    )

                contrib_repos = (
                    raw_results.get("data", {})
                    .get("viewer", {})
                    .get("repositoriesContributedTo", {})
                )
                owned_repos = (
                    raw_results.get("data", {})
                    .get("viewer", {})
                    .get("repositories", {})
                )

                repos = owned_repos.get("nodes", [])
                if not self._ignore_forked_repos:
                    repos += contrib_repos.get("nodes", [])

                processed_repos = 0
                for repo in repos:
                    if repo is None:
                        continue
                    name = repo.get("nameWithOwner")
                    if name in self._repos or name in self._exclude_repos:
                        continue
                    self._repos.add(name)
                    processed_repos += 1

                    self._stargazers += repo.get("stargazers", {}).get("totalCount", 0)
                    self._forks += repo.get("forkCount", 0)

                    repo_langs = repo.get("languages", {}).get("edges", [])
                    if repo_langs:
                        lang_names = [
                            entry.get("node", {}).get("name", "?") for entry in repo_langs
                        ]
                        print(f"  Repo {name}: {lang_names}")

                    for lang in repo_langs:
                        lang_name = lang.get("node", {}).get("name", "Other")
                        lang_size = lang.get("size", 0)
                        if lang_name.lower() in exclude_langs_lower:
                            continue
                        if lang_name in self._languages:
                            self._languages[lang_name]["size"] += lang_size
                            self._languages[lang_name]["occurrences"] += 1
                        else:
                            self._languages[lang_name] = {
                                "size": lang_size,
                                "occurrences": 1,
                                "color": lang.get("node", {}).get("color"),
                            }

                print(f"Processed {processed_repos} repositories on page {page_count}")

                if owned_repos.get("pageInfo", {}).get(
                    "hasNextPage", False
                ) or contrib_repos.get("pageInfo", {}).get("hasNextPage", False):
                    next_owned = owned_repos.get("pageInfo", {}).get(
                        "endCursor", next_owned
                    )
                    next_contrib = contrib_repos.get("pageInfo", {}).get(
                        "endCursor", next_contrib
                    )
                else:
                    break

            print(f"Total repositories found: {len(self._repos)}")
            print(f"Languages found: {len(self._languages)}")

            langs_total = sum([v.get("size", 0) for v in self._languages.values()])
            for k, v in self._languages.items():
                v["prop"] = (
                    100 * (v.get("size", 0) / langs_total) if langs_total > 0 else 0
                )

            # Debug: show language breakdown
            print("Language breakdown (by size):")
            sorted_langs = sorted(
                self._languages.items(), key=lambda x: x[1].get("size", 0), reverse=True
            )
            for lang_name, lang_data in sorted_langs[:15]:  # Top 15
                print(
                    f"  {lang_name}: {lang_data.get('size', 0):,} bytes ({lang_data.get('prop', 0):.2f}%)"
                )

            self._stats_fetched = True

    @property
    async def name(self) -> str:
        """
        :return: GitHub user's name (e.g., Jacob Strieb)
        """
        if self._name is not None:
            return self._name
        await self.get_stats()
        assert self._name is not None
        return self._name

    @property
    async def stargazers(self) -> int:
        """
        :return: total number of stargazers on user's repos
        """
        if self._stargazers is not None:
            return self._stargazers
        await self.get_stats()
        assert self._stargazers is not None
        return self._stargazers

    @property
    async def forks(self) -> int:
        """
        :return: total number of forks on user's repos + forks made by user
        """
        # Primeiro, obter forks recebidos via get_stats
        if self._forks is None:
            await self.get_stats()
        assert self._forks is not None
        forks_received = self._forks

        # Depois, obter forks feitos
        forks_made = await self.forks_made

        # Retornar a soma total
        total = forks_received + forks_made
        print(f"Total forks: {forks_received} received + {forks_made} made = {total}")

        return total

    @property
    async def languages(self) -> Dict:
        """
        :return: summary of languages used by the user
        """
        if self._languages is not None:
            return self._languages
        await self.get_stats()
        assert self._languages is not None
        return self._languages

    @property
    async def languages_proportional(self) -> Dict:
        """
        :return: summary of languages used by the user, with proportional usage
        """
        if self._languages is None:
            await self.get_stats()
            assert self._languages is not None

        return {k: v.get("prop", 0) for (k, v) in self._languages.items()}

    @property
    async def repos(self) -> Set[str]:
        """
        :return: list of names of user's repos
        """
        if self._repos is not None:
            return self._repos
        await self.get_stats()
        assert self._repos is not None
        return self._repos

    @property
    async def total_contributions(self) -> int:
        """
        :return: count of user's total contributions as defined by GitHub (all years)
        """
        if self._total_contributions is not None:
            return self._total_contributions

        print("Fetching total contributions from all years...")
        self._total_contributions = 0
        years = (
            (await self.queries.query(Queries.contrib_years()))
            .get("data", {})
            .get("viewer", {})
            .get("contributionsCollection", {})
            .get("contributionYears", [])
        )
        print(f"Found contribution years: {years}")

        if not years:
            print("WARNING: No contribution years found!")
            return 0

        by_year = (
            (await self.queries.query(Queries.all_contribs(years)))
            .get("data", {})
            .get("viewer", {})
            .values()
        )
        for year in by_year:
            contrib = year.get("contributionCalendar", {}).get("totalContributions", 0)
            self._total_contributions += contrib

        print(f"Total contributions (all years): {self._total_contributions}")
        return cast(int, self._total_contributions)

    @property
    async def lines_changed(self) -> Tuple[int, int]:
        """
        :return: count of total lines added, removed, or modified by the user
        """
        if self._lines_changed is not None:
            return self._lines_changed
        additions = 0
        deletions = 0
        repos = await self.repos
        print(f"Calculating lines changed for {len(repos)} repositories...")

        for i, repo in enumerate(repos):
            try:
                print(f"Processing repository {i + 1}/{len(repos)}: {repo}")
                r = await self.queries.query_rest(f"/repos/{repo}/stats/contributors")

                if not r or not isinstance(r, list):
                    print(f"Invalid response for {repo}: {type(r)}")
                    continue

                for author_obj in r:
                    # Handle malformed response from the API by skipping this repo
                    if not isinstance(author_obj, dict) or not isinstance(
                        author_obj.get("author", {}), dict
                    ):
                        continue
                    author = author_obj.get("author", {}).get("login", "")
                    if author.lower() != self.username.lower():
                        continue

                    weeks = author_obj.get("weeks", [])
                    if not isinstance(weeks, list):
                        continue

                    for week in weeks:
                        if isinstance(week, dict):
                            additions += week.get("a", 0)
                            deletions += week.get("d", 0)

            except Exception as e:
                print(f"Error processing {repo}: {e}")
                continue

        print(f"Total lines: +{additions}, -{deletions}")
        self._lines_changed = (additions, deletions)
        return self._lines_changed

    @property
    async def views(self) -> int:
        """
        Note: only returns views for the last 14 days (as-per GitHub API)
        :return: total number of page views the user's projects have received
        """
        if self._views is not None:
            return self._views

        total = 0
        repos = await self.repos
        print(f"Calculating views for {len(repos)} repositories...")

        for i, repo in enumerate(repos):
            try:
                print(f"Processing views for repository {i + 1}/{len(repos)}: {repo}")
                r = await self.queries.query_rest(f"/repos/{repo}/traffic/views")

                if not r or not isinstance(r, dict):
                    print(f"Invalid response for {repo}: {type(r)}")
                    continue

                views_data = r.get("views", [])
                if not isinstance(views_data, list):
                    continue

                for view in views_data:
                    if isinstance(view, dict):
                        total += view.get("count", 0)

            except Exception as e:
                print(f"Error processing views for {repo}: {e}")
                continue

        print(f"Total views (last 14 days): {total}")
        self._views = total
        return total

    @property
    async def total_commits(self) -> int:
        """
        Get the total number of commits made by the user (igual ao script original).
        """
        total_commits = 0
        if self._emails:
            for email in self._emails:
                query = f'''
                query {{
                  user(login: "{self.username}") {{
                    contributionsCollection {{
                      totalCommitContributions
                    }}
                  }}
                }}
                '''
                response = await self.queries.query(query)
                if "data" in response and "user" in response["data"]:
                    total_commit = response["data"]["user"]["contributionsCollection"][
                        "totalCommitContributions"
                    ]
                    total_commits += total_commit
                else:
                    print(f"Erro ao buscar commits para email {email}: {response}")
        else:
            query = f'''
            query {{
              user(login: "{self.username}") {{
                contributionsCollection {{
                  totalCommitContributions
                }}
              }}
            }}
            '''
            response = await self.queries.query(query)
            if "data" in response and "user" in response["data"]:
                total_commits = response["data"]["user"]["contributionsCollection"][
                    "totalCommitContributions"
                ]
            else:
                print(
                    f"Erro ao buscar commits para username {self.username}: {response}"
                )
        return total_commits

    @property
    async def prs(self) -> int:
        """
        Get the total number of pull requests made by the user.
        """
        if self._prs is not None:
            return self._prs
        await self.get_summary_stats()
        assert self._prs is not None
        return self._prs

    @property
    async def issues(self) -> int:
        """
        Get the total number of issues opened by the user.
        """
        if self._issues is not None:
            return self._issues
        await self.get_summary_stats()
        assert self._issues is not None
        return self._issues

    async def get_user_forks(self) -> None:
        """
        Get repositories forked by the user
        """
        if self._forks_made is not None:
            return

        print("Fetching forks made by user...")

        total_forks = 0
        cursor = None

        while True:
            query = f"""
query {{
  viewer {{
    repositories(first: 100, isFork: true, ownerAffiliations: OWNER, after: {"null" if cursor is None else '"' + cursor + '"'}) {{
      totalCount
      pageInfo {{
        hasNextPage
        endCursor
      }}
      nodes {{
        nameWithOwner
        parent {{
          nameWithOwner
        }}
      }}
    }}
  }}
}}
"""
            raw_results = await self.queries.query(query)

            if raw_results is None:
                self._forks_made = 0
                return

            viewer = raw_results.get("data", {}).get("viewer", {})
            if not viewer:
                self._forks_made = 0
                return

            repositories = viewer.get("repositories", {})

            # Na primeira página, pegamos o totalCount
            if cursor is None:
                total_forks = repositories.get("totalCount", 0)

            # Verificar se há mais páginas
            page_info = repositories.get("pageInfo", {})
            if page_info.get("hasNextPage"):
                cursor = page_info.get("endCursor")
            else:
                break

        self._forks_made = total_forks
        print(f"Found {self._forks_made} forks made by user")

    @property
    async def forks_made(self) -> int:
        """
        :return: total number of forks made by the user
        """
        if self._forks_made is not None:
            return self._forks_made
        await self.get_user_forks()
        assert self._forks_made is not None
        return self._forks_made

    async def get_all_time_commits(self) -> None:
        """
        Get total commits from all years via GraphQL
        """
        print("Fetching total commits from all years...")

        # Buscar todos os anos de contribuição
        years = (
            (await self.queries.query(Queries.contrib_years()))
            .get("data", {})
            .get("viewer", {})
            .get("contributionsCollection", {})
            .get("contributionYears", [])
        )

        print(f"Found contribution years: {years}")
        total_commits = 0

        # Para cada ano, buscar o total de commits
        for year in years:
            query = f"""
query {{
  viewer {{
    contributionsCollection(from: "{year}-01-01T00:00:00Z", to: "{int(year) + 1}-01-01T00:00:00Z") {{
      totalCommitContributions
      restrictedContributionsCount
    }}
  }}
}}
"""
            result = await self.queries.query(query)
            if result and "data" in result:
                contrib = (
                    result.get("data", {})
                    .get("viewer", {})
                    .get("contributionsCollection", {})
                )
                year_commits = contrib.get("totalCommitContributions", 0) + contrib.get(
                    "restrictedContributionsCount", 0
                )
                total_commits += year_commits
                print(f"  Year {year}: {year_commits} commits")
            else:
                print(f"  Year {year}: Failed to fetch data")

        self._total_commits = total_commits
        print(f"Total commits from all years: {total_commits}")


###############################################################################
# Main Function
###############################################################################


async def main() -> None:
    """
    Used mostly for testing; this module is not usually run standalone
    """
    access_token = os.getenv("ACCESS_TOKEN")
    user = os.getenv("GITHUB_ACTOR")
    if access_token is None or user is None:
        raise RuntimeError(
            "ACCESS_TOKEN and GITHUB_ACTOR environment variables cannot be None!"
        )
    async with aiohttp.ClientSession() as session:
        s = Stats(user, access_token, session)
        print(await s.to_str())


if __name__ == "__main__":
    asyncio.run(main())
