# Review a pull request in the browser

The Browser preview workflow builds the real Pyodide demo for each ready pull request.
It uses the fictional example household and keeps the existing CI screenshot artifacts.
Production stays on GitHub Pages and deploys with releases.

A same-repository pull request gets a Cloudflare Worker named `vuurtoren-site-pr-<number>`.
Its deployment link appears on the pull request and in the preview job summary.
The preview uses `/vuurtoren/`, as production does, and sends `X-Robots-Tag: noindex`.
Forks and bot pull requests do not deploy. Missing credentials produce an explicit skip notice.

## Enable preview publication

Create a `preview` environment in the repository's GitHub settings.
Add `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID` as environment secrets.
The token needs Account → Workers Scripts → Edit in the chosen Cloudflare account.
That account must have a workers.dev subdomain.
Use a separate preview account if an account-wide token could reach other production Workers.
Ready pull request code can read this environment's token, so only trusted branches may deploy.

Rerun Browser preview after adding the secrets. Confirm its deployment URL opens the example household.
Closing a pull request or marking it draft deletes its Worker.
The daily retirement sweep removes missed previews; a failed GitHub lookup keeps the Worker.

The preview setup does not need real household data, browser credentials or a running local database.
