#!/usr/bin/python3

import asyncio
import os
import re

import aiohttp

from github_stats import Stats


################################################################################
# Helper Functions
################################################################################


def generate_output_folder() -> None:
    """
    Create the output folder if it does not already exist
    """
    if not os.path.isdir("generated"):
        os.mkdir("generated")


################################################################################
# Individual Image Generation Functions
################################################################################


async def generate_overview(s: Stats) -> None:
    """
    Generate an SVG badge with summary statistics
    :param s: Represents user's GitHub statistics
    """
    try:
        print("Starting generation of overview.svg...")
        with open("templates/overview.svg", "r") as f:
            output = f.read()

        print("Fetching statistics data...")
        output = re.sub("{{ name }}", await s.name, output)
        output = re.sub("{{ stars }}", f"{await s.stargazers:,}", output)
        output = re.sub("{{ forks }}", f"{await s.forks:,}", output)
        output = re.sub("{{ contributions }}", f"{await s.total_contributions:,}", output)
        output = re.sub("{{ views }}", f"{await s.views:,}", output)
        output = re.sub("{{ repos }}", f"{len(await s.repos):,}", output)
        commits = await s.total_commits
        output = re.sub("{{ commits }}", f"{commits:,}", output)
        output = re.sub("{{ prs }}", f"{await s.prs:,}", output)
        output = re.sub("{{ issues }}", f"{await s.issues:,}", output)

        generate_output_folder()
        output_path = "generated/overview.svg"
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(output)
        
        # Verify file was created and has content
        if not os.path.exists(output_path):
            raise FileNotFoundError(f"Failed to create {output_path}")
        file_size = os.path.getsize(output_path)
        if file_size == 0:
            raise ValueError(f"Generated {output_path} is empty!")
        print(f"Successfully generated overview.svg ({file_size} bytes)")
    except Exception as e:
        print(f"ERROR generating overview.svg: {e}")
        import traceback
        traceback.print_exc()
        raise


async def generate_languages(s: Stats) -> None:
    """
    Generate an SVG badge with summary languages used
    :param s: Represents user's GitHub statistics
    """
    try:
        print("Starting generation of languages.svg...")
        with open("templates/languages.svg", "r") as f:
            output = f.read()

        print("Fetching languages data...")
        languages = await s.languages
        print(f"Found {len(languages)} languages")
        
        if not languages:
            print("WARNING: No languages found! Generating empty languages.svg")
            progress = ""
            lang_list = ""
        else:
            progress = ""
            lang_list = ""
            sorted_languages = sorted(
                languages.items(), reverse=True, key=lambda t: t[1].get("size")
            )
            delay_between = 150
            for i, (lang, data) in enumerate(sorted_languages):
                color = data.get("color")
                color = color if color is not None else "#000000"
                progress += (
                    f'<span style="background-color: {color};'
                    f'width: {data.get("prop", 0):0.3f}%;" '
                    f'class="progress-item"></span>'
                )
                lang_list += f"""
<li style="animation-delay: {i * delay_between}ms;">
<svg xmlns="http://www.w3.org/2000/svg" class="octicon" style="fill:{color};"
viewBox="0 0 16 16" version="1.1" width="16" height="16"><path
fill-rule="evenodd" d="M8 4a4 4 0 100 8 4 4 0 000-8z"></path></svg>
<span class="lang">{lang}</span>
<span class="percent">{data.get("prop", 0):0.2f}%</span>
</li>

"""

        output = re.sub(r"{{ progress }}", progress, output)
        output = re.sub(r"{{ lang_list }}", lang_list, output)

        generate_output_folder()
        output_path = "generated/languages.svg"
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(output)
        
        # Verify file was created and has content
        if not os.path.exists(output_path):
            raise FileNotFoundError(f"Failed to create {output_path}")
        file_size = os.path.getsize(output_path)
        if file_size == 0:
            raise ValueError(f"Generated {output_path} is empty!")
        print(f"Successfully generated languages.svg ({file_size} bytes)")
    except Exception as e:
        print(f"ERROR generating languages.svg: {e}")
        import traceback
        traceback.print_exc()
        raise


################################################################################
# Main Function
################################################################################


async def main() -> None:
    """
    Generate all badges
    """
    access_token = os.getenv("ACCESS_TOKEN")
    if not access_token:
        # access_token = os.getenv("GITHUB_TOKEN")
        raise Exception("A personal access token is required to proceed!")
    user = os.getenv("GITHUB_ACTOR")
    if user is None:
        raise RuntimeError("Environment variable GITHUB_ACTOR must be set.")
    exclude_repos = os.getenv("EXCLUDED")
    excluded_repos = (
        {x.strip() for x in exclude_repos.split(",")} if exclude_repos else None
    )
    exclude_langs = os.getenv("EXCLUDED_LANGS")
    excluded_langs = (
        {x.strip() for x in exclude_langs.split(",")} if exclude_langs else None
    )
    # Convert a truthy value to a Boolean
    raw_ignore_forked_repos = os.getenv("EXCLUDE_FORKED_REPOS")
    ignore_forked_repos = (
        not not raw_ignore_forked_repos
        and raw_ignore_forked_repos.strip().lower() != "false"
    )
    emails = os.getenv("GIT_EMAILS")
    email_list = (
        list({x.strip() for x in emails.split(",")}) if emails else None
    )
    
    async with aiohttp.ClientSession() as session:
        s = Stats(
            user,
            access_token,
            session,
            exclude_repos=excluded_repos,
            exclude_langs=excluded_langs,
            ignore_forked_repos=ignore_forked_repos,
            emails=email_list,
        )
        try:
            # Generate both images in parallel, but catch errors individually
            results = await asyncio.gather(
                generate_languages(s),
                generate_overview(s),
                return_exceptions=True
            )
            
            # Check for exceptions
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    image_name = "languages.svg" if i == 0 else "overview.svg"
                    print(f"ERROR: Failed to generate {image_name}: {result}")
                    raise result
                    
            print("All images generated successfully!")
        except Exception as e:
            print(f"FATAL ERROR during image generation: {e}")
            import traceback
            traceback.print_exc()
            raise


if __name__ == "__main__":
    asyncio.run(main())